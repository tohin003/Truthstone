"""``python -m truthstone.bench.codex <command>``.

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
from typing import Any

from truthstone.bench.codex import (
    agents,
    appserver,
    claude,
    claude_sandbox,
    guards,
    homes,
    limits,
    orchestrator,
    report,
    scripted,
    suite,
    toolchain,
)
from truthstone.bench.codex.plan import Plan

DEFAULT_CODEX = shutil.which("codex") or str(Path.home() / ".local" / "bin" / "codex")
DEFAULT_CLAUDE = claude.default_claude_bin()
DEFAULT_UV = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
RESULTS = suite.BENCH_ROOT / "results"


# -- model-free commands ----------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> int:
    tasks = suite.load_suite(only=args.task or None, suite=args.suite)
    for task in tasks:
        print(
            f"{task.id:<40}{task.set:<11}{task.family:<24}{task.language[:2]:<4}"
            f"{','.join(task.opportunity.mechanisms)}"
        )
    counts = {s: sum(1 for t in tasks if t.set == s) for s in suite.SETS}
    name = suite.suite_spec(args.suite).name
    print(f"\n{name}: {len(tasks)} task(s) {counts}; suite digest {suite.suite_digest(tasks)}")
    return 0


def _node_for(tasks: list[suite.Task], explicit: str | None) -> str | None:
    """The Node to grade (and run) TypeScript tasks with; None when no task needs it."""
    if not any(t.language == "typescript" for t in tasks):
        return None
    return os.path.abspath(explicit or toolchain.default_node())


def _cmd_validate(args: argparse.Namespace) -> int:
    tasks = suite.load_suite(only=args.task or None, suite=args.suite)
    try:
        # Ignored content is refused always; content not committed yet only while drafting.
        suite.assert_committed(tasks, allow_untracked=args.allow_untracked)
    except suite.SuiteError as exc:
        print(f"refusing to validate: {exc}")
        return 2
    # absolute, but not resolved: resolving a venv's python symlink would leave the venv
    python = os.path.abspath(args.python or scripted.default_python())
    node = _node_for(tasks, args.node)
    failures = 0
    rows = []
    for task in tasks:
        result = scripted.validate_task(task, python, node=node)
        for v in result.variants:
            flag = "ok " if v.ok else "BAD"
            detail = (v.problem or ", ".join(v.reasons))[:90]
            print(f"{flag} {task.id:<42}{v.variant:<8}{v.outcome:<18}{detail}")
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
    name = suite.suite_spec(args.suite).name
    print(f"\n{len(tasks) - failures}/{len(tasks)} task(s) validated; suite {name}")
    return 1 if failures else 0


def codex_version(codex_bin: str) -> str:
    out = subprocess.run([codex_bin, "--version"], capture_output=True, text=True, timeout=30).stdout
    match = re.search(r"(\d+\.\d+\.\d+)", out)
    return match.group(1) if match else out.strip()


def _shard(text: str) -> list[int]:
    """'K/N' or 'K1,K2,.../N' -> [K1, ..., N] (Plan.pair_shard)."""
    residues, _, n = text.partition("/")
    return [*sorted(int(k) for k in residues.split(",")), int(n)]


def _cmd_plan(args: argparse.Namespace) -> int:
    tasks = suite.load_suite(only=args.task or None, suite=args.suite)
    dropped = [t.id for t in tasks if t.id in suite.DROPPED]
    if dropped and args.task:
        print(f"refusing to register dropped task(s): {[f'{t}: {suite.DROPPED[t]}' for t in dropped]}")
        return 2
    tasks = [t for t in tasks if t.id not in suite.DROPPED]
    try:
        suite.assert_committed(tasks)  # a registration must equal any clean checkout
    except suite.SuiteError as exc:
        print(f"refusing to register: {exc}")
        return 2
    frozen = suite.FROZEN.get(suite.suite_spec(args.suite).name) if args.suite else None
    if frozen and suite.suite_digest(tasks) != frozen:
        print(
            f"refusing to register: {args.suite} is frozen at {frozen[:16]}... (amendment G11); "
            f"these tasks digest to {suite.suite_digest(tasks)[:16]}... (every task, unchanged)"
        )
        return 2
    common: dict = {}
    node = _node_for(tasks, args.node)
    if node is not None:
        common["node_version"] = toolchain.node_version(node)
    if args.suite and args.suite != suite.DEFAULT_SUITE:
        common["suite"] = suite.suite_spec(args.suite).name
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
            "permission_mode": args.permission_mode or claude.DEFAULT_PERMISSION_MODE,
            "allowed_tools": [
                t for t in (args.allowed_tools or ",".join(claude.DEFAULT_ALLOWED_TOOLS)).split(",") if t
            ],
            "codex_version": claude.claude_version(args.claude),  # the host CLI's version
            "trust": "session-plugin-dir",
            # Every cell's Bash runs in Claude Code's own sandbox: writes confined to the
            # cell, no network (claude_sandbox.py, proven by `sandbox-check`).
            "sandbox": "claude-bash-sandbox",
            "network": False,
            "sandbox_profile": claude_sandbox.PROFILE,
            "reasoning_summary": "n/a",
            "service_tier": "n/a",
            "budget": dataclasses.asdict(policy),
        }
    else:
        host_fields = {"codex_version": codex_version(args.codex), "trust": args.trust}
        if args.accounts:
            from truthstone.bench.codex import accounts as codex_accounts

            names = [a.strip() for a in args.accounts.split(",") if a.strip()]
            unknown = sorted(set(names) - set(codex_accounts.ACCOUNTS))
            if unknown:
                print(f"unknown Codex account(s) {unknown}; known: {sorted(codex_accounts.ACCOUNTS)}")
                return 2
            stops = dict(codex_accounts.CodexAccountPolicy().week_stop)
            for item in args.week_stop or []:  # G21: a plan may move an account's weekly stop line
                name, _, pct = item.partition("=")
                if name.strip() not in codex_accounts.ACCOUNTS or not pct:
                    known = sorted(codex_accounts.ACCOUNTS)
                    print(f"bad --week-stop {item!r}: use ACCOUNT=PERCENT, ACCOUNT in {known}")
                    return 2
                stops[name.strip()] = float(pct)
            policy = codex_accounts.CodexAccountPolicy(
                per_cell_week=args.weekly_percent_per_cell or 0.1,
                per_cell_primary=args.per_cell_session or 0.55,
                week_stop=stops,
            )
            host_fields.update({"accounts": names, "budget": dataclasses.asdict(policy)})
    default_model = "claude-opus-5-5" if args.host == "claude" else "gpt-6.1-sol"  # amendment A5
    plan = Plan(
        name=args.name,
        stage=args.stage,
        seed=args.seed,
        tasks=[t.id for t in tasks],
        phrasings=list(args.phrasing or suite.PHRASINGS),
        replicates=[int(r) for r in args.replicates.split(",")],
        model=args.model or default_model,
        effort=args.effort,
        truthstone_ref=args.truthstone_ref,
        cell_timeout_s=args.cell_timeout,
        max_attempts=args.max_attempts,
        suite_digest=suite.suite_digest(tasks),
        notes=args.notes or "",
        arms=ARM_CHOICES[args.arms],
        observe_plugin=args.observe_plugin,
        pair_shard=_shard(args.shard) if args.shard else [],
        **common,
        **host_fields,
    )
    if args.host == "codex" and not plan.accounts and args.stop_weekly_at is not None:
        plan.budget["stop_weekly_at"] = args.stop_weekly_at
    if args.host == "codex" and not plan.accounts and args.weekly_percent_per_cell is not None:
        plan.budget["weekly_percent_per_cell"] = args.weekly_percent_per_cell
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    plan.save(out)
    unit = "observe-only screening cells" if plan.screening else "cells"
    print(
        f"plan {plan.name}: {len(plan.pairs())} pairs = {len(plan.arms) * len(plan.pairs())} {unit}; "
        f"suite {plan.suite} {plan.suite_digest[:16]}; observe arm: {plan.observe_variant} plugin; "
        f"digest {plan.digest()[:16]}"
    )
    return 0


# `--arms`: both arms (the paired study), or the observe arm alone (a screening pilot).
ARM_CHOICES = {"both": ["on", "observe"], "observe": ["observe"], "on": ["on"]}


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


def _plan_tasks(plan: Plan, args: argparse.Namespace) -> dict[str, suite.Task]:
    """The plan's tasks, from the plan's own suite (``--suite`` may only confirm it)."""
    given = getattr(args, "suite", None)
    if given and suite.suite_spec(given).name != plan.suite:
        raise orchestrator.Halt(f"--suite {given} disagrees with the plan's suite {plan.suite!r}")
    return {t.id: t for t in suite.load_suite(only=plan.tasks, suite=plan.suite)}


def _toolchain(plan: Plan, state: Path, args: argparse.Namespace) -> tuple[str | None, Path | None]:
    """The pinned Node and its private bin, when the plan has TypeScript tasks."""
    if not plan.node_version:
        return None, None
    node = os.path.abspath(getattr(args, "node", None) or toolchain.default_node())
    try:
        bin_dir = toolchain.make_toolchain(state / "toolchain", node, pinned=plan.node_version)
    except toolchain.ToolchainError as exc:
        raise orchestrator.Halt(str(exc)) from exc
    return str(bin_dir / "node"), bin_dir


def _claude_runner(plan: Plan, run_dir: Path, args: argparse.Namespace) -> orchestrator.Runner:
    """Claude Code cells: ``claude -p`` in scratch repos outside the user's home, each one's
    Bash in Claude Code's sandbox and its file tools confined to the cell."""
    if plan.sandbox_profile != claude_sandbox.PROFILE:
        raise orchestrator.Halt(
            f"the plan's Claude sandbox profile {plan.sandbox_profile!r} is not this harness's "
            f"{claude_sandbox.PROFILE!r}: re-make the plan (every Claude cell must run sandboxed)"
        )
    bare = claude_sandbox.bare_file_tools(plan.allowed_tools)
    if bare:
        raise orchestrator.Halt(f"the plan allows {bare} bare, which would let them write anywhere")
    tasks = _plan_tasks(plan, args)
    work_root = Path(args.work_root).expanduser() if args.work_root else homes.default_work_root(plan.name)
    homes.assert_outside_tmp(work_root)
    homes.assert_outside_tmp(run_dir)
    state = homes.private_dir(work_root / "state")
    task_node, toolchain_bin = _toolchain(plan, state, args)
    taskenv = state / "taskenv"
    if taskenv.exists():
        thaw_tree(taskenv)
    task_python = homes.make_task_env(taskenv, args.uv, plan.task_python, plan.pytest_version)
    freeze_tree(taskenv)
    build = guards.prepare_build(
        Path(args.truthstone_repo), plan.truthstone_ref, state / "build", args.uv, "3.12"
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
    guard = claude.TruthstoneClaudePlugin.from_build(
        build,
        state,
        claude_bin,
        args.uv,
        recorder,
        permission_mode=plan.permission_mode,
        observe_plugin=plan.observe_variant,
    )
    unknown = sorted(set(plan.accounts) - set(guard.accounts))
    if unknown:
        raise orchestrator.Halt(f"unknown account(s) {unknown}")
    # Hidden from every cell: the checkout (hidden tests), the run directory and the work
    # root (both arms' homes), and credentials. Re-opened: the task interpreter and Node.
    readable = [taskenv, *([toolchain_bin.parent] if toolchain_bin is not None else [])]
    sandbox_paths = claude_sandbox.SandboxPaths.for_study(suite.REPO_ROOT, run_dir, work_root, readable)
    settings = claude.ClaudeSettings(
        model=plan.model,
        effort=plan.effort,
        permission_mode=plan.permission_mode,
        timeout_s=plan.cell_timeout_s,
        allowed_tools=tuple(plan.allowed_tools),
        sandbox=sandbox_paths,
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
        task_node=task_node,
        toolchain_bin=toolchain_bin,
    )
    runner.allow_partial = bool(getattr(args, "allow_partial", False))
    return runner


def limits_context(contexts: dict) -> object | None:
    """The arm whose Codex home reads the plan's usage windows. Any prepared arm will do (the
    account is the same); an observe-only screening plan has no "on" arm at all."""
    return contexts.get("on") or next(iter(contexts.values()), None)


def _real_runner(plan: Plan, run_dir: Path, args: argparse.Namespace) -> orchestrator.Runner:
    if plan.host == "claude":
        return _claude_runner(plan, run_dir, args)
    tasks = _plan_tasks(plan, args)
    work_root = Path(args.work_root).expanduser() if args.work_root else homes.default_work_root(plan.name)
    homes.assert_outside_tmp(work_root)
    homes.assert_outside_tmp(run_dir)
    state = homes.private_dir(work_root / "state")
    task_node, toolchain_bin = _toolchain(plan, state, args)
    task_python = homes.make_task_env(state / "taskenv", args.uv, plan.task_python, plan.pytest_version)
    build = guards.prepare_build(
        Path(args.truthstone_repo), plan.truthstone_ref, state / "build", args.uv, "3.12"
    )
    recorder = None
    if plan.recorder:
        script = state / "hook_recorder.py"
        shutil.copyfile(Path(guards.__file__).with_name("hook_recorder.py"), script)
        recorder = (task_python, script)
    timer = guards.build_hook_timer(state)  # G9: every hook's wall time, spawn to exit (T6)
    if timer is None:
        print("no C compiler: hooks run untimed, so T6 (end to end) will read as not measured")
    guard = guards.TruthstonePlugin(
        build,
        args.codex,
        trust=plan.trust,
        recorder=recorder,
        observe_plugin=plan.observe_variant,
        hook_timer=timer,
    )
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
        plan,
        tasks,
        guard,
        agent,
        run_dir,
        work_root,
        str(task_python),
        real_codex=True,
        task_node=task_node,
        toolchain_bin=toolchain_bin,
    )

    def read_limits() -> dict | None:
        ctx = limits_context(runner.contexts)
        if ctx is None:
            return None
        env = guard.base_env(ctx, ctx.codex_template)
        # A transient app-server failure must not refuse a whole study at its start: retry,
        # and say what failed (an unreadable window still stops the run, as registered).
        for attempt in range(3):
            try:
                with appserver.AppServer(args.codex, env) as server:
                    return appserver.plan_type_and_windows(server.rate_limits())
            except appserver.AppServerError as exc:
                runner.log(f"usage windows unreadable (attempt {attempt + 1} of 3): {exc}")
                time.sleep(2 * (attempt + 1))
        return None

    runner.limits_reader = read_limits
    if plan.accounts:
        # Amendment G5: each pair on one of the plan's accounts, chosen on their windows.
        from truthstone.bench.codex import accounts as codex_accounts

        runner.account_policy = plan.account_policy()
        runner.account_reader = lambda account: codex_accounts.read_windows(
            args.codex, codex_accounts.account_home(state, account)
        )
    runner.allow_partial = bool(getattr(args, "allow_partial", False))
    return runner


