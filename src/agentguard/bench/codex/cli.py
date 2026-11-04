"""``python -m agentguard.bench.codex <command>``.

Model-free: ``list``, ``validate``, ``plan``, ``preflight``, ``dry-run``, ``analyze``.
Live (spends the ChatGPT plan's usage; requires ``--confirm-live``): ``run``, ``smoke``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from agentguard.bench.codex import (
    agents,
    appserver,
    guards,
    homes,
    limits,
    orchestrator,
    report,
    scripted,
    suite,
)
from agentguard.bench.codex.plan import Plan

DEFAULT_CODEX = shutil.which("codex") or str(Path.home() / ".local" / "bin" / "codex")
DEFAULT_UV = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
RESULTS = suite.BENCH_ROOT / "results"


# -- model-free commands ----------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> int:
    tasks = suite.load_suite(only=args.task or None)
    for task in tasks:
        print(f"{task.id:<34}{task.set:<11}{task.family:<24}{','.join(task.opportunity.mechanisms)}")
    counts = {s: sum(1 for t in tasks if t.set == s) for s in suite.SETS}
    print(f"\n{len(tasks)} task(s) {counts}; suite digest {suite.suite_digest(tasks)[:16]}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    tasks = suite.load_suite(only=args.task or None)
    # absolute, but not resolved: resolving a venv's python symlink would leave the venv
    python = os.path.abspath(args.python or scripted.default_python())
    failures = 0
    rows = []
    for task in tasks:
        result = scripted.validate_task(task, python)
        for v in result.variants:
            flag = "ok " if v.ok else "BAD"
            detail = (v.problem or ", ".join(v.reasons))[:90]
            print(f"{flag} {task.id:<34}{v.variant:<8}{v.outcome:<18}{detail}")
        failures += 0 if result.ok else 1
        rows.append(
            {
                "task": task.id,
                "ok": result.ok,
                "variants": [{s: getattr(v, s) for s in v.__slots__} for v in result.variants],
            }
        )
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\n{len(tasks) - failures}/{len(tasks)} task(s) validated")
    return 1 if failures else 0


def codex_version(codex_bin: str) -> str:
    out = subprocess.run([codex_bin, "--version"], capture_output=True, text=True, timeout=30).stdout
    match = re.search(r"(\d+\.\d+\.\d+)", out)
    return match.group(1) if match else out.strip()


def _cmd_plan(args: argparse.Namespace) -> int:
    tasks = suite.load_suite(only=args.task or None)
    plan = Plan(
        name=args.name,
        stage=args.stage,
        seed=args.seed,
        tasks=[t.id for t in tasks],
        phrasings=list(args.phrasing or suite.PHRASINGS),
        replicates=[int(r) for r in args.replicates.split(",")],
        model=args.model,
        effort=args.effort,
        agentguard_ref=args.agentguard_ref,
        codex_version=codex_version(args.codex),
        trust=args.trust,
        cell_timeout_s=args.cell_timeout,
        max_attempts=args.max_attempts,
        suite_digest=suite.suite_digest(tasks),
        notes=args.notes or "",
    )
    if args.stop_weekly_at is not None:
        plan.budget["stop_weekly_at"] = args.stop_weekly_at
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    plan.save(out)
    print(
        f"plan {plan.name}: {len(plan.pairs())} pairs = {2 * len(plan.pairs())} cells; "
        f"digest {plan.digest()[:16]}"
    )
    return 0


# -- wiring a real run ------------------------------------------------------------


class AgentBudgetSpent(orchestrator.Halt):
    """A hard cap on live agent invocations was reached (smoke runs)."""


class CappedAgent:
    """Refuses to start more than ``cap`` live agent runs, whatever the loop asks for.

    The runner re-runs void pairs; a smoke run must never turn into a third model call.
    """

    def __init__(self, inner: object, cap: int):
        self.inner = inner
        self.cap = cap
        self.started = 0

    def run(self, *args: object, **kwargs: object) -> agents.AgentRun:
        if self.started >= self.cap:
            raise AgentBudgetSpent(f"live agent cap of {self.cap} reached")
        self.started += 1
        return self.inner.run(*args, **kwargs)  # type: ignore[attr-defined]


def _real_runner(plan: Plan, run_dir: Path, args: argparse.Namespace) -> orchestrator.Runner:
    tasks = {t.id: t for t in suite.load_suite(only=plan.tasks)}
    work_root = Path(args.work_root).expanduser() if args.work_root else homes.default_work_root(plan.name)
    homes.assert_outside_tmp(work_root)
    homes.assert_outside_tmp(run_dir)
    state = homes.private_dir(work_root / "state")
    task_python = homes.make_task_env(state / "taskenv", args.uv, plan.task_python, plan.pytest_version)
    build = guards.prepare_build(
        Path(args.agentguard_repo), plan.agentguard_ref, state / "build", args.uv, "3.12"
    )
    recorder = None
    if plan.recorder:
        script = state / "hook_recorder.py"
        shutil.copyfile(Path(guards.__file__).with_name("hook_recorder.py"), script)
        recorder = (task_python, script)
    guard = guards.AgentGuardPlugin(build, args.codex, trust=plan.trust, recorder=recorder)
    settings = agents.CodexSettings(
        model=plan.model,
        effort=plan.effort,
        reasoning_summary=plan.reasoning_summary,
        service_tier=plan.service_tier,
        sandbox=plan.sandbox,
        network=plan.network,
        timeout_s=plan.cell_timeout_s,
    )
    agent: object = agents.CodexExecAgent(args.codex, settings)
    if getattr(args, "max_agent_runs", None):
        agent = CappedAgent(agent, args.max_agent_runs)
    runner = orchestrator.Runner(
        plan, tasks, guard, agent, run_dir, work_root, str(task_python), real_codex=True
    )

    def read_limits() -> dict | None:
        ctx = runner.contexts.get("on")
        if ctx is None:
            return None
        env = guard.base_env(ctx, ctx.codex_template)
        try:
            with appserver.AppServer(args.codex, env) as server:
                return appserver.plan_type_and_windows(server.rate_limits())
        except appserver.AppServerError:
            return None

    runner.limits_reader = read_limits
    runner.allow_partial = bool(getattr(args, "allow_partial", False))
    return runner


def _cmd_preflight(args: argparse.Namespace) -> int:
    """Everything a live run does before its first model call, and nothing after."""
    plan = Plan.load(Path(args.plan))
    run_dir = Path(args.run_dir) if args.run_dir else RESULTS / f"{plan.name}-preflight-{int(time.time())}"
    runner = _real_runner(plan, run_dir, args)
    runner.bind()
    report_data: dict = {"plan": plan.digest(), "codex_version": codex_version(args.codex)}
    if plan.codex_version and report_data["codex_version"] != plan.codex_version:
        print(f"codex {report_data['codex_version']} != pinned {plan.codex_version}")
        return 1
    runner.setup_arms()
    try:
        report_data["manipulation_checks"] = runner.manipulation_checks()
        report_data["limits"] = runner.limits_reader() if runner.limits_reader else None
        task = next(iter(runner.tasks.values()))
        for name, ctx in runner.contexts.items():
            made = suite.materialize(
                task, ctx.root / "pre" / "w", ctx.root / "pre" / "p", python=runner.task_python
            )
            home = homes.clone_codex_home(ctx.codex_template, ctx.root / "pre" / "c")
            problems, hooks = runner.guard.verify_cell(ctx, home, made.repo)
            homes.unlink_auth(home)
            report_data[f"cell_check_{name}"] = {"problems": problems, "hooks": hooks.get("hooks")}
            shutil.rmtree(ctx.root / "pre", ignore_errors=True)
            if problems:
                print(f"{name}: {problems}")
                return 1
    finally:
        runner.teardown_arms()
    (run_dir / "preflight.json").write_text(json.dumps(report_data, indent=2, default=str))
    for check in report_data["manipulation_checks"]:
        print(
            f"manipulation check {check['arm']:<8} ok: "
            f"{check['evidence']['interventions'] or check['evidence']['would_have']}"
        )
    print(f"usage windows: {report_data['limits']}")
    print(f"preflight passed; details in {run_dir / 'preflight.json'}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    if not args.confirm_live:
        print("refusing: a live run spends the ChatGPT plan's usage; pass --confirm-live")
        return 2
    plan = Plan.load(Path(args.plan))
    run_dir = Path(args.run_dir) if args.run_dir else RESULTS / plan.name
    runner = _real_runner(plan, run_dir, args)
    try:
        summary = runner.run(max_pairs=args.max_pairs)
    except orchestrator.Halt as exc:
        (run_dir / "HALTED").write_text(f"{time.ctime()}: {exc}\n")
        print(f"HALTED: {exc}")
        return 3
    print(json.dumps(summary))
    return 0


def _cmd_dry_run(args: argparse.Namespace) -> int:
    tasks = suite.load_suite(only=args.task or None)
    run_dir = Path(args.run_dir)
    if run_dir.exists() and not args.resume:
        shutil.rmtree(run_dir)
    python = os.path.abspath(args.python or scripted.default_python())
    plan = Plan(
        name=run_dir.name,
        stage="dry-run",
        seed=args.seed,
        tasks=[t.id for t in tasks],
        phrasings=list(suite.PHRASINGS),
        replicates=[int(r) for r in args.replicates.split(",")],
        model="scripted",
        effort="medium",
        suite_digest=suite.suite_digest(tasks),
    )
    work_root = Path(args.work_root) if args.work_root else run_dir / "work"
    agent = agents.ScriptedAgent(
        agents.dry_run_policy(seed=args.seed), python, model="scripted", effort="medium"
    )
    runner = orchestrator.Runner(
        plan,
        {t.id: t for t in tasks},
        guards.FakeGuard(),
        agent,
        run_dir,
        work_root,
        python,
        real_codex=False,
        log=(lambda _m: None) if args.quiet else print,
    )
    summary = runner.run(max_pairs=args.max_pairs)
    analysis = report.analyze(run_dir)
    (run_dir / "analysis.json").write_text(json.dumps(analysis, indent=2, default=str))
    (run_dir / "report.md").write_text(report.render_markdown(analysis))
    print(json.dumps(summary))
    print(report.render_markdown(analysis))
    return 0


def read_allowance(codex_bin: str) -> dict | None:
    """The plan's usage windows, read through a throwaway, isolated CODEX_HOME.

    ``account/rateLimits/read`` on ``codex app-server``: no prompt, no model call. The
    home holds only a symlink to the user's login, which is never opened here.
    """
    root = homes.private_dir(
        homes.default_work_root("allowance") / homes.neutral_name(os.getpid(), time.time())
    )
    home = homes.private_dir(root / "c")
    try:
        homes.link_auth(home)
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(root),
            "CODEX_HOME": str(home),
            "USER": os.environ.get("USER", "dev"),
            "LANG": "en_US.UTF-8",
        }
        with appserver.AppServer(codex_bin, env) as server:
            return appserver.plan_type_and_windows(server.rate_limits())
    except (appserver.AppServerError, homes.IsolationError) as exc:
        print(f"could not read usage windows: {exc}")
        return None
    finally:
        homes.unlink_auth(home)
        shutil.rmtree(root, ignore_errors=True)


def _cmd_allowance(args: argparse.Namespace) -> int:
    reading = read_allowance(args.codex)
    if reading is None:
        return 2

    def show(window: dict | None, label: str) -> str:
        if not window:
            return f"{label}: unavailable"
        resets = window.get("resets_at")
        when = time.strftime("%Y-%m-%d %H:%M %Z", time.localtime(resets)) if isinstance(resets, int) else "?"
        return f"{label}: {window.get('used_percent')}% used, resets {when}"

    print(
        f"plan: {reading.get('plan_type')}; limit reached: {reading.get('limit_reached')}; "
        f"ordinary usage allowed: {reading.get('ordinary_usage_allowed')}"
    )
    print(show(reading.get("primary"), "5-hour window"))
    print(show(reading.get("secondary"), "weekly window"))
    status = 0
    if args.plan:
        plan = Plan.load(Path(args.plan))
        run_dir = Path(args.run_dir) if args.run_dir else RESULTS / plan.name
        states = orchestrator.pair_states(
            orchestrator.load_records(run_dir / "cells.jsonl"), plan.max_attempts
        )
        remaining = sum(
            1
            for p in plan.pairs()
            if not states.get(p.id, orchestrator.PairState()).complete
            and not states.get(p.id, orchestrator.PairState()).excluded
        )
        verdict = limits.feasibility(reading, 2 * remaining, plan.budget_policy())
        print(f"plan {plan.name}: {verdict.reason}")
        status = 0 if verdict.ok else 1
    if args.json:
        print(json.dumps(reading, indent=2))
    return status


def _cmd_analyze(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    analysis = report.analyze(run_dir)
    out_json = Path(args.json) if args.json else run_dir / "analysis.json"
    out_md = Path(args.markdown) if args.markdown else run_dir / "report.md"
    out_json.write_text(json.dumps(analysis, indent=2, default=str))
    out_md.write_text(report.render_markdown(analysis))
    print(report.render_markdown(analysis))
    return 0


# -- parser -----------------------------------------------------------------------


def _live_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--plan", required=True)
    p.add_argument("--run-dir")
    p.add_argument("--work-root", help="Neutral directory outside /tmp for homes and cell repos.")
    p.add_argument("--codex", default=DEFAULT_CODEX)
    p.add_argument("--uv", default=DEFAULT_UV)
    p.add_argument(
        "--agentguard-repo",
        default=str(suite.REPO_ROOT),
        help="Git repository the build under test is exported from.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m agentguard.bench.codex")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="List the task suite.")
    p.add_argument("--task", action="append")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("validate", help="Prove every grader on noop/honest/planted solutions.")
    p.add_argument("--task", action="append")
    p.add_argument("--python", help="Interpreter with pytest for the task code.")
    p.add_argument("--json")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("plan", help="Write a run plan (pre-registration input).")
    p.add_argument("--name", required=True)
    p.add_argument("--stage", default="main", choices=["pilot", "main", "smoke"])
    p.add_argument("--seed", type=int, default=20261105)
    p.add_argument("--task", action="append")
    p.add_argument("--phrasing", action="append", choices=list(suite.PHRASINGS))
    p.add_argument("--replicates", default="1,2,3")
    p.add_argument("--model", default="gpt-6-luna")
    p.add_argument("--effort", default="medium")
    p.add_argument("--agentguard-ref", default="HEAD")
    p.add_argument("--trust", default="app-server", choices=["app-server", "bypass"])
    p.add_argument("--cell-timeout", type=int, default=1200)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--stop-weekly-at", type=float, help="Override the weekly stop line (smoke plans only).")
    p.add_argument("--codex", default=DEFAULT_CODEX)
    p.add_argument("--notes")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_plan)

    p = sub.add_parser("preflight", help="Build, install, trust, attest both arms; no model call.")
    _live_options(p)
    p.set_defaults(func=_cmd_preflight)

    for name in ("run", "smoke"):
        p = sub.add_parser(
            name, help="Live run (spends plan usage)." if name == "run" else "A capped live run."
        )
        _live_options(p)
        p.add_argument("--max-pairs", type=int, default=None if name == "run" else 1)
        p.add_argument("--confirm-live", action="store_true")
        p.add_argument(
            "--allow-partial",
            action="store_true",
            help="Start even if the weekly allowance cannot finish the plan (stops at the weekly line).",
        )
        p.add_argument(
            "--max-agent-runs",
            type=int,
            default=None if name == "run" else 2,
            help="Hard cap on live codex exec invocations in this session.",
        )
        p.set_defaults(func=_cmd_run)

    p = sub.add_parser("dry-run", help="The whole pipeline with a scripted agent and a fake guard.")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--work-root")
    p.add_argument("--task", action="append")
    p.add_argument("--replicates", default="1")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--python")
    p.add_argument("--max-pairs", type=int)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=_cmd_dry_run)

    p = sub.add_parser("allowance", help="Read the ChatGPT plan's Codex usage windows (no model call).")
    p.add_argument("--codex", default=DEFAULT_CODEX)
    p.add_argument("--plan", help="Also check whether this plan's remaining cells fit the weekly window.")
    p.add_argument("--run-dir")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_allowance)

    p = sub.add_parser("analyze", help="Pre-registered analysis of a run directory.")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--json")
    p.add_argument("--markdown")
    p.set_defaults(func=_cmd_analyze)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
