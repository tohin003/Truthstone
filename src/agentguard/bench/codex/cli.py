"""``python -m agentguard.bench.codex <command>``.

Model-free: ``list``, ``validate``, ``plan``, ``preflight``, ``dry-run``, ``analyze``.
Live (spends the ChatGPT plan's usage; requires ``--confirm-live``): ``run``, ``smoke``.
"""

from __future__ import annotations

import argparse
import dataclasses
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
    claude,
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
DEFAULT_CLAUDE = claude.default_claude_bin()
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
    host_fields: dict = {}
    if args.host == "claude":
        accounts = [a.strip() for a in (args.accounts or "work,personal").split(",") if a.strip()]
        unknown = sorted(set(accounts) - set(claude.ACCOUNTS))
        if unknown:
            print(f"unknown account(s) {unknown}; known: {sorted(claude.ACCOUNTS)}")
            return 2
        policy = claude.AccountPolicy(
            per_cell_session=args.per_cell_session or 0.0, per_cell_week=args.per_cell_week or 0.0
        )
        host_fields = {
            "host": "claude",
            "accounts": accounts,
            "permission_mode": args.permission_mode,
            "codex_version": claude.claude_version(args.claude),  # the host CLI's version
            "trust": "session-plugin-dir",
            "sandbox": "none",
            "network": True,
            "reasoning_summary": "n/a",
            "service_tier": "n/a",
            "budget": dataclasses.asdict(policy),
        }
    else:
        host_fields = {"codex_version": codex_version(args.codex), "trust": args.trust}
    default_model = "claude-opus-5-5" if args.host == "claude" else "gpt-6-luna"
    plan = Plan(
        name=args.name,
        stage=args.stage,
        seed=args.seed,
        tasks=[t.id for t in tasks],
        phrasings=list(args.phrasing or suite.PHRASINGS),
        replicates=[int(r) for r in args.replicates.split(",")],
        model=args.model or default_model,
        effort=args.effort,
        agentguard_ref=args.agentguard_ref,
        cell_timeout_s=args.cell_timeout,
        max_attempts=args.max_attempts,
        suite_digest=suite.suite_digest(tasks),
        notes=args.notes or "",
        **host_fields,
    )
    if args.host == "codex" and args.stop_weekly_at is not None:
        plan.budget["stop_weekly_at"] = args.stop_weekly_at
    if args.host == "codex" and args.weekly_percent_per_cell is not None:
        plan.budget["weekly_percent_per_cell"] = args.weekly_percent_per_cell
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


def freeze_tree(root: Path) -> None:
    """Read-only for everyone: no cell can install into the shared task interpreter."""
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        os.chmod(path, mode & ~0o222)