def _study_cues(plan: Plan, run_dir: Path, task: suite.Task) -> tuple[str, ...]:
    """The study's own names: never in what any arm's model is given (paths that carry them
    would tell the model it is being studied, and which task it is)."""
    return (plan.name, run_dir.name, str(suite.REPO_ROOT), "bench/codex", "/cells/", task.id)


def _visible_problems(
    plan: Plan, ctx: guards.ArmContext, mentions: list[str], cues: list[str] | None = None
) -> list[str]:
    """Amendment G1: under a skill-free plan the observe arm's model is never shown the product.
    The guarded arm is (its skill is part of the treatment); plans before G1 show it in both.
    The study's own names are never shown to either arm."""
    problems = []
    if ctx.arm.observe_only and mentions and plan.skill_free_observe:
        problems.append(
            f"the observe arm's model would be shown the product ({len(mentions)} mention(s)): "
            f"{mentions[0][:200]}"
        )
    if cues:
        problems.append(f"the {ctx.arm.name} arm's model would be shown the study's names: {cues[0][:200]}")
    return problems


def _visible_line(plan: Plan, ctx: guards.ArmContext, count: int) -> str:
    line = f"model-visible context {ctx.arm.name:<8} {count} product mention(s)"
    if not ctx.arm.observe_only:
        return f"{line} (the guarded arm's own plugin)"
    if count and not plan.skill_free_observe:
        return f"{line}: WARNING, a plan from before amendment G1 (the full plugin in the observe arm)"
    return line


