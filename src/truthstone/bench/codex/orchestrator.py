"""The cell loop: checkpointed, resumable, budget-gated, and strict about its instrument.

Per pair (task x phrasing x replicate), in the plan's interleaved order:

1. read the plan's usage windows; go, wait for a reset, or stop (outcome-blind);
2. run the two cells back to back, in the pair's pre-assigned arm order;
3. a cell is **valid** only if Codex completed a turn under the pinned settings and the
   arm is attested (hooks evidently ran, the observe flag matches, nothing leaked or was
   phantom-blocked). Anything else voids the cell, and a void cell voids its pair;
4. a void pair is re-run later, both cells, as a new attempt. Usage-limit voids wait for
   the window and do not count against the pair's attempt limit;
5. every cell is appended to ``cells.jsonl`` and fsynced before the next one starts.

Instrument failures that implicate the arm itself (an observe-only arm that spoke, a
denial nobody decided, the wrong mode recorded) halt the run: continuing would only
produce more data from a broken instrument.
"""

from __future__ import annotations

import dataclasses
import difflib
import json
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from truthstone.bench.codex import claims, grader, guards, homes, limits, naming, suite, toolchain, transcript
from truthstone.bench.codex.plan import Pair, Plan


class Halt(RuntimeError):
    """The instrument is broken. Stop, fix, resume."""


# Codex's sandbox modes as its rollout spells them (``sandbox_policy.type``).
_CODEX_SANDBOX_MODES = frozenset({"read-only", "workspace-write", "danger-full-access", "external-sandbox"})


@dataclass(slots=True)
class PairState:
    complete: bool = False
    excluded: bool = False
    attempts: int = 0  # attempts that count against the limit
    last_attempt: int = 0


def pair_states(records: list[dict], max_attempts: int, arms: int = 2) -> dict[str, PairState]:
    """Per pair: complete when all ``arms`` cells of one attempt are valid (2 for a paired
    plan, 1 for an observe-only screening plan)."""
    states: dict[str, PairState] = {}
    needed = arms
    by_attempt: dict[tuple[str, int], list[dict]] = {}
    for record in records:
        if record.get("kind") == "pair_excluded":
            states.setdefault(record["pair_id"], PairState()).excluded = True
            continue
        if record.get("kind") != "cell":
            continue
        by_attempt.setdefault((record["pair_id"], record["attempt"]), []).append(record)
    for (pair_id, attempt), cells in sorted(by_attempt.items()):
        state = states.setdefault(pair_id, PairState())
        state.last_attempt = max(state.last_attempt, attempt)
        by_arm = {c["arm"]: c for c in cells}
        if len(by_arm) == needed and all(c["status"] == "valid" for c in by_arm.values()):
            state.complete = True
        elif not all(c.get("void_reason") == "usage_limit" for c in cells if c["status"] != "valid"):
            state.attempts += 1
    for state in states.values():
        if not state.complete and state.attempts >= max_attempts:
            state.excluded = True
    return states


def screened_cells(records: list[dict]) -> list[dict]:
    """Observe-only screening: each pair's first valid observe cell."""
    seen: set[str] = set()
    out: list[dict] = []
    for record in sorted(
        (r for r in records if r.get("kind") == "cell" and r["status"] == "valid" and r["arm"] == "observe"),
        key=lambda r: (r["pair_id"], r["attempt"]),
    ):
        if record["pair_id"] not in seen:
            seen.add(record["pair_id"])
            out.append(record)
    return out


def complete_pairs(records: list[dict]) -> list[tuple[dict, dict]]:
    """(on, observe) for every pair's first attempt with both cells valid."""
    by_attempt: dict[tuple[str, int], dict[str, dict]] = {}
    for record in records:
        if record.get("kind") == "cell" and record["status"] == "valid":
            by_attempt.setdefault((record["pair_id"], record["attempt"]), {})[record["arm"]] = record
    seen: set[str] = set()
    out: list[tuple[dict, dict]] = []
    for (pair_id, _attempt), arms in sorted(by_attempt.items()):
        if pair_id in seen or set(arms) != {"on", "observe"}:
            continue
        seen.add(pair_id)
        out.append((arms["on"], arms["observe"]))
    return out


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except ValueError:
                continue  # a torn final line from a crash; that cell simply re-runs
    return records


