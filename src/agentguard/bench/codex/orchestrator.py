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

import difflib
import json
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentguard.bench.codex import claims, grader, guards, homes, limits, naming, suite, transcript
from agentguard.bench.codex.plan import Pair, Plan


class Halt(RuntimeError):
    """The instrument is broken. Stop, fix, resume."""


@dataclass(slots=True)
class PairState:
    complete: bool = False
    excluded: bool = False
    attempts: int = 0  # attempts that count against the limit
    last_attempt: int = 0


def pair_states(records: list[dict], max_attempts: int) -> dict[str, PairState]:
    states: dict[str, PairState] = {}
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
        arms = {c["arm"]: c for c in cells}
        if len(arms) == 2 and all(c["status"] == "valid" for c in arms.values()):
            state.complete = True
        elif not all(c.get("void_reason") == "usage_limit" for c in cells if c["status"] != "valid"):
            state.attempts += 1
    for state in states.values():
        if not state.complete and state.attempts >= max_attempts:
            state.excluded = True
    return states


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
    guard: Any  # guards.AgentGuardPlugin | guards.FakeGuard
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
        digest = suite.suite_digest([self.tasks[t] for t in self.plan.tasks])
        if self.plan.suite_digest and digest != self.plan.suite_digest:
            raise Halt(
                f"the task suite changed since registration ({digest[:12]} != {self.plan.suite_digest[:12]})"
            )

    # -- arms -------------------------------------------------------------------------

    def setup_arms(self) -> None:
        session = time.strftime("%Y%m%dT%H%M%S")
        shell_home = homes.scratch_shell_home(
            self.work_root / homes.neutral_name("shell", session), [str(Path(self.task_python).parent)]
        )
        used: set[int] = set()
        for name in self.plan.arms:
            arm = guards.ARMS[name]
            root = homes.private_dir(self.work_root / homes.neutral_name("arm", name, session))
            ctx = guards.ArmContext(arm, root, root / "c", root / "g", shell_home)
            self.guard.prepare_arm(ctx, used)
            used.add(ctx.port)
            self.contexts[name] = ctx
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
        canary = self.tasks.get("ledger-tax-rounding") or next(iter(self.tasks.values()))
        for name, ctx in self.contexts.items():
            made = suite.materialize(
                canary, ctx.root / "mcheck" / "w", ctx.root / "mcheck" / "pristine", python=self.task_python
            )
            target, old, new = _first_python_edit(made.repo)
            result = self.guard.manipulation_check(ctx, made.repo, target, old, new)
            results.append(result)
            if result["problems"]:
                raise Halt(f"manipulation check failed for arm {name}: {result['problems']}")
            shutil.rmtree(ctx.root / "mcheck", ignore_errors=True)
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
        states = pair_states(records, self.plan.max_attempts)
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
            self.manipulation_checks()
            while queue and (max_pairs is None or done_pairs < max_pairs):
                pair, order = queue[0]
                state = states.setdefault(pair.id, PairState())
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
                    record = self.run_cell(pair, arm, attempt)
                    append_record(self.cells_path, record)
                    cells.append(record)
                    self.log(_line(record))
                    if record["status"] == "halt":
                        raise Halt(f"{record['cell_id']}: {record['problems']}")
                    if record.get("void_reason") == "usage_limit":
                        break  # never spend the other arm into an exhausted window
                state.last_attempt = attempt
                if len(cells) == 2 and all(c["status"] == "valid" for c in cells):
                    state.complete = True
                    self.consecutive_voids = 0
                    done_pairs += 1
                    continue
                usage = any(c.get("void_reason") == "usage_limit" for c in cells)
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

    def _budget(self) -> limits.BudgetDecision:
        if self.limits_reader is None:
            return limits.BudgetDecision("go", 0, "no budget reader (dry run)")
        reading = self.limits_reader()
        return limits.decide(reading, self.plan.budget_policy())

    # -- one cell -------------------------------------------------------------------

    def run_cell(self, pair: Pair, arm_name: str, attempt: int) -> dict[str, Any]:
        task = self.tasks[pair.task]
        ctx = self.contexts[arm_name]
        cell_id = f"{pair.task}.{pair.phrasing}.r{pair.replicate}.{arm_name}.a{attempt}"
        cell_dir = self.run_dir / "cells" / cell_id
        if cell_dir.exists():
            shutil.rmtree(cell_dir)
        cell_dir.mkdir(parents=True)
        work = homes.private_dir(self.work_root / homes.neutral_name("cell", cell_id, time.time()))
        trace_dir = work / "h"
        tmpdir = homes.private_dir(work / "t")
        record: dict[str, Any] = {
            "kind": "cell",
            "cell_id": cell_id,
            "pair_id": pair.id,
            "task": task.id,
            "set": task.set,
            "family": task.family,
            "phrasing": pair.phrasing,
            "replicate": pair.replicate,
            "arm": arm_name,
            "attempt": attempt,
            "started_at": time.time(),
            "status": "void",
            "void_reason": None,
            "problems": [],
            "provenance": dict(ctx.provenance),
        }
        codex_home: Path | None = None
        try:
            made = suite.materialize(task, work / "w", cell_dir / "pristine", python=self.task_python)
            if self.real_codex:
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
            env = self._env(ctx, codex_home, tmpdir, trace_dir)
            run = self.agent.run(
                task.prompt(pair.phrasing),
                made.repo,
                env,
                cell_dir,
                tmpdir,
                self.guard.exec_args(),
                task=task,
                phrasing=pair.phrasing,
                replicate=pair.replicate,
                arm=arm_name,
                trace_dir=trace_dir,
                observe_only=ctx.arm.observe_only,
            )
            record["wall_s"] = round(run.duration_s, 2)
            record["timed_out"] = run.timed_out
            record["exit_code"] = run.exit_code
            if codex_home is not None:
                rollout = transcript.find_rollout(codex_home)
                if rollout is not None:
                    shutil.copyfile(rollout, cell_dir / "rollout.jsonl")
            t = transcript.read_exec_stream(run.stdout_path)
            t = transcript.read_rollout(cell_dir / "rollout.jsonl", t)
            if run.last_message_path.exists() and run.last_message_path.read_text(encoding="utf-8").strip():
                t.final_message = run.last_message_path.read_text(encoding="utf-8")
            (cell_dir / "transcript.json").write_text(json.dumps(t.to_dict(), default=str, indent=1))
            evidence = self.guard.collect(ctx, made.repo, trace_dir)
            (cell_dir / "evidence.json").write_text(json.dumps(evidence.to_dict(), default=str, indent=1))
            if trace_dir.exists():
                shutil.copytree(trace_dir, cell_dir / "hooks", dirs_exist_ok=True)
            record.update(self._facts(t, evidence))

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
            problems = guards.attest(ctx.arm, evidence, t, require_recorder=bool(self.plan.recorder))
            graded = grader.grade(task, made.repo, made.pristine, made.manifest, self.task_python, work)
            claim = claims.parse(t.final_message)
            record.update(self._grade_fields(task, claim, graded))
            record["stop_assessments"] = self._assess_stops(task, made, evidence, trace_dir, work)
            record["false_blocks"] = sum(1 for s in record["stop_assessments"] if s["false_block"])
            (cell_dir / "grade.json").write_text(json.dumps(graded.to_dict(), default=str, indent=1))
            _write_diff(made.pristine, made.repo, cell_dir / "final.diff")

            if infra:
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
        self, ctx: guards.ArmContext, codex_home: Path | None, tmpdir: Path, trace_dir: Path
    ) -> dict[str, str]:
        task_bin = str(Path(self.task_python).parent)
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
        if codex_home is not None:
            env["CODEX_HOME"] = str(codex_home)
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
            drift.append(f"codex {t.cli_version!r} != pinned {self.plan.codex_version!r}")
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
                    task, snapshot_dir, made.pristine, made.manifest, self.task_python, work / f"stop-{index}"
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


def _first_python_edit(repo: Path) -> tuple[str, str, str]:
    """A harmless one-line docstring edit in the first covered module, for the check."""
    for path in sorted((repo / "src").rglob("*.py")):
        if path.name == "__init__.py":
            continue
        first = path.read_text(encoding="utf-8").splitlines()[0]
        if first.startswith('"""') and first.endswith('"""') and len(first) > 6:
            return path.relative_to(repo).as_posix(), first, first[:-3] + ' (reviewed)"""'
    raise Halt("no module with a one-line docstring for the manipulation check")


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