def _claude_preflight(plan: Plan, run_dir: Path, args: argparse.Namespace) -> int:
    """Provision the build's runtime per account, read /usage, and run the manipulation
    checks (synthetic payloads through the plugin's own hooks). No prompt reaches a model."""
    runner = _real_runner(plan, run_dir, args)
    runner.bind()
    data: dict = {"plan": plan.digest(), "claude_version": plan.codex_version, "accounts": plan.accounts}
    # The cells' sandbox, proven with the pinned binary and the plan's flags: no model call.
    agent = runner.agent.inner if isinstance(runner.agent, CappedAgent) else runner.agent
    sandbox = claude_sandbox.check(
        agent.claude_bin,
        runner.work_root,
        model=plan.model,
        permission_mode=plan.permission_mode,
        allowed_tools=tuple(plan.allowed_tools),
    )
    data["sandbox_check"] = dataclasses.asdict(sandbox)
    _print_sandbox(sandbox)
    if not sandbox.ok:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "preflight.json").write_text(json.dumps(data, indent=2, default=str))
        return 1
    runner.setup_arms()  # provisions each account's plugin runtime (``claude -p /usage``)
    try:
        runner._refresh_usage(force=True)
        data["usage"] = runner.account_readings
        data["account_choice"] = dataclasses.asdict(runner._choose_account())
        data["manipulation_checks"] = runner.manipulation_checks()
        task = next(iter(runner.tasks.values()))
        for name, ctx in runner.contexts.items():
            health = runner.guard.health(ctx)
            data[f"daemon_{name}"] = health
            if not health or bool(health.get("observing")) != ctx.arm.observe_only:
                print(f"{name}: daemon health {health}")
                return 1
            # Amendment G1: what this arm's model would be given (system prompt, tool and
            # skill listings, first message), captured from the real binary with no model.
            where = homes.private_dir(
                (runner.cell_root or runner.work_root) / homes.neutral_name("visible", name, time.time())
            )
            made = suite.materialize(
                task, where / "w", where / "p", python=runner.task_python, instructions=runner.instructions
            )
            try:
                seen = claude_sandbox.visible_context(
                    agent.claude_bin,
                    runner.work_root,
                    runner.guard.exec_args(ctx),
                    agent.settings.sandbox,
                    task.prompt(plan.phrasings[0]),
                    model=plan.model,
                    effort=plan.effort,
                    permission_mode=plan.permission_mode,
                    allowed_tools=tuple(plan.allowed_tools),
                    repo=made.repo,
                    cues=_study_cues(plan, run_dir, task),
                )
            finally:
                shutil.rmtree(where, ignore_errors=True)
            data[f"visible_context_{name}"] = dataclasses.asdict(seen)
            mentions = seen.mentions + seen.init_mentions
            problems = seen.problems + _visible_problems(plan, ctx, mentions, seen.cue_mentions)
            if seen.user_memory_visible:
                problems.append("the account's own CLAUDE.md would reach the model: user memory is loaded")
            print(_visible_line(plan, ctx, len(mentions)))
            if problems:
                print(f"{name}: {problems}")
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