def append_record(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


@dataclass(slots=True)
class Runner:
    plan: Plan
    tasks: dict[str, suite.Task]
    guard: Any  # guards.TruthstonePlugin | guards.FakeGuard
    agent: Any  # agents.CodexExecAgent | agents.ScriptedAgent
    run_dir: Path
    work_root: Path
    task_python: str
    real_codex: bool
    limits_reader: Callable[[], dict | None] | None = None
    sleep: Callable[[float], None] = time.sleep
    log: Callable[[str], None] = print
    contexts: dict[str, guards.ArmContext] = field(default_factory=dict)
    consecutive_voids: int = 0
    consecutive_limit_voids: int = 0
    allow_partial: bool = False  # start even if the allowance cannot finish the plan
    # Claude host: where cells live (outside the user's home), and account state.
    cell_root: Path | None = None
    account_reader: Callable[[str], dict | None] | None = None  # account -> /usage reading
    account_policy: Any = None  # claude.AccountPolicy
    account_readings: dict[str, dict | None] = field(default_factory=dict)
    usage_read_at: float = 0.0
    # TypeScript tasks: the pinned Node, and the private bin (node, npm, npx only) that
    # goes on the agent's PATH. None when the plan has no TypeScript task.
    task_node: str | None = None
    toolchain_bin: Path | None = None

    @property
    def host(self) -> str:
        return self.plan.host

    @property
    def instructions(self) -> str:
        """The repository-notes file this host reads (same protocol text either way)."""
        return "CLAUDE.md" if self.host == "claude" else "AGENTS.md"

    @property
    def cells_path(self) -> Path:
        return self.run_dir / "cells.jsonl"

    # -- binding the run directory to the plan ------------------------------------

    def bind(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        plan_path = self.run_dir / "plan.json"
        if plan_path.exists():
            existing = Plan.load(plan_path)
            if existing.digest() != self.plan.digest():
                raise Halt(
                    f"{self.run_dir} belongs to plan {existing.digest()[:12]}, not {self.plan.digest()[:12]}"
                )
        else:
            self.plan.save(plan_path)
        tasks_path = suite.suite_spec(self.plan.suite).tasks_path.resolve()
        strays = sorted(t for t in self.plan.tasks if self.tasks[t].root.parent.resolve() != tasks_path)
        if strays:
            raise Halt(f"task(s) {strays} are not from the plan's suite {self.plan.suite!r}")
        digest = suite.suite_digest([self.tasks[t] for t in self.plan.tasks])
        if self.plan.suite_digest and digest != self.plan.suite_digest:
            raise Halt(
                f"the task suite changed since registration ({digest[:12]} != {self.plan.suite_digest[:12]})"
            )
        variant = getattr(self.guard, "observe_variant", None)  # None: the dry run's fake guard
        if variant is not None and variant != self.plan.observe_variant:
            raise Halt(
                f"the observe arm would install the {variant} plugin; the plan registers "
                f"{self.plan.observe_variant!r}"
            )

    # -- arms -------------------------------------------------------------------------

    def setup_arms(self) -> None:
        session = time.strftime("%Y%m%dT%H%M%S")
        prefix = [str(Path(self.task_python).parent)]
        if self.toolchain_bin is not None:
            prefix.append(str(self.toolchain_bin))
        shell_home = homes.scratch_shell_home(self.work_root / homes.neutral_name("shell", session), prefix)
        used: set[int] = set()
        for name in self.plan.arms:
            arm = guards.ARMS[name]
            root = homes.private_dir(self.work_root / homes.neutral_name("arm", name, session))
            ctx = guards.ArmContext(arm, root, root / "c", root / "g", shell_home)
            self.guard.prepare_arm(ctx, used)
            used.add(ctx.port)
            self.contexts[name] = ctx
        if self.host == "claude" and self.real_codex and hasattr(self.guard, "provision"):
            scratch = homes.private_dir(self.work_root / homes.neutral_name("provision", session))
            for account in self.plan.accounts:
                problems = self.guard.provision(account, scratch)
                if problems:
                    raise Halt(f"could not provision the plugin runtime: {problems}")
        build = getattr(self.guard, "build", None)
        if build is not None:
            build_path = self.run_dir / "build.json"
            recorded = json.loads(build_path.read_text()) if build_path.exists() else None
            if recorded and recorded["commit"] != build.commit:
                raise Halt(f"build under test changed: {recorded['commit'][:12]} -> {build.commit[:12]}")
            build_path.write_text(
                json.dumps(
                    {
                        "ref": build.ref,
                        "commit": build.commit,
                        "plugin_digest": build.plugin_digest,
                        "version": build.version,
                    },
                    indent=2,
                )
            )

    def manipulation_checks(self) -> list[dict]:
        """Before any model call: prove each arm's identity with synthetic payloads."""
        if not hasattr(self.guard, "manipulation_check"):
            return []
        results = []
        canary = self.tasks.get("ledger-tax-rounding") or next(
            (t for _, t in sorted(self.tasks.items()) if t.language == "python"),
            next(iter(self.tasks.values())),
        )
        accounts: list[str | None] = list(self.plan.accounts) if self.host == "claude" else [None]
        for name, ctx in self.contexts.items():
            for account in accounts:
                where = (self.cell_root or ctx.root) / homes.neutral_name(
                    "mcheck", name, account, time.time()
                )
                made = suite.materialize(
                    canary,
                    where / "w",
                    where / "pristine",
                    python=self.task_python,
                    instructions=self.instructions,
                )
                target, old, new = _first_source_edit(made.repo)
                if account is None:
                    result = self.guard.manipulation_check(ctx, made.repo, target, old, new)
                else:
                    result = self.guard.manipulation_check(ctx, account, made.repo, target, old, new)
                results.append(result)
                shutil.rmtree(where, ignore_errors=True)
                if result["problems"]:
                    raise Halt(f"manipulation check failed for arm {name}: {result['problems']}")
        with (self.run_dir / "manipulation-checks.jsonl").open("a", encoding="utf-8") as handle:
            handle.writelines(json.dumps({"ts": time.time(), **r}, default=str) + "\n" for r in results)
        return results

    def teardown_arms(self) -> None:
        for name, ctx in self.contexts.items():
            try:
                self.guard.teardown_arm(ctx, self.run_dir / "arms" / f"{name}-{ctx.root.name}")
            except Exception as exc:  # noqa: BLE001 - teardown must not mask the run's own error
                self.log(f"teardown {name}: {exc}")

    # -- the loop -------------------------------------------------------------------

    def run(self, max_pairs: int | None = None) -> dict[str, Any]:
        self.bind()
        records = load_records(self.cells_path)
        arms = len(self.plan.arms)
        states = pair_states(records, self.plan.max_attempts, arms)
        queue = [
            entry
            for entry in self.plan.schedule()
            if not states.get(entry[0].id, PairState()).complete
            and not states.get(entry[0].id, PairState()).excluded
        ]
        done_pairs = 0
        stopped = ""
        self.log(f"{len(queue)} pair(s) to run; {sum(s.complete for s in states.values())} already complete")
        if not queue:
            return {"pairs_run": 0, "stopped": "nothing to do"}
        self.setup_arms()
        try:
            self._check_allowance(arms * (len(queue) if max_pairs is None else min(max_pairs, len(queue))))
            self.manipulation_checks()
            while queue and (max_pairs is None or done_pairs < max_pairs):
                pair, order = queue[0]
                state = states.setdefault(pair.id, PairState())
                account: str | None = None
                if self.host == "claude":
                    choice = self._choose_account()
                    if choice.account is None:
                        if choice.wait_s:
                            self.log(f"account wait {choice.wait_s}s: {choice.reason}")
                            self.sleep(choice.wait_s)
                            self._refresh_usage(force=True)  # confirm the reset with /usage
                            continue
                        stopped = choice.reason
                        self.log(f"account stop: {choice.reason}")
                        break
                    account = choice.account
                else:
                    decision = self._budget()
                    if decision.action == "stop":
                        stopped = decision.reason
                        self.log(f"budget stop: {decision.reason}")
                        break
                    if decision.action == "wait":
                        self.log(f"budget wait {decision.seconds}s: {decision.reason}")
                        self.sleep(decision.seconds)
                        continue
                queue.pop(0)
                attempt = state.last_attempt + 1
                cells = []
                for arm in order:
                    if cells and self._account_blocked(account):
                        # The 98% rule applies to every cell's start, including a pair's second.
                        record = self._deferred_cell(pair, arm, attempt, account)
                        append_record(self.cells_path, record)
                        cells.append(record)
                        self.log(_line(record))
                        break
                    record = self.run_cell(pair, arm, attempt, account=account)
                    self._note_stream_reading(account, record)
                    append_record(self.cells_path, record)
                    cells.append(record)
                    self.log(_line(record))
                    if record["status"] == "halt":
                        raise Halt(f"{record['cell_id']}: {record['problems']}")
                    if record.get("void_reason") == "usage_limit":
                        break  # never spend the other arm into an exhausted window
                state.last_attempt = attempt
                if any(c["status"] == "valid" for c in cells):
                    self.consecutive_limit_voids = 0
                if len(cells) == arms and all(c["status"] == "valid" for c in cells):
                    state.complete = True
                    self.consecutive_voids = 0
                    done_pairs += 1
                    continue
                usage = any(c.get("void_reason") == "usage_limit" for c in cells)
                if usage and self.host == "claude":
                    self.consecutive_limit_voids += 1
                    if self.consecutive_limit_voids >= 3:
                        # Readings say go but the provider keeps refusing (a limit /usage does
                        # not show). Stop rather than spin; resume later from the checkpoint.
                        stopped = "three consecutive usage-limit voids"
                        self.log(f"account stop: {stopped}")
                        queue.insert(0, (pair, order))
                        break
                    self._refresh_usage(force=True)  # the stream's reading may be stale
                if not usage:
                    state.attempts += 1
                    self.consecutive_voids += 1
                    if self.consecutive_voids >= 3:
                        raise Halt("three consecutive void pairs: the instrument, not the agent, is failing")
                if state.attempts >= self.plan.max_attempts:
                    append_record(
                        self.cells_path,
                        {
                            "kind": "pair_excluded",
                            "pair_id": pair.id,
                            "attempts": state.attempts,
                            "ts": time.time(),
                        },
                    )
                    self.log(f"pair excluded after {state.attempts} void attempt(s): {pair.id}")
                    continue
                # Re-run at the end of the current replicate block.
                position = next(
                    (i for i, (p, _) in enumerate(queue) if p.replicate != pair.replicate), len(queue)
                )
                queue.insert(position, (pair, order))
        finally:
            self.teardown_arms()
        summary = {"pairs_run": done_pairs, "stopped": stopped, "remaining": len(queue)}
        (self.run_dir / "last-session.json").write_text(json.dumps(summary, indent=2))
        return summary

    # -- Claude accounts --------------------------------------------------------------

    def _refresh_usage(self, force: bool = False) -> None:
        """``/usage`` for every allowed account: at the start, every refresh interval, on demand."""
        if self.account_reader is None:
            return
        interval = getattr(self.account_policy, "usage_refresh_s", 1800)
        if not force and time.time() - self.usage_read_at < interval:
            return
        for account in self.plan.accounts:
            self.account_readings[account] = self.account_reader(account)
        self.usage_read_at = time.time()
        with (self.run_dir / "usage.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps({"ts": self.usage_read_at, "readings": self.account_readings}, default=str) + "\n"
            )

    def _choose_account(self) -> Any:
        from truthstone.bench.codex import claude

        self._refresh_usage()
        policy = self.account_policy or claude.AccountPolicy()
        return claude.choose_account(self.account_readings, policy, allowed=tuple(self.plan.accounts))

    def _account_blocked(self, account: str | None) -> bool:
        """The start rule for a pair's second cell: the same caps as scheduling."""
        if account is None:
            return False
        from truthstone.bench.codex import claude

        policy = self.account_policy or claude.AccountPolicy()
        ok, _why = claude.cell_allowed(account, self.account_readings.get(account), policy)
        return not ok

    def _deferred_cell(self, pair: Pair, arm: str, attempt: int, account: str | None) -> dict[str, Any]:
        task = self.tasks[pair.task]
        return {
            "kind": "cell",
            "cell_id": f"{pair.task}.{pair.phrasing}.r{pair.replicate}.{arm}.a{attempt}",
            "pair_id": pair.id,
            "task": task.id,
            "set": task.set,
            "family": task.family,
            "recipe": task.recipe,
            "language": task.language,
            "phrasing": pair.phrasing,
            "replicate": pair.replicate,
            "arm": arm,
            "attempt": attempt,
            "account": account,
            "started_at": time.time(),
            "finished_at": time.time(),
            "status": "void",
            "void_reason": "usage_limit",
            "problems": [
                "not started: the account reached its start cap (the 98% rule, or the personal reserve)"
            ],
        }

    def _note_stream_reading(self, account: str | None, record: dict) -> None:
        """Between /usage reads, a cell's own rate_limit_event is the freshest reading."""
        if account is None:
            return
        from truthstone.bench.codex import claude

        reading = claude.reading_from_stream(record.get("limits_after"))
        if reading is not None and reading["session"].get("used_percent") is not None:
            previous = self.account_readings.get(account) or {}
            if reading["week"].get("used_percent") is None and previous.get("week"):
                reading["week"] = previous["week"]  # the stream may omit the weekly window
            self.account_readings[account] = reading

    def _check_allowance(self, cells: int) -> None:
        """Refuse to start a study the plan's weekly allowance cannot finish."""
        if self.host == "claude":
            self._refresh_usage(force=True)
            choice = self._choose_account()
            record = {
                "ts": time.time(),
                "cells": cells,
                "account_choice": choice.account,
                "reason": choice.reason,
                "readings": self.account_readings,
            }
            (self.run_dir / "allowance.json").write_text(json.dumps(record, indent=2, default=str))
            self.log(f"allowance: {choice.reason}")
            if choice.account is None and not choice.wait_s and not self.allow_partial:
                raise Halt(f"refusing to start: {choice.reason}")
            return
        if self.limits_reader is None:
            return
        verdict = limits.feasibility(self.limits_reader(), cells, self.plan.budget_policy())
        self.log(f"allowance: {verdict.reason}")
        record = {"ts": time.time(), "cells": cells, **dataclasses.asdict(verdict)}
        (self.run_dir / "allowance.json").write_text(json.dumps(record, indent=2))
        if not verdict.ok and not self.allow_partial:
            raise Halt(f"refusing to start: {verdict.reason}. Pass --allow-partial to run what fits.")

    def _budget(self) -> limits.BudgetDecision:
        if self.limits_reader is None:
            return limits.BudgetDecision("go", 0, "no budget reader (dry run)")
        reading = self.limits_reader()
        return limits.decide(reading, self.plan.budget_policy())

    # -- one cell -------------------------------------------------------------------

    def run_cell(self, pair: Pair, arm_name: str, attempt: int, account: str | None = None) -> dict[str, Any]:
        task = self.tasks[pair.task]
        ctx = self.contexts[arm_name]
        cell_id = f"{pair.task}.{pair.phrasing}.r{pair.replicate}.{arm_name}.a{attempt}"
        cell_dir = self.run_dir / "cells" / cell_id
        if cell_dir.exists():
            shutil.rmtree(cell_dir)
        cell_dir.mkdir(parents=True)
        work = homes.private_dir(
            (self.cell_root or self.work_root) / homes.neutral_name("cell", cell_id, time.time())
        )
        trace_dir = work / "h"
        tmpdir = homes.private_dir(work / "t")
        record: dict[str, Any] = {
            "kind": "cell",
            "cell_id": cell_id,
            "pair_id": pair.id,
            "task": task.id,
            "set": task.set,
            "family": task.family,
            "recipe": task.recipe,
            "language": task.language,
            "phrasing": pair.phrasing,
            "replicate": pair.replicate,
            "arm": arm_name,
            "attempt": attempt,
            "started_at": time.time(),
            "status": "void",
            "void_reason": None,
            "problems": [],
            "provenance": dict(ctx.provenance),
            "account": account,
        }
        codex_home: Path | None = None
        try:
            made = suite.materialize(
                task,
                work / "w",
                cell_dir / "pristine",
                python=self.task_python,
                instructions=self.instructions,
            )
            if self.real_codex and self.host == "codex":
                codex_home = homes.clone_codex_home(ctx.codex_template, work / "c")
                problems, report = self.guard.verify_cell(ctx, codex_home, made.repo)
                record["limits_before"] = report.get("limits")
                record["hooks"] = report.get("hooks")
                health = self.guard.health(ctx)
                if not health or bool(health.get("observing")) != ctx.arm.observe_only:
                    record.update(status="halt", void_reason="daemon", problems=[f"daemon health {health}"])
                    return record
                if problems:
                    record.update(void_reason="preflight", problems=problems)
                    return record
            elif self.real_codex and self.host == "claude":
                problems, report = self.guard.verify_cell(ctx, account, made.repo)
                record["limits_before"] = self.account_readings.get(account)
                health = self.guard.health(ctx)
                if not health or bool(health.get("observing")) != ctx.arm.observe_only:
                    record.update(status="halt", void_reason="daemon", problems=[f"daemon health {health}"])
                    return record
                if problems:
                    record.update(void_reason="preflight", problems=problems)
                    return record
            env = self._env(ctx, codex_home, tmpdir, trace_dir, account=account)
            run = self.agent.run(
                task.prompt(pair.phrasing),
                made.repo,
                env,
                cell_dir,
                tmpdir,
                self.guard.exec_args(ctx),
                task=task,
                phrasing=pair.phrasing,
                replicate=pair.replicate,
                arm=arm_name,
                trace_dir=trace_dir,
                observe_only=ctx.arm.observe_only,
                account=account,
            )
            record["wall_s"] = round(run.duration_s, 2)
            record["timed_out"] = run.timed_out
            record["exit_code"] = run.exit_code
            if codex_home is not None:
                rollout = transcript.find_rollout(codex_home)
                if rollout is not None:
                    shutil.copyfile(rollout, cell_dir / "rollout.jsonl")
            if self.host == "claude":
                t = transcript.read_claude_stream(run.stdout_path)
            else:
                t = transcript.read_exec_stream(run.stdout_path)
                t = transcript.read_rollout(cell_dir / "rollout.jsonl", t)
            if run.last_message_path.exists() and run.last_message_path.read_text(encoding="utf-8").strip():
                t.final_message = run.last_message_path.read_text(encoding="utf-8")
            (cell_dir / "transcript.json").write_text(json.dumps(t.to_dict(), default=str, indent=1))
            evidence = self.guard.collect(ctx, made.repo, trace_dir)
            (cell_dir / "evidence.json").write_text(json.dumps(evidence.to_dict(), default=str, indent=1))
            if trace_dir.exists():
                shutil.copytree(trace_dir, cell_dir / "hooks", dirs_exist_ok=True)
            if self.host == "claude":
                # Claude Code tells its hooks the effort and permission mode, not its stream.
                reported = evidence.recorder_settings
                efforts = {_effort_level(s.get("effort")) for s in reported if s.get("effort")}
                if len(efforts) == 1:
                    t.effort = efforts.pop()
                elif efforts:
                    t.effort = ",".join(sorted(efforts))
                modes = {str(s["permission_mode"]) for s in reported if s.get("permission_mode")}
                record["permission_modes"] = sorted(modes)
                record["hook_events_reported"] = t.hook_events_reported
                record["post_tool_feedback"] = len(t.post_tool_feedback)
            record.update(self._facts(t, evidence))
            # The instrument check (amendment G1): what the observe arm's model was given must
            # not name the product. Recorded for every observe cell; void under a G1 plan.
            if ctx.arm.observe_only and t.visible_product:
                record["visible_product"] = t.visible_product[:5]

            infra = limits.classify_infra(
                run.exit_code,
                run.timed_out,
                t.turns_completed,
                t.final_message,
                t.errors,
                run.stderr_tail(),
                t.usage_limit_hit,
            )
            settings = self._settings_drift(t)
            if self.host == "claude":
                modes = set(record.get("permission_modes") or []) | (
                    {t.approval_policy} if t.approval_policy else set()
                )
                if modes and modes != {self.plan.permission_mode}:
                    settings.append(
                        f"permission mode {sorted(modes)} != pinned {self.plan.permission_mode!r}"
                    )
                if (t.rate_limits_last or {}).get("using_overage"):
                    record.update(
                        status="halt",
                        void_reason="overage",
                        problems=["the account is spending paid overage; never allowed"],
                    )
                    return record
            if self.real_codex and self.host == "claude":
                after, _ = self.guard.verify_cell(ctx, account, made.repo)
                settings += after  # the runtime must not have changed during the cell
            problems = guards.attest(ctx.arm, evidence, t, require_recorder=bool(self.plan.recorder))
            graded = grader.grade(
                task, made.repo, made.pristine, made.manifest, self.task_python, work, node=self.task_node
            )
            claim = claims.parse(t.final_message)
            record.update(self._grade_fields(task, claim, graded))
            record["stop_assessments"] = self._assess_stops(task, made, evidence, trace_dir, work)
            record["false_blocks"] = sum(1 for s in record["stop_assessments"] if s["false_block"])
            (cell_dir / "grade.json").write_text(json.dumps(graded.to_dict(), default=str, indent=1))
            _write_diff(made.pristine, made.repo, cell_dir / "final.diff")

            if record.get("visible_product") and self.plan.skill_free_observe:
                # Systematic (the arm's install, not the agent): stop before it costs more.
                record.update(
                    status="halt",
                    void_reason="visible_product",
                    problems=[
                        f"the observe arm's model was shown the product: {record['visible_product'][0]}"
                    ],
                )
            elif infra:
                record.update(void_reason=infra, problems=[p.text for p in problems])
            elif settings:
                record.update(void_reason="settings_drift", problems=settings)
            elif any(p.severity == "halt" for p in problems):
                record.update(status="halt", void_reason="attestation", problems=[p.text for p in problems])
            elif problems:
                record.update(void_reason="attestation", problems=[p.text for p in problems])
            else:
                record["status"] = "valid"
            return record
        except Halt:
            raise
        except Exception as exc:  # noqa: BLE001 - a harness failure voids the cell, visibly
            record.update(void_reason="harness_error", problems=[f"{type(exc).__name__}: {exc}"])
            return record
        finally:
            record["finished_at"] = time.time()
            if codex_home is not None:
                try:
                    homes.unlink_auth(codex_home)
                except homes.IsolationError as exc:
                    record["problems"].append(str(exc))
            shutil.rmtree(work, ignore_errors=True)

    def _env(
        self,
        ctx: guards.ArmContext,
        codex_home: Path | None,
        tmpdir: Path,
        trace_dir: Path,
        account: str | None = None,
    ) -> dict[str, str]:
        task_bin = str(Path(self.task_python).parent)
        if self.toolchain_bin is not None:
            task_bin = f"{task_bin}:{self.toolchain_bin}"
        env = {
            "PATH": f"{task_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(ctx.shell_home),
            "ZDOTDIR": str(ctx.shell_home),
            "SHELL": "/bin/zsh",
            "TMPDIR": str(tmpdir),
            "USER": os.environ.get("USER", "dev"),
            "LOGNAME": os.environ.get("LOGNAME", os.environ.get("USER", "dev")),
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
            "TZ": "UTC",
            "TERM": "dumb",
            "NO_COLOR": "1",
            "GIT_AUTHOR_NAME": "Dev",
            "GIT_AUTHOR_EMAIL": "dev@example.com",
            "GIT_COMMITTER_NAME": "Dev",
            "GIT_COMMITTER_EMAIL": "dev@example.com",
            naming.ENV_RECORD_DIR: str(trace_dir),
            **self.guard.arm_env(ctx),
        }
        if self.toolchain_bin is not None:
            env.update(toolchain.npm_env(tmpdir))
        if codex_home is not None:
            env["CODEX_HOME"] = str(codex_home)
        if self.host == "claude" and self.real_codex:
            # The subscription sign-in lives in the login keychain, which follows HOME, so
            # the real HOME stays (verified: a scratch HOME falls back to an unsigned session).
            env["HOME"] = str(Path.home())
            env.pop("ZDOTDIR", None)
            env["DISABLE_AUTOUPDATER"] = "1"  # the study's pinned binary must stay what it is
            accounts = getattr(self.guard, "accounts", {})
            if account in accounts:
                env["CLAUDE_CONFIG_DIR"] = str(accounts[account])
        return env

    def _settings_drift(self, t: transcript.Transcript) -> list[str]:
        drift = []
        if t.model and t.model != self.plan.model:
            drift.append(f"model {t.model!r} != pinned {self.plan.model!r}")
        if t.effort and t.effort != self.plan.effort:
            drift.append(f"effort {t.effort!r} != pinned {self.plan.effort!r}")
        if (
            self.plan.codex_version
            and t.cli_version
            and t.cli_version not in (self.plan.codex_version, "scripted")
        ):
            drift.append(f"{self.host} {t.cli_version!r} != pinned {self.plan.codex_version!r}")
        if self.host == "codex":
            # The sandbox as Codex applied it (the rollout's turn context), not as requested.
            # Only a recognised, different mode counts: an unfamiliar spelling from a newer
            # Codex must not void every cell.
            if t.sandbox in _CODEX_SANDBOX_MODES and t.sandbox != self.plan.sandbox:
                drift.append(f"sandbox {t.sandbox!r} != pinned {self.plan.sandbox!r}")
            if t.sandbox_network is not None and t.sandbox_network != self.plan.network:
                drift.append(f"sandbox network access {t.sandbox_network} != pinned {self.plan.network}")
        return drift

    @staticmethod
    def _facts(t: transcript.Transcript, evidence: guards.HookEvidence) -> dict[str, Any]:
        model = t.model or ""
        return {
            "process": t.process_facts(),
            "visible_denials": len(t.visible_denials),
            "stop_continuations": len(t.stop_continuations),
            "guard_context_messages": t.guard_context_messages,
            "model_requests": t.model_requests,
            "usage": t.usage,
            "credits_est": limits.estimate_credits(model, t.usage),
            "limits_after": t.rate_limits_last,
            "duration_ms": t.duration_ms,
            "cli_version": t.cli_version,
            "model": t.model,
            "effort": t.effort,
            "evidence": evidence.summary(),
            "claim_message_present": t.final_message is not None,
        }

    @staticmethod
    def _grade_fields(task: suite.Task, claim: claims.Claim, graded: grader.Grade) -> dict[str, Any]:
        return {
            "claim": {"status": claim.status, "source": claim.source},
            "outcome": grader.outcome(task, claim, graded),
            "success": grader.task_success(task, claim, graded),
            "grade": {
                "passed": graded.passed,
                "reasons": graded.reasons[:20],
                "codes": sorted(graded.reason_codes),
                "canaries_lost": graded.canaries_lost,
                "out_of_scope": graded.out_of_scope,
                "protected_modified": graded.protected_modified,
                "new_dependencies": graded.new_dependencies,
                "sentinel_failures": graded.sentinel_failures,
                "mode_failures": graded.mode_failures,
                "changed": len(graded.changed) + len(graded.added) + len(graded.deleted),
            },
        }

    def _assess_stops(
        self,
        task: suite.Task,
        made: suite.Materialized,
        evidence: guards.HookEvidence,
        trace_dir: Path,
        work: Path,
    ) -> list[dict]:
        """For each Stop the guard held (or would have held): was the work already right?"""
        stops = [d for d in evidence.decisions if d.get("event_type") == "stop"]
        out = []
        for index, (decision, snap) in enumerate(zip(stops, evidence.recorder_stops, strict=False)):
            held = decision.get("action") == "block" or decision.get("would_have") == "block"
            if not held:
                continue
            snapshot_dir = trace_dir / str(snap.get("snapshot") or "")
            entry = {
                "index": index,
                "action": decision.get("action"),
                "would_have": decision.get("would_have"),
                "snapshot": snap.get("snapshot"),
                "false_block": False,
                "graded": False,
            }
            if snap.get("snapshot") and snapshot_dir.is_dir():
                graded = grader.grade(
                    task,
                    snapshot_dir,
                    made.pristine,
                    made.manifest,
                    self.task_python,
                    work / f"stop-{index}",
                    node=self.task_node,
                )
                claim = claims.parse(snap.get("last_assistant_message"))
                verdict = grader.outcome(task, claim, graded)
                entry.update(
                    graded=True,
                    snapshot_outcome=verdict,
                    snapshot_reasons=graded.reasons[:6],
                    false_block=verdict
                    in (grader.PASS_CLAIMED, grader.PASS_UNCLAIMED, grader.CORRECT_REFUSAL),
                )
            out.append(entry)
        return out


def _effort_level(raw: Any) -> str:
    """Claude Code reports effort to hooks as ``{"level": "medium"}``."""
    if isinstance(raw, dict):
        return str(raw.get("level") or "")
    return str(raw or "")


def _first_source_edit(repo: Path) -> tuple[str, str, str]:
    """A harmless one-line edit in the first covered module, for the check.

    Python: a one-line module docstring. TypeScript: a leading ``//`` comment line.
    """
    for path in sorted((repo / "src").rglob("*.py")):
        if path.name == "__init__.py":
            continue
        first = path.read_text(encoding="utf-8").splitlines()[0]
        if first.startswith('"""') and first.endswith('"""') and len(first) > 6:
            return path.relative_to(repo).as_posix(), first, first[:-3] + ' (reviewed)"""'
    for path in sorted((repo / "src").rglob("*.ts")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].startswith("// ") and len(lines[0]) > 6:
            return path.relative_to(repo).as_posix(), lines[0], lines[0] + " (reviewed)"
    raise Halt("no module with a one-line docstring or leading comment for the manipulation check")


_first_python_edit = _first_source_edit  # the former name


def _write_diff(pristine: Path, repo: Path, out: Path, limit: int = 200_000) -> None:
    before = suite.snapshot(pristine)
    after = suite.snapshot(repo)
    changed, added, deleted = suite.diff_snapshots(before, after)
    chunks: list[str] = []
    for rel in [*changed, *added, *deleted]:

        def read(root: Path, rel: str = rel) -> list[str]:
            path = root / rel
            try:
                return path.read_text(encoding="utf-8").splitlines(keepends=True) if path.is_file() else []
            except (UnicodeDecodeError, OSError):
                return ["<binary>\n"]

        chunks.extend(difflib.unified_diff(read(pristine), read(repo), f"a/{rel}", f"b/{rel}"))
        if sum(len(c) for c in chunks) > limit:
            chunks.append("\n<diff truncated>\n")
            break
    out.write_text("".join(chunks), encoding="utf-8")


def _line(record: dict) -> str:
    flag = {"valid": " ", "void": "~", "halt": "!"}.get(record["status"], "?")
    outcome = record.get("outcome", "-")
    extra = record.get("void_reason") or ""
    return (
        f"{flag} {record['cell_id']:<58} {outcome:<18} wall={record.get('wall_s', '-')}s "
        f"req={record.get('model_requests', '-')} {extra}"
    )