def thaw_tree(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        if not path.is_symlink():
            os.chmod(path, path.stat().st_mode | 0o200)


def _claude_runner(plan: Plan, run_dir: Path, args: argparse.Namespace) -> orchestrator.Runner:
    """Claude Code cells: ``claude -p`` in scratch repos outside the user's home."""
    tasks = {t.id: t for t in suite.load_suite(only=plan.tasks)}
    work_root = Path(args.work_root).expanduser() if args.work_root else homes.default_work_root(plan.name)
    homes.assert_outside_tmp(work_root)
    homes.assert_outside_tmp(run_dir)
    state = homes.private_dir(work_root / "state")
    taskenv = state / "taskenv"
    if taskenv.exists():
        thaw_tree(taskenv)
    task_python = homes.make_task_env(taskenv, args.uv, plan.task_python, plan.pytest_version)
    freeze_tree(taskenv)
    build = guards.prepare_build(
        Path(args.agentguard_repo), plan.agentguard_ref, state / "build", args.uv, "3.12"
    )
    recorder = None
    if plan.recorder:
        script = state / "hook_recorder.py"
        shutil.copyfile(Path(guards.__file__).with_name("hook_recorder.py"), script)
        recorder = (task_python, script)
    claude_bin = claude.pin_claude_bin(args.claude, state / "claude-bin")
    version = claude.claude_version(claude_bin)
    if plan.codex_version and version != plan.codex_version:
        raise orchestrator.Halt(f"Claude Code {version} != pinned {plan.codex_version}")
    guard = claude.AgentGuardClaudePlugin.from_build(build, state, claude_bin, args.uv, recorder)
    unknown = sorted(set(plan.accounts) - set(guard.accounts))
    if unknown:
        raise orchestrator.Halt(f"unknown account(s) {unknown}")
    settings = claude.ClaudeSettings(
        model=plan.model,
        effort=plan.effort,
        permission_mode=plan.permission_mode,
        timeout_s=plan.cell_timeout_s,
    )
    agent: object = claude.ClaudeExecAgent(claude_bin, settings)
    if getattr(args, "max_agent_runs", None):
        agent = CappedAgent(agent, args.max_agent_runs)
    # Outside /Users entirely: no ancestor CLAUDE.md of the user's applies to a cell.
    cell_root = homes.private_dir(Path("/private/tmp") / homes.neutral_name("cells", plan.name, os.getuid()))
    runner = orchestrator.Runner(
        plan,
        tasks,
        guard,
        agent,
        run_dir,
        work_root,
        str(task_python),
        real_codex=True,
        cell_root=cell_root,
        account_reader=lambda account: claude.read_usage(claude_bin, guard.accounts[account]),
        account_policy=plan.account_policy(),
    )
    runner.allow_partial = bool(getattr(args, "allow_partial", False))
    return runner


def _real_runner(plan: Plan, run_dir: Path, args: argparse.Namespace) -> orchestrator.Runner:
    if plan.host == "claude":
        return _claude_runner(plan, run_dir, args)
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


def _claude_preflight(plan: Plan, run_dir: Path, args: argparse.Namespace) -> int:
    """Provision the build's runtime per account, read /usage, and run the manipulation
    checks (synthetic payloads through the plugin's own hooks). No prompt reaches a model."""
    runner = _real_runner(plan, run_dir, args)
    runner.bind()
    data: dict = {"plan": plan.digest(), "claude_version": plan.codex_version, "accounts": plan.accounts}
    runner.setup_arms()  # provisions each account's plugin runtime (``claude -p /usage``)
    try:
        runner._refresh_usage(force=True)
        data["usage"] = runner.account_readings
        data["account_choice"] = dataclasses.asdict(runner._choose_account())
        data["manipulation_checks"] = runner.manipulation_checks()
        for name, ctx in runner.contexts.items():
            health = runner.guard.health(ctx)
            data[f"daemon_{name}"] = health
            if not health or bool(health.get("observing")) != ctx.arm.observe_only:
                print(f"{name}: daemon health {health}")
                return 1
    finally:
        runner.teardown_arms()
    (run_dir / "preflight.json").write_text(json.dumps(data, indent=2, default=str))
    for check in data["manipulation_checks"]:
        print(
            f"manipulation check {check['arm']:<8} {check['account']:<9} ok: "
            f"{check['evidence']['interventions'] or check['evidence']['would_have']}"
        )
    for account, reading in data["usage"].items():
        print(f"{account}: {_usage_line(reading)}")
    print(f"next pair would run on: {data['account_choice']['account']} ({data['account_choice']['reason']})")
    print(f"preflight passed; details in {run_dir / 'preflight.json'}")
    return 0


def _usage_line(reading: dict | None) -> str:
    if not reading:
        return "unavailable"

    def one(window: dict | None) -> str:
        window = window or {}
        resets = window.get("resets_at")
        when = (
            time.strftime("%b %d %H:%M", time.localtime(resets)) if isinstance(resets, (int, float)) else "?"
        )
        return f"{window.get('used_percent')}% (resets {when})"

    return f"5-hour {one(reading.get('session'))}; week {one(reading.get('week'))}"


def _cmd_claude_usage(args: argparse.Namespace) -> int:
    """Both accounts' windows via ``claude -p /usage`` (no model call), and the choice the
    runner would make under the pre-registered account policy."""
    policy = Plan.load(Path(args.plan)).account_policy() if args.plan else claude.AccountPolicy()
    readings = {name: claude.read_usage(args.claude, path) for name, path in claude.ACCOUNTS.items()}
    for name, reading in readings.items():
        allowed, why = claude.cell_allowed(name, reading, policy, cells=2)
        print(f"{name:<9} {_usage_line(reading)}  -> {'eligible' if allowed else 'not eligible'}: {why}")
    choice = claude.choose_account(readings, policy)
    print(f"choice: {choice.account} ({choice.reason}){f'; wait {choice.wait_s}s' if choice.wait_s else ''}")
    if args.json:
        print(json.dumps(readings, indent=2, default=str))
    return 0 if choice.account else 1


def _cmd_preflight(args: argparse.Namespace) -> int:
    """Everything a live run does before its first model call, and nothing after."""
    plan = Plan.load(Path(args.plan))
    run_dir = Path(args.run_dir) if args.run_dir else RESULTS / f"{plan.name}-preflight-{int(time.time())}"
    if plan.host == "claude":
        return _claude_preflight(plan, run_dir, args)
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
        print("refusing: a live run spends subscription usage; pass --confirm-live")
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
    host_fields: dict = {}
    fake = None
    if args.host == "claude":
        # Simulated accounts that start near their caps, so one dry run exercises the
        # 98% rule, the personal reserve, a wait for a 5-hour reset and a mid-cell 429.
        policy = claude.AccountPolicy(per_cell_session=1.5, per_cell_week=0.25)
        host_fields = {
            "host": "claude",
            "accounts": ["work", "personal"],
            "budget": dataclasses.asdict(policy),
        }
        fake = claude.FakeAccounts(
            {"work": (90.0, 30.0), "personal": (60.0, 40.0)}, per_cell=1.5, per_cell_week=0.25
        )
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
        **host_fields,
    )
    work_root = Path(args.work_root) if args.work_root else run_dir / "work"
    interrupt = {plan.schedule()[2][0].id} if fake is not None and len(plan.schedule()) > 2 else set()
    agent = agents.ScriptedAgent(
        agents.dry_run_policy(seed=args.seed),
        python,
        model="scripted",
        effort="medium",
        host=args.host,
        accounts=fake,
        interrupt=interrupt,
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
    if fake is not None:
        runner.account_reader = fake.read
        runner.account_policy = plan.account_policy()
        runner.sleep = fake.sleep
    summary = runner.run(max_pairs=args.max_pairs)
    if fake is not None:
        summary["accounts"] = {
            "cells": fake.cells,
            "simulated_wait_s": fake.waited_s,
            "window_resets": fake.resets,
        }
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
    p.add_argument(
        "--claude", default=DEFAULT_CLAUDE, help="Claude Code binary (copied and pinned per study)."
    )
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
    p.add_argument("--host", default="codex", choices=["codex", "claude"])
    p.add_argument("--model", help="Default: gpt-6-luna (codex), claude-opus-5-5 (claude).")
    p.add_argument("--effort", default="medium")
    p.add_argument("--accounts", help="Claude: comma-separated accounts the plan may use (work,personal).")
    p.add_argument(
        "--permission-mode", default="bypassPermissions", help="Claude: --permission-mode for cells."
    )
    p.add_argument("--per-cell-session", type=float, help="Claude: measured 5-hour points per cell (smoke).")
    p.add_argument("--per-cell-week", type=float, help="Claude: measured weekly points per cell (smoke).")
    p.add_argument("--claude", default=DEFAULT_CLAUDE)
    p.add_argument("--agentguard-ref", default="HEAD")
    p.add_argument("--trust", default="app-server", choices=["app-server", "bypass"])
    p.add_argument("--cell-timeout", type=int, default=1200)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--stop-weekly-at", type=float, help="Override the weekly stop line (smoke plans only).")
    p.add_argument(
        "--weekly-percent-per-cell",
        type=float,
        help="Measured weekly usage per cell (from the pilot), for the allowance pre-check.",
    )
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
    p.add_argument("--host", default="codex", choices=["codex", "claude"])
    p.set_defaults(func=_cmd_dry_run)

    p = sub.add_parser("claude-usage", help="Both Claude accounts' usage windows via /usage (no model call).")
    p.add_argument("--claude", default=DEFAULT_CLAUDE)
    p.add_argument("--plan", help="Apply this Claude plan's account policy.")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_claude_usage)

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