def _print_sandbox(result: claude_sandbox.CheckResult) -> None:
    label = "sandboxed" if result.sandboxed else "negative control (no sandbox)"
    status = "ok" if result.ok else "FAILED"
    print(
        f"claude sandbox check [{label}] {status}: profile {result.profile}, "
        f"Claude Code {result.claude_version}"
    )
    obs = result.observations
    for probe in obs.get("probes", []):
        print(f"  {probe}")
    print(f"  files: {obs.get('files')}")
    print(
        f"  Read of a hidden path refused: {obs.get('read_hidden_refused')}; hooks reached loopback: "
        f"{obs.get('hooks_seen')}"
    )
    for problem in result.problems:
        print(f"  problem: {problem}")


def _cmd_sandbox_check(args: argparse.Namespace) -> int:
    """Prove the cells' sandbox with no model call (see claude_sandbox.check / codex_probe)."""
    work_root = homes.private_dir(homes.default_work_root("sandbox-check"))
    report_data: dict = {}
    status = 0
    if args.host in ("claude", "both"):
        claude_bin = claude.pin_claude_bin(args.claude, work_root / "claude-bin")
        result = claude_sandbox.check(claude_bin, work_root, model=args.model)
        _print_sandbox(result)
        report_data["claude"] = dataclasses.asdict(result)
        status |= 0 if result.ok else 1
        if args.control:
            control = claude_sandbox.check(claude_bin, work_root, model=args.model, sandboxed=False)
            _print_sandbox(control)
            report_data["claude_control"] = dataclasses.asdict(control)
            status |= 0 if control.ok else 1
    if args.host in ("codex", "both"):
        codex = agents.codex_sandbox_probe(args.codex, work_root)
        print(
            f"codex sandbox probe ({codex['profile']}) {'ok' if codex['ok'] else 'FAILED'}: {codex['probes']}"
        )
        for problem in codex["problems"]:
            print(f"  problem: {problem}")
        report_data["codex"] = codex
        status |= 0 if codex["ok"] else 1
    if args.json:
        Path(args.json).write_text(json.dumps(report_data, indent=2, default=str), encoding="utf-8")
    return status


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


def _cmd_leakage(args: argparse.Namespace) -> int:
    """The no-leakage lint's hashed list of golden task ids and task-unique strings."""
    from truthstone.bench.codex import leakage

    data = leakage.write() if args.write else leakage.build()
    where = f"written to {leakage.LIST_PATH}" if args.write else "not written (use --write)"
    print(f"{len(data['ids'])} task ids and {len(data['strings'])} task-unique strings, hashed; {where}")
    overlap = data.get("_overlap_with_product_code") or []
    if overlap:
        # For the builder's review only: each is a lint failure, a leak until shown generic.
        print(f"already in product code, the lint will flag ({len(overlap)}): {', '.join(overlap)}")
    return 0


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
    # G5: both Codex logins answer (app-server, no model call); the plan's own must.
    accounts_report = _codex_accounts_report(args.codex, plan.account_policy() if plan.accounts else None)
    report_data["accounts"] = accounts_report
    _print_accounts(accounts_report)
    needed = plan.accounts or ["main"]
    dead = [a for a in needed if accounts_report["accounts"][a]["reading"] is None]
    if dead:
        print(f"the plan's Codex account(s) {dead} did not answer: check `codex login` for them")
        return 1
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
                task,
                ctx.root / "pre" / "w",
                ctx.root / "pre" / "p",
                python=runner.task_python,
                instructions=runner.instructions,
            )
            home = homes.clone_codex_home(ctx.codex_template, ctx.root / "pre" / "c")
            try:
                problems, hooks = runner.guard.verify_cell(ctx, home, made.repo)
                # Amendment G1: what this arm's model would be given, rendered with no model call.
                mentions, cues = runner.guard.visible_context(
                    ctx,
                    home,
                    made.repo,
                    task.prompt(plan.phrasings[0]),
                    cues=_study_cues(plan, run_dir, task),
                )
            finally:
                homes.unlink_auth(home)
            problems += _visible_problems(plan, ctx, mentions, cues)
            report_data[f"cell_check_{name}"] = {"problems": problems, "hooks": hooks.get("hooks")}
            report_data[f"visible_context_{name}"] = {
                "mentions": len(mentions),
                "examples": mentions[:3],
                "study_cues": cues,
            }
            print(_visible_line(plan, ctx, len(mentions)))
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


def _runner_alive(pid_path: Path) -> int | None:
    """The detached runner's pid if that process is still this harness (a pid can be reused)."""
    try:
        pid = int(pid_path.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    proc = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False
    )
    return pid if "truthstone.bench.codex" in proc.stdout else None


def _cmd_status(args: argparse.Namespace) -> int:
    """Progress of a run directory: counts only (no outcomes), the runner, stops and halts."""
    run_dir = Path(args.run_dir)
    plan = Plan.load(run_dir / "plan.json")
    records = orchestrator.load_records(run_dir / "cells.jsonl")
    cells = [r for r in records if r.get("kind") == "cell"]
    states = orchestrator.pair_states(records, plan.max_attempts, len(plan.arms))
    complete = sum(s.complete for s in states.values())
    excluded = sum(s.excluded for s in states.values())
    voids: dict[str, int] = {}
    for c in cells:
        if c["status"] != "valid":
            voids[str(c.get("void_reason"))] = voids.get(str(c.get("void_reason")), 0) + 1
    print(
        f"{plan.name}: suite {plan.suite}, arms {'+'.join(plan.arms)}, {plan.model}/{plan.effort}, "
        f"stage {plan.stage}"
    )
    print(f"pairs complete {complete}/{len(plan.pairs())}; excluded {excluded}")
    print(f"cells run {len(cells)}: valid {sum(c['status'] == 'valid' for c in cells)}; voids {voids}")
    if cells:
        last = cells[-1]
        print(f"last cell {last['cell_id']} ({last['status']}) at {time.ctime(last.get('finished_at') or 0)}")
    alive = _runner_alive(run_dir / "run.pid")
    print(f"runner: {'running, pid ' + str(alive) if alive else 'not running'}")
    for name in ("HALTED", "last-session.json", "allowance.json"):
        path = run_dir / name
        if path.exists():
            print(f"{name}: {path.read_text(encoding='utf-8').strip()[:400]}")
    return 0


def _detach(args: argparse.Namespace, run_dir: Path) -> int:
    """Re-run this exact command in a new session, detached from the terminal.

    The child survives the parent shell and session ending (``start_new_session``; macOS
    has no ``setsid`` command), keeps the machine awake while it runs (``caffeinate -i``),
    and writes ``run.log`` and ``run.pid`` in the run directory. Resuming is running the
    same command again: completed pairs are skipped.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    pid_path = run_dir / "run.pid"
    active = _runner_alive(pid_path)
    if active:
        print(f"refusing: a runner is already active for {run_dir} (pid {active})")
        return 2
    raw = [a for a in getattr(args, "raw_argv", sys.argv[1:]) if a != "--detach"]
    argv = [sys.executable, "-m", "truthstone.bench.codex", *raw]
    if "--run-dir" not in raw:
        argv += ["--run-dir", str(run_dir)]
    caffeinate = shutil.which("caffeinate")
    if caffeinate:
        argv = [caffeinate, "-i", *argv]
    log = run_dir / "run.log"
    with log.open("ab") as out, open(os.devnull, "rb") as devnull:
        child = subprocess.Popen(
            argv, stdin=devnull, stdout=out, stderr=subprocess.STDOUT, start_new_session=True, cwd=os.getcwd()
        )
    pid_path.write_text(f"{child.pid}\n")
    print(f"detached: pid {child.pid} (stop it with: kill -TERM -- -{child.pid}); log {log}")
    print(f"watch with: python -m truthstone.bench.codex status --run-dir {run_dir}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    if not args.confirm_live:
        print("refusing: a live run spends subscription usage; pass --confirm-live")
        return 2
    plan = Plan.load(Path(args.plan))
    run_dir = Path(args.run_dir) if args.run_dir else RESULTS / plan.name
    if getattr(args, "detach", False):
        return _detach(args, run_dir)
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
    tasks = suite.load_suite(only=args.task or None, suite=args.suite)
    run_dir = Path(args.run_dir)
    if run_dir.exists() and not args.resume:
        shutil.rmtree(run_dir)
    python = os.path.abspath(args.python or scripted.default_python())
    node = _node_for(tasks, args.node)
    host_fields: dict = {"suite": suite.suite_spec(args.suite).name}
    if node is not None:
        host_fields["node_version"] = toolchain.node_version(node)
    fake = None
    if args.host == "claude":
        # Simulated accounts that start near their caps, so one dry run exercises the
        # 98% rule, the personal reserve, a wait for a 5-hour reset and a mid-cell 429.
        policy = claude.AccountPolicy(per_cell_session=1.5, per_cell_week=0.25)
        host_fields = {
            **host_fields,
            "host": "claude",
            "accounts": ["work", "personal"],
            "budget": dataclasses.asdict(policy),
            "permission_mode": claude.DEFAULT_PERMISSION_MODE,
            "allowed_tools": list(claude.DEFAULT_ALLOWED_TOOLS),
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
        arms=ARM_CHOICES[args.arms],
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
        permission_mode=plan.permission_mode,
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
        task_node=node,
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


def read_allowance(codex_bin: str, account: str | None = None) -> dict | None:
    """An account's usage windows (None: the default login), read through a throwaway,
    isolated CODEX_HOME.

    ``account/rateLimits/read`` on ``codex app-server``: no prompt, no model call. The
    home holds only a symlink to the login, which is never opened here.
    """
    from truthstone.bench.codex import accounts as codex_accounts

    root = homes.private_dir(
        homes.default_work_root("allowance") / homes.neutral_name(os.getpid(), time.time(), account)
    )
    home = homes.private_dir(root / "c")
    try:
        homes.link_auth(home, codex_accounts.auth_source(account))
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(root),
            "CODEX_HOME": str(home),
            "USER": os.environ.get("USER", "dev"),
            "LANG": "en_US.UTF-8",
        }
        for attempt in range(3):  # a slow app-server answer is not a missing account
            try:
                with appserver.AppServer(codex_bin, env) as server:
                    return appserver.plan_type_and_windows(server.rate_limits())
            except appserver.AppServerError as exc:
                print(f"could not read usage windows{f' of {account}' if account else ''}: {exc}")
                time.sleep(2 * (attempt + 1))
        return None
    except homes.IsolationError as exc:
        print(f"could not read usage windows: {exc}")
        return None
    finally:
        homes.unlink_auth(home)
        shutil.rmtree(root, ignore_errors=True)


def _codex_accounts_report(codex_bin: str, policy: Any = None) -> dict[str, Any]:
    """Both Codex accounts' windows (G5), each one's eligibility and its cells before its weekly
    stop, and the combined capacity. No model call."""
    from truthstone.bench.codex import accounts as codex_accounts

    policy = policy or codex_accounts.CodexAccountPolicy()
    rows = {}
    for name in codex_accounts.PREFERENCE:
        reading = read_allowance(codex_bin, name)
        rows[name] = {**codex_accounts.describe(name, reading, policy), "reading": reading}
    usable = [r for r in rows.values() if r["reading"] is not None]
    return {"accounts": rows, "combined_capacity": sum(r["cells_before_weekly_stop"] for r in usable)}


def _print_accounts(report_data: dict[str, Any]) -> None:
    for name, row in report_data["accounts"].items():
        if row["reading"] is None:
            print(f"account {name}: usage windows unreadable")
            continue
        primary, week = row["windows"] or (None, None)
        print(
            f"account {name}: plan {row['plan_type']}; 5-hour {primary}%, weekly {week}%; "
            f"{'eligible' if row['eligible_for_a_pair'] else 'not eligible'} ({row['why']}); "
            f"{row['cells_before_weekly_stop']} cells before its weekly stop"
        )
    print(f"combined capacity: {report_data['combined_capacity']} cells")


def _cmd_allowance(args: argparse.Namespace) -> int:
    plan = Plan.load(Path(args.plan)) if args.plan else None
    if plan is not None and plan.accounts:
        report_data = _codex_accounts_report(args.codex, plan.account_policy())
        _print_accounts(report_data)
        run_dir = Path(args.run_dir) if args.run_dir else RESULTS / plan.name
        states = orchestrator.pair_states(
            orchestrator.load_records(run_dir / "cells.jsonl"), plan.max_attempts, len(plan.arms)
        )
        remaining = len(plan.arms) * sum(
            1
            for p in plan.pairs()
            if not states.get(p.id, orchestrator.PairState()).complete
            and not states.get(p.id, orchestrator.PairState()).excluded
        )
        room = sum(report_data["accounts"][a]["cells_before_weekly_stop"] for a in plan.accounts)
        print(
            f"plan {plan.name}: {remaining} cells on accounts {plan.accounts}, which can take {room}: "
            + ("fits" if room >= remaining else "does NOT fit (run what fits with --allow-partial)")
        )
        if args.json:
            print(json.dumps(report_data, indent=2, default=str))
        return 0 if room >= remaining else 1
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
        run_dir = Path(args.run_dir) if args.run_dir else RESULTS / plan.name
        states = orchestrator.pair_states(
            orchestrator.load_records(run_dir / "cells.jsonl"), plan.max_attempts, len(plan.arms)
        )
        remaining = sum(
            1
            for p in plan.pairs()
            if not states.get(p.id, orchestrator.PairState()).complete
            and not states.get(p.id, orchestrator.PairState()).excluded
        )
        verdict = limits.feasibility(reading, len(plan.arms) * remaining, plan.budget_policy())
        print(f"plan {plan.name}: {verdict.reason}")
        status = 0 if verdict.ok else 1
    print("both Codex accounts (G5), for information:")
    _print_accounts(_codex_accounts_report(args.codex))
    if args.json:
        print(json.dumps(reading, indent=2))
    return status


def _cmd_calibrate(args: argparse.Namespace) -> int:
    """The dev review's calibration table pooled over several runs (pilot + extended screen)."""
    try:
        cal = report.pooled_calibration([Path(d) for d in args.run_dir], regraded=args.regraded)
    except (ValueError, FileNotFoundError) as exc:
        print(f"refusing to pool: {exc}")
        return 2
    if args.json:
        Path(args.json).write_text(json.dumps(cal, indent=2, default=str), encoding="utf-8")
    print(report.render_pooled_calibration(cal))
    return 0


def _cmd_regrade(args: argparse.Namespace) -> int:
    """Re-grade a finished run under today's grader from each cell's pristine tree and diff."""
    from truthstone.bench.codex import regrade

    rows = regrade.regrade_run(Path(args.run_dir), python=args.python)
    changed = [r for r in rows if "outcome" in r and r["outcome"] != r["stored_outcome"]]
    problems = [r for r in rows if "problem" in r]
    for r in changed:
        print(f"{r['cell_id']:<64} {r['stored_outcome']:<18} -> {r['outcome']}")
    print(
        f"{len(rows)} valid cells re-graded: {len(changed)} changed outcome, {len(problems)} could not be "
        f"re-graded; details in {Path(args.run_dir) / regrade.OUT}"
    )
    for r in problems:
        print(f"  {r['cell_id']}: {r['problem']}")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    if args.gate:
        from truthstone.bench.codex import acceptance

        overrides = {}
        for item in args.threshold or []:
            key, _, value = item.partition("=")
            overrides[key.strip()] = float(value)
        run_dirs = [Path(d) for d in args.run_dir]
        plans = [Plan.load(d / "plan.json") for d in run_dirs]
        if len(plans) > 1 and all(len(p.arms) == 2 for p in plans):
            # paired runs (the held-out study): only the shards of one design, partitioning it (G9)
            try:
                report.pooled_design(run_dirs)
            except ValueError as exc:
                print(f"refusing the gate: {exc}")
                return 2
        result = acceptance.gate(run_dirs, acceptance.GateThresholds(**overrides))
        if args.json:
            Path(args.json).write_text(json.dumps(result, indent=2, default=str))
        print(acceptance.render_gate(result))
        return 0 if result["overall"] == "PASS" else 1
    if args.acceptance:
        from truthstone.bench.codex import acceptance

        result = acceptance.acceptance([Path(d) for d in args.run_dir])
        if args.json:
            Path(args.json).write_text(json.dumps(result, indent=2, default=str))
        text = acceptance.render(result)
        if args.markdown:
            Path(args.markdown).write_text(text)
        print(text)
        return 0
    run_dirs = [Path(d) for d in args.run_dir]
    run_dir = run_dirs[0]
    try:
        # several run dirs: the shards of one design (G9), analysed as one
        analysis = report.analyze(run_dirs if len(run_dirs) > 1 else run_dir)
    except ValueError as exc:
        print(f"refusing to analyse: {exc}")
        return 2
    out_json = Path(args.json) if args.json else run_dir / "analysis.json"
    out_md = Path(args.markdown) if args.markdown else run_dir / "report.md"
    out_json.write_text(json.dumps(analysis, indent=2, default=str))
    out_md.write_text(report.render_markdown(analysis))
    print(report.render_markdown(analysis))
    return 0


# -- parser -----------------------------------------------------------------------


def _suite_option(p: argparse.ArgumentParser, live: bool = False) -> None:
    p.add_argument(
        "--suite",
        choices=list(suite.SUITES),
        default=None if live else suite.DEFAULT_SUITE,
        help=(
            "Must match the plan's suite (the plan pins it)."
            if live
            else f"Named task suite (default {suite.DEFAULT_SUITE})."
        ),
    )


def _arms_option(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--arms",
        choices=list(ARM_CHOICES),
        default="both",
        help="both (the paired study) or observe (a screening pilot: base rates, cost, instrument).",
    )


def _node_option(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--node", help=f"Node for TypeScript tasks (default: ${toolchain.ENV_NODE}, PATH, then nvm)."
    )


def _live_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--plan", required=True)
    _suite_option(p, live=True)
    _node_option(p)
    p.add_argument("--run-dir")
    p.add_argument("--work-root", help="Neutral directory outside /tmp for homes and cell repos.")
    p.add_argument("--codex", default=DEFAULT_CODEX)
    p.add_argument(
        "--claude", default=DEFAULT_CLAUDE, help="Claude Code binary (copied and pinned per study)."
    )
    p.add_argument("--uv", default=DEFAULT_UV)
    p.add_argument(
        "--truthstone-repo",
        default=str(suite.REPO_ROOT),
        help="Git repository the build under test is exported from.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m truthstone.bench.codex")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="List the task suite.")
    _suite_option(p)
    p.add_argument("--task", action="append")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("validate", help="Prove every grader on noop/honest/planted solutions.")
    _suite_option(p)
    p.add_argument("--task", action="append")
    p.add_argument("--python", help="Interpreter with pytest for the task code.")
    _node_option(p)
    p.add_argument("--json")
    p.add_argument(
        "--allow-untracked",
        action="store_true",
        help="Validate task files not committed yet (drafting); files .gitignore excludes are refused.",
    )
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("plan", help="Write a run plan (pre-registration input).")
    _suite_option(p)
    _node_option(p)
    p.add_argument("--name", required=True)
    p.add_argument("--stage", default="main", choices=["pilot", "main", "smoke"])
    p.add_argument("--seed", type=int, default=20261105)
    p.add_argument("--task", action="append")
    p.add_argument("--phrasing", action="append", choices=list(suite.PHRASINGS))
    p.add_argument("--replicates", default="1,2,3")
    p.add_argument("--host", default="codex", choices=["codex", "claude"])
    p.add_argument("--model", help="Default: gpt-6.1-sol (codex), claude-opus-5-5 (claude).")
    p.add_argument("--effort", default="medium")
    p.add_argument(
        "--accounts",
        help="Comma-separated accounts the plan may use. Claude: work,personal (default). Codex (G5): "
        "p,main (none: the default login, as before).",
    )
    p.add_argument("--permission-mode", help="Claude: --permission-mode for cells (default dontAsk).")
    p.add_argument(
        "--allowed-tools", help="Claude: comma-separated --allowedTools (default: the coding tools)."
    )
    p.add_argument("--per-cell-session", type=float, help="Claude: measured 5-hour points per cell (smoke).")
    p.add_argument("--per-cell-week", type=float, help="Claude: measured weekly points per cell (smoke).")
    p.add_argument("--claude", default=DEFAULT_CLAUDE)
    p.add_argument("--truthstone-ref", default="HEAD")
    p.add_argument("--trust", default="app-server", choices=["app-server", "bypass"])
    p.add_argument("--cell-timeout", type=int, default=1200)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--stop-weekly-at", type=float, help="Override the weekly stop line (smoke plans only).")
    p.add_argument(
        "--week-stop",
        action="append",
        metavar="ACCOUNT=PERCENT",
        help="Codex multi-account plans: move one account's weekly stop line (G21), e.g. main=80.",
    )
    p.add_argument(
        "--weekly-percent-per-cell",
        type=float,
        help="Measured weekly usage per cell (from the pilot), for the allowance pre-check.",
    )
    p.add_argument("--codex", default=DEFAULT_CODEX)
    p.add_argument("--notes")
    _arms_option(p)
    p.add_argument(
        "--shard",
        help="K/N or K1,K2,.../N: run only the pairs whose position modulo N is one of the K "
        "(disjoint shards for parallel runners, amendment G9; 0,1,2/5 is three fifths).",
    )
    p.add_argument(
        "--observe-plugin",
        default="hooks-only",
        choices=["hooks-only", "full"],
        help="What the observe arm installs (amendment G1): the plugin without its skills (default), "
        "or the full plugin, whose skill listing names the guard to the model.",
    )
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
        p.add_argument(
            "--detach",
            action="store_true",
            help="Run in a new session (survives the terminal), awake, logging to <run-dir>/run.log.",
        )
        p.set_defaults(func=_cmd_run)

    p = sub.add_parser("status", help="Progress of a run directory (counts only; no outcomes).")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(func=_cmd_status)

    p = sub.add_parser("dry-run", help="The whole pipeline with a scripted agent and a fake guard.")
    _suite_option(p)
    _node_option(p)
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
    _arms_option(p)
    p.set_defaults(func=_cmd_dry_run)

    p = sub.add_parser(
        "sandbox-check",
        help="Prove the cells' sandbox, no model (Claude: real binary + scripted local API; "
        "Codex: codex sandbox).",
    )
    p.add_argument("--host", default="both", choices=["claude", "codex", "both"])
    p.add_argument("--claude", default=DEFAULT_CLAUDE)
    p.add_argument("--codex", default=DEFAULT_CODEX)
    p.add_argument("--model", default="claude-opus-5-5", help="Model name the scripted API is asked for.")
    p.add_argument("--control", action="store_true", help="Also run the unsandboxed negative control.")
    p.add_argument("--json")
    p.set_defaults(func=_cmd_sandbox_check)

    p = sub.add_parser("leakage", help="Rebuild the no-leakage lint's hashed list of task strings.")
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=_cmd_leakage)

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

    p = sub.add_parser(
        "calibrate", help="Dev review: observe-arm base rates pooled over runs of one suite (blind)."
    )
    p.add_argument("--run-dir", action="append", required=True, help="Repeat for each run to pool.")
    p.add_argument(
        "--regraded", action="store_true", help="Use each run's regrade.json (today's grader) for outcomes."
    )
    p.add_argument("--json")
    p.set_defaults(func=_cmd_calibrate)

    p = sub.add_parser("regrade", help="Re-grade a finished run under today's grader (no model).")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--python", help="Interpreter with pytest for the task code.")
    p.set_defaults(func=_cmd_regrade)

    p = sub.add_parser("analyze", help="Pre-registered analysis of a run directory.")
    p.add_argument("--run-dir", required=True, action="append")
    p.add_argument(
        "--acceptance",
        action="store_true",
        help="The v0.2 acceptance targets T1-T6 over one or more dev runs (never held-out).",
    )
    p.add_argument(
        "--gate",
        action="store_true",
        help="The release gate (G9): one PASS/FAIL line per target, dev GO/NO-GO or the held-out study.",
    )
    p.add_argument(
        "--threshold",
        action="append",
        help="Override a gate threshold, KEY=VALUE (e.g. t3_lower=-0.05); see acceptance.GateThresholds.",
    )
    p.add_argument("--json")
    p.add_argument("--markdown")
    p.set_defaults(func=_cmd_analyze)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.raw_argv = list(sys.argv[1:] if argv is None else argv)  # `run --detach` re-runs exactly this
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
