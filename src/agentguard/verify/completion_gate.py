"""Completion Gate (SPEC §19, §20).

    The agent should not simply say: "Done."

`Stop` fires when the agent believes it has finished. This decides whether the evidence
agrees, and returns one of PASS / INCOMPLETE / VERIFICATION_FAILED /
HUMAN_REVIEW_REQUIRED.

The gate is built to be *quiet by default*, because a completion gate that fires on
ordinary turns is the most annoying thing this project could ship. It holds the turn open
only when there is positive evidence of a problem:

* code changed and the changed files no longer parse
* the agent ran tests, and the output says they failed
* code changed, the project has tests covering it, and nothing was run

Everything else passes silently — including every turn that changed no code, every project
without a test runner, and every case where the evidence is merely unclear. "Could not
tell" is never treated as failure.

Loop safety is structural. `stop_hook_active` tells us a Stop hook is already holding the
session open, and a per-task cap bounds how many times the gate may speak at all. A
disagreement between AgentGuard and the agent must end in the agent proceeding, not in a
loop (SPEC §39).

Seeing and speaking are separate (Phase 7)
------------------------------------------
Every path through this module now also produces `Finding`s tagged with the SPEC §3
failure mode they evidence, and those findings are produced **before** rationing is
applied. Loop safety, the per-task cap and observe-only mode all govern whether the gate
*speaks*; none of them should govern what the census *counts*. Observation is free.

One observation here never speaks at all: §3.15, "write insufficient tests". It is INFO
severity, so nothing surfaces it — it exists to be counted.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from agentguard.core.enums import (
    ChallengeCategory,
    EscalationLevel,
    FailureMode,
    GateResult,
    Severity,
    Verdict,
)
from agentguard.core.models import EvidenceRef, Finding
from agentguard.core.taskstate import TaskState
from agentguard.repo.index import RepoIndex
from agentguard.verify import baseline, claims, commands, runners, static

log = logging.getLogger(__name__)

_BLOCKING = (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


@dataclass(slots=True)
class GateVerdict:
    result: GateResult
    reason: str = ""
    evidence: list[EvidenceRef] = field(default_factory=list)
    # What was observed, regardless of whether it will be said. Census input.
    findings: list[Finding] = field(default_factory=list)
    # The failing run behind a VERIFICATION_FAILED from the agent's tests, if any.
    failure: runners.TestOutcome | None = None
    # Set when rationing muted a blocking verdict: the problem left unresolved (G10).
    unresolved: str = ""

    @property
    def should_block(self) -> bool:
        return self.result is not GateResult.PASS


def evaluate(
    state: TaskState | None,
    index: RepoIndex,
    stop_hook_active: bool = False,
    max_blocks: int = 2,
    message: str | None = None,
    pending_tasks: list[dict] | None = None,
) -> GateVerdict:
    """Decide whether this turn may end. Never raises.

    ``message`` is the agent's final message. A turn that hands back honestly — asks a
    question, or says what is not done or not verified, without claiming completion —
    is not a false completion and is not held (G4a).

    ``pending_tasks`` is what the host says is still running (``AgentEvent.
    pending_tasks``): a test run still in flight is not a result yet (G7).
    """
    if state is None:
        return GateVerdict(GateResult.PASS)

    verdict = _assess(state, index, pending_tasks or [])
    if verdict.should_block:
        verdict = _hand_back(state, verdict, message) or verdict

    # Rationing is applied last, to the *speaking* only. Everything above has already
    # been observed and recorded.
    muted = _muted_reason(state, stop_hook_active, max_blocks)
    if verdict.should_block and muted:
        problem = next((f.summary for f in verdict.findings if f.severity in _BLOCKING), "")
        return GateVerdict(
            GateResult.PASS,
            reason=muted,
            findings=verdict.findings,
            unresolved=problem or verdict.result.value,
        )
    return verdict


def _muted_reason(state: TaskState, stop_hook_active: bool, max_blocks: int) -> str:
    """Why the gate must stay quiet even though it has something to say."""
    if state.stop_blocks >= max_blocks:
        return "completion-gate budget spent"
    if stop_hook_active and state.stop_blocks >= 1:
        return "a stop hook is already holding this turn"
    return ""


def _assess(state: TaskState, index: RepoIndex, pending_tasks: list[dict] | None = None) -> GateVerdict:
    """What the evidence says, before any question of whether to say it."""
    # A file whose bytes are back to how the task found it is no change (G2b): an edit
    # and its revert, or a file created and removed again.
    reverted = baseline.reverted(state, index.root)
    touched = state.touched_files - reverted
    written = touched - state.deleted_files
    changed = {path for path in touched | state.deleted_files if _is_source(path, index)} - reverted
    if not changed:
        return GateVerdict(GateResult.PASS, "no source changes to verify")

    # Independent of the blocking assessment: an agent can run the suite, watch it pass,
    # and still have left new code untested (SPEC §3, "write insufficient tests").
    observations = _insufficient_tests(state, index, changed, written)

    # 1. Does it parse? The cheapest and least arguable failure there is — for files the
    #    task broke (G15). A file that never parsed (a template) is not the task's doing,
    #    and a passing test run after the file's last edit shows the project's own
    #    interpreter parses it, even where the daemon's older one cannot.
    problems = [
        problem
        for problem in static.check_files(index.root, touched)
        if _task_broke(problem.path, state)
    ]
    if problems:
        listing = "; ".join(f"{p.path}:{p.line} {p.message}" for p in problems[:3])
        evidence = [
            EvidenceRef(source="static", path=p.path, line=p.line, note=p.message)
            for p in problems[:5]
        ]
        reason = (
            f"The change leaves {len(problems)} file(s) unparsable: {listing}. "
            "Fix the syntax before finishing."
        )
        return GateVerdict(
            GateResult.VERIFICATION_FAILED,
            reason=reason,
            evidence=evidence,
            findings=[
                _finding(
                    FailureMode.FALSE_COMPLETION,
                    Severity.HIGH,
                    subject="unparsable-on-completion",
                    summary=f"finished with {len(problems)} file(s) that no longer parse",
                    detail=listing,
                    evidence=evidence,
                ),
                *observations,
            ],
        )

    # 2. Is a test run still going? Then there is no result to finish on yet (G7). The
    #    host reports what is still running; a watch mode is never a test run.
    running = _tests_in_flight(pending_tasks or [])
    if running:
        return _in_flight(running, observations)

    # 3. What do the agent's own test runs say, read in order (G2a)? The latest run of
    #    each suite decides; a failure it fixed is history, and a pass the agent edited
    #    past is stale. A run with test paths verifies only what those paths cover, and a
    #    comment-only edit does not make a pass stale (G2b).
    verification = state.verification
    rerun = {path for path in changed if _needs_rerun(path, index, state)}
    timeline = runners.assess_timeline(
        verification,
        state.last_change_seq,
        rerun,
        reaches=_reaches(index, state),
        unchanged_since=lambda path, run: baseline.code_unchanged(state, index.root, path, run.seq),
    )
    if timeline.failing is not None:
        return _failing(timeline, observations)
    unverified = timeline.open_failure is not None or timeline.stale or timeline.unreached
    if unverified and state.spec.tests_waived:
        return GateVerdict(
            GateResult.PASS, "the request explicitly waived running tests", findings=observations
        )
    if timeline.open_failure is not None:
        return _narrower(timeline, observations)
    if timeline.stale:
        return _stale(timeline, observations)
    if timeline.unreached:
        return _off_target(timeline, index, state, observations)

    # 4. The developer asked for tests (G6). Not writing any is not done, whatever ran:
    #    "…has no tests; fix it and add tests" used to waive the gate instead (probe G).
    if state.spec.tests_requested and not _wrote_tests(state, index, written):
        return _requested_tests_missing(observations)

    if timeline.latest_pass is not None:
        return GateVerdict(GateResult.PASS, "tests ran and passed", findings=observations)

    # 5. Nothing was run. Only a problem if there was something to run *and* the
    #    developer did not say not to.
    if state.spec.tests_waived:
        return GateVerdict(
            GateResult.PASS, "the request explicitly waived running tests", findings=observations
        )

    available = runners.detect_runners(index)
    if not available:
        return GateVerdict(GateResult.PASS, "no test runner in this project", findings=observations)

    covering = runners.affected_tests(index, changed, deleted_coverage=state.deleted_coverage)
    if not covering:
        # Changed code that nothing covers. Worth saying once, but it is a gap in the
        # project, not a failure by the agent — so it does not hold the turn open. The
        # §3.15 observation above has already recorded it.
        return GateVerdict(
            GateResult.PASS, "no existing tests cover the changed files", findings=observations
        )

    if verification.commands_seen and not verification.outcomes:
        # A test command ran but its result was unreadable. Unclear is not failed.
        return GateVerdict(
            GateResult.PASS, "test output could not be interpreted", findings=observations
        )
    if verification.background:
        # Launched into the background and no longer running (the host would have said),
        # but its result was never seen here. Could not tell is never failed.
        return GateVerdict(
            GateResult.PASS, "a background test run finished unseen", findings=observations
        )

    command = runners.suggested_command(available, covering)
    evidence = [EvidenceRef(source="tests", path=path) for path in covering[:5]]
    return GateVerdict(
        GateResult.INCOMPLETE,
        reason=(
            f"{len(changed)} file(s) changed and no tests were run, but "
            f"{len(covering)} test file(s) cover this code: {', '.join(covering[:4])}. "
            f"Run them before finishing — `{command}` — and report what they said."
        ),
        evidence=evidence,
        findings=[
            _finding(
                FailureMode.UNVERIFIED_CHANGE,
                Severity.MEDIUM,
                subject="no-test-run",
                summary=f"{len(changed)} file(s) changed and no tests were run",
                detail=f"{len(covering)} test file(s) cover this code: {', '.join(covering[:4])}",
                evidence=evidence,
            ),
            *observations,
        ],
    )


def _task_broke(path: str, state: TaskState) -> bool:
    """Whether an unparsable file is this task's doing (G15).

    Not when it did not parse before the task first changed it, nor when a passing test
    run came after its last change. Without a baseline (no PreToolUse was seen), it is
    blamed, as before.
    """
    if not state.parse_baseline.get(path, True):
        return False
    changed_at = state.last_change_seq.get(path)
    if changed_at is None:
        return True
    return not any(
        outcome.passed and outcome.seq is not None and outcome.seq > changed_at
        for outcome in state.verification.outcomes
    )


# -- the timeline's verdicts (G2a) ---------------------------------------------------


def _failing(timeline: runners.Timeline, observations: list[Finding]) -> GateVerdict:
    failure = timeline.failing
    evidence = [EvidenceRef(source="runtime", note=f"{failure.runner}: {failure.summary}")]
    after = timeline.changed_after_failure
    reason = (
        f"The test run reported failures — `{failure.command}`"
        + (f": {failure.summary}" if failure.summary else "")
        + ". The task is not complete while its own tests are failing."
    )
    if after:
        reason += (
            f" {_listing(after)} changed after that run; re-run `{failure.command}` "
            "to show whether the change fixed it."
        )
    return GateVerdict(
        GateResult.VERIFICATION_FAILED,
        reason=reason,
        failure=failure,
        evidence=evidence,
        findings=[
            _finding(
                FailureMode.FALSE_COMPLETION,
                Severity.HIGH,
                subject="failing-tests-on-completion",
                summary=f"finished while `{failure.command}` was reporting failures",
                detail=failure.summary,
                evidence=evidence,
            ),
            *observations,
        ],
    )


def _narrower(timeline: runners.Timeline, observations: list[Finding]) -> GateVerdict:
    failure, green = timeline.open_failure, timeline.narrower_pass
    evidence = [
        EvidenceRef(source="runtime", note=f"failed: {failure.command}"),
        EvidenceRef(source="runtime", note=f"passed: {green.command}"),
    ]
    return GateVerdict(
        GateResult.INCOMPLETE,
        reason=(
            f"Re-run `{failure.command}`: it reported failures"
            + (f" ({failure.summary})" if failure.summary else "")
            + f", and the latest green run, `{green.command}`, was narrower or ran other tests, so "
            "it does not show that those failures are fixed. Run it before finishing and report "
            "what it said."
        ),
        evidence=evidence,
        findings=[
            _finding(
                FailureMode.UNVERIFIED_CHANGE,
                Severity.MEDIUM,
                subject="narrower-verification",
                summary=f"`{failure.command}` failed and was never re-run; only `{green.command}` passed",
                detail=failure.summary,
                evidence=evidence,
            ),
            *observations,
        ],
    )


def _stale(timeline: runners.Timeline, observations: list[Finding]) -> GateVerdict:
    green, stale = timeline.stale_against or timeline.latest_pass, timeline.stale
    evidence = [EvidenceRef(source="filesystem", path=path) for path in stale[:5]]
    return GateVerdict(
        GateResult.INCOMPLETE,
        reason=(
            f"{_listing(stale)} changed after the last passing test run (`{green.command}`), so "
            f"that run does not cover the final code. Re-run `{green.command}` before finishing "
            "and report what it said."
        ),
        evidence=evidence,
        findings=[
            _finding(
                FailureMode.UNVERIFIED_CHANGE,
                Severity.MEDIUM,
                subject="stale-verification",
                summary=f"{len(stale)} file(s) changed after the last passing test run",
                detail=", ".join(stale[:6]) + ("…" if len(stale) > 6 else ""),
                evidence=evidence,
            ),
            *observations,
        ],
    )


def _off_target(
    timeline: runners.Timeline, index: RepoIndex, state: TaskState, observations: list[Finding]
) -> GateVerdict:
    """Every passing run named test paths, and none of them covers these changes (G2b)."""
    files, green = timeline.unreached, timeline.latest_pass
    tests = _tests_to_run(files, index, state)
    command = runners.suggested_command(runners.detect_runners(index), tests) if tests else ""
    them = "it" if len(files) == 1 else "them"
    run = f"Run `{command}`" if command else f"Run the tests that cover {them}"
    reason = (
        f"{_listing(files)} changed, and the passing test run (`{green.command}`) did not include "
        f"the tests that cover {them}"
        + (f" ({', '.join(tests[:4])})" if tests else "")
        + f". {run} before finishing and report what it said."
    )
    evidence = [EvidenceRef(source="tests", path=path) for path in tests[:5]]
    return GateVerdict(
        GateResult.INCOMPLETE,
        reason=reason,
        evidence=evidence,
        findings=[
            _finding(
                FailureMode.UNVERIFIED_CHANGE,
                Severity.MEDIUM,
                subject="off-target-verification",
                summary=f"{len(files)} changed file(s) were not covered by any passing test run",
                detail=f"passed: {green.command}; covering: {', '.join(tests[:4])}",
                evidence=evidence,
            ),
            *observations,
        ],
    )


def _tests_to_run(files: list[str], index: RepoIndex, state: TaskState) -> list[str]:
    """The tests to suggest for ``files``: those covering them, and any that are tests."""
    tests = set(runners.affected_tests(index, set(files), deleted_coverage=state.deleted_coverage))
    tests |= {path for path in files if _looks_like_test(path, index)}
    return sorted(tests)


def _reaches(index: RepoIndex, state: TaskState) -> Callable[[runners.TestOutcome, str], bool]:
    """`runners.run_reaches` bound to the index, with each file's covering tests worked
    out only when a run with test paths needs them."""
    covering: dict[str, frozenset[str]] = {}
    known = _known_selectors(index)

    def reaches(run: runners.TestOutcome, path: str) -> bool:
        if not run.scope:
            return True  # the whole suite reaches everything
        if path not in covering:
            covering[path] = _covering_targets(path, index, state)
        return runners.run_reaches(run, path, covering[path], known)

    return reaches


def _covering_targets(path: str, index: RepoIndex, state: TaskState) -> frozenset[str]:
    """Test files a run must include to verify a change to ``path`` (G2b). Generous on
    purpose — a run is accepted when it reaches the file through any of them: tests of the
    file and of code that imports it, a few hops out; tests importing it (a test helper);
    for a ``conftest.py``, every test below it."""
    tests = set(index.tests_for(path))
    for dependent in index.blast_radius(path, depth=3):
        tests |= index.tests_for(dependent)
        record = index.files.get(dependent)
        if record is not None and record.is_test:
            tests.add(dependent)
    tests |= {test for test in state.deleted_coverage.get(path, ()) if test in index.files}
    folder, _, name = path.rpartition("/")
    if name == "conftest.py":
        tests |= {
            test
            for test, record in index.files.items()
            if record.is_test and (not folder or test.startswith(folder + "/"))
        }
    return frozenset(tests)


def _known_selectors(index: RepoIndex) -> Callable[[str, str], bool]:
    """``known(target, style)`` for `runners.run_reaches`: whether a command-line selector
    names something in the index. An unknown one could reach anything, so it never counts
    against a run. Cached per target: a task names few."""
    cache: dict[tuple[str, str], bool] = {}

    def known(target: str, style: str) -> bool:
        if (target, style) not in cache:
            cache[(target, style)] = _names_indexed(index, target, style)
        return cache[(target, style)]

    return known


def _names_indexed(index: RepoIndex, target: str, style: str) -> bool:
    if not target or target == "." or target.startswith(("/", "..")):
        return False
    if style == "pattern":
        return any(target in path for path, record in index.files.items() if record.is_test)
    for path in index.files:
        name = path.removesuffix(".py") if style == "module" else path
        if name == target or name.endswith("/" + target):
            return True
        if path.startswith(target + "/") or ("/" + target + "/") in ("/" + path):
            return True
        if style == "module" and target.startswith(name + "/"):
            return True
    return False


# -- runs still in flight (G7) -----------------------------------------------------------

_IN_FLIGHT = frozenset({"running", "pending", "started", "in_progress", "queued"})
_SHELL_TASKS = frozenset({"shell", "bash", "local_bash", "powershell"})


def _tests_in_flight(pending_tasks: list[dict]) -> list[str]:
    """Commands of host background tasks that are test or typecheck runs still going."""
    running = []
    for task in pending_tasks:
        if not isinstance(task, dict):
            continue
        status, kind, command = task.get("status"), task.get("type"), task.get("command")
        if str(status).lower() not in _IN_FLIGHT or not isinstance(command, str):
            continue
        if kind is not None and str(kind).lower() not in _SHELL_TASKS:
            continue
        if commands.test_invocation(command) or commands.typecheck_invocation(command):
            running.append(command.strip()[:200])
    return running


def _in_flight(running: list[str], observations: list[Finding]) -> GateVerdict:
    shown = ", ".join(f"`{command}`" for command in running[:3])
    return GateVerdict(
        GateResult.INCOMPLETE,
        reason=(
            f"Tests are still running in the background ({shown}); wait for the result and "
            "report what it said before finishing."
        ),
        evidence=[EvidenceRef(source="runtime", note=f"still running: {command}") for command in running[:5]],
        findings=[
            _finding(
                FailureMode.UNVERIFIED_CHANGE,
                Severity.MEDIUM,
                subject="tests-in-flight",
                summary=f"finished while {len(running)} test run(s) were still running",
                detail=", ".join(running[:5]),
            ),
            *observations,
        ],
    )


# -- honest hand-backs (G4a) ------------------------------------------------------------


def _hand_back(state: TaskState, verdict: GateVerdict, message: str | None) -> GateVerdict | None:
    """A PASS that records what was seen, when the turn is not a false completion.

    * The message asks a question, or discloses that the work is unverified or failing,
      and claims neither completion nor verification ("I could not make test_x pass.
      Should I mock it?"). Gaming guard: "Done, all tests pass. Anything else?" claims,
      so it gets no exemption.
    * A TDD red phase the developer asked for: the only failures are in test files this
      task created, and the request asked for a failing test or a reproduction.

    Every exemption is recorded as a finding and logged; nothing is silently waived.
    """
    said = claims.classify(message)
    kind = said.hand_back
    if not kind and not said.claims_verified and _red_phase(state, verdict.failure):
        kind = "red phase"
    if not kind:
        return None
    blocking = [f for f in verdict.findings if f.severity in _BLOCKING]
    kept = [f for f in verdict.findings if f.severity not in _BLOCKING]
    what = blocking[0].summary if blocking else verdict.result.value
    log.info("agentguard: completion gate exempted a %s hand-back: %s", kind, what)
    if kind == "red phase":
        exemption = _finding(
            FailureMode.NOT_A_FAILURE,
            Severity.INFO,
            subject="tdd-red-phase",
            summary=f"ended on the requested red phase: {what}",
            detail=", ".join(verdict.failure.failing_files),
        )
    else:
        exemption = _finding(
            FailureMode.UNVERIFIED_CHANGE,
            Severity.LOW,
            subject="honest-hand-back",
            summary=f"handed back with a {kind} instead of claiming completion: {what}",
            detail=verdict.reason[:300],
        )
    return GateVerdict(
        GateResult.PASS,
        reason=f"the agent handed the turn back ({kind}) without claiming completion",
        findings=[exemption, *kept],
    )


def _red_phase(state: TaskState, failure: runners.TestOutcome | None) -> bool:
    if failure is None or not failure.failing_files or not claims.red_phase_requested(state.spec.prompt):
        return False
    from agentguard.repo import scanner

    created_tests = {path for path in state.created_files if scanner.is_test_path(path)}
    return all(
        any(path == mine or mine.endswith("/" + path) or path.endswith("/" + mine) for mine in created_tests)
        for path in failure.failing_files
    )


def _requested_tests_missing(observations: list[Finding]) -> GateVerdict:
    return GateVerdict(
        GateResult.INCOMPLETE,
        reason=(
            "The request asked for tests, and this task wrote none: no test file was added "
            "or changed. Write the tests that were asked for, run them, and report what "
            "they said before finishing."
        ),
        findings=[
            _finding(
                FailureMode.INSUFFICIENT_TESTS,
                Severity.MEDIUM,
                subject="requested-tests-missing",
                summary="the request asked for tests and none were written",
            ),
            *observations,
        ],
    )


def _wrote_tests(state: TaskState, index: RepoIndex, written: set[str]) -> bool:
    """A test file was added or changed during the task: through an edit tool, or by a
    command (a test file in the index modified since the task began)."""
    if any(_looks_like_test(path, index) for path in written):
        return True
    since = int(state.started_at * 1_000_000_000)
    return any(record.is_test and record.mtime_ns >= since for record in index.files.values())


def _listing(paths: list[str]) -> str:
    shown = ", ".join(paths[:4]) + (f" and {len(paths) - 4} more" if len(paths) > 4 else "")
    return f"{len(paths)} file(s) ({shown})" if len(paths) > 1 else shown


def _needs_rerun(path: str, index: RepoIndex, state: TaskState) -> bool:
    """A change a test run would check: a test itself, or code some test reaches. A new
    module nothing tests is not made "stale" by an earlier run; re-running would not
    check it either."""
    return _looks_like_test(path, index) or _has_any_coverage(path, index, state.deleted_coverage)


# -- §3.15 "write insufficient tests" ---------------------------------------------


def _insufficient_tests(
    state: TaskState, index: RepoIndex, changed: set[str], written: set[str]
) -> list[Finding]:
    """Changed code that nothing tests, in a project that does test its code.

    Recorded, never raised — hence INFO. Three conditions, and all three are needed to
    keep this from becoming a complaint about the repository rather than an observation
    about the change:

    * **The project tests itself.** A runner *and* existing test files. In a repository
      with no tests, "no test was written" is the status quo, not a finding.
    * **The agent wrote no tests during this task.** If it touched a test file, it
      engaged with testing and this detector has nothing to say about whether it did so
      sufficiently — that judgement is not deterministic.
    * **Some changed file has no coverage at all**, directly or through a dependent.
      Editing well-covered code without adding a test is ordinary work.

    What this proves is narrow, and the census says so: untested code was changed, not
    that the tests written were inadequate.
    """
    if not any(record.is_test for record in index.files.values()):
        return []
    if not runners.detect_runners(index):
        return []
    if any(_looks_like_test(path, index) for path in written):
        return []

    uncovered = sorted(
        path for path in changed if not _has_any_coverage(path, index, state.deleted_coverage)
    )
    if not uncovered:
        return []

    return [
        _finding(
            FailureMode.INSUFFICIENT_TESTS,
            Severity.INFO,
            subject="untested-change",
            summary=f"{len(uncovered)} changed file(s) have no tests, and none were written",
            detail=", ".join(uncovered[:6]) + ("…" if len(uncovered) > 6 else ""),
            evidence=[EvidenceRef(source="tests", path=path) for path in uncovered[:5]],
        )
    ]


def _looks_like_test(path: str, index: RepoIndex) -> bool:
    record = index.files.get(index.normalize(path))
    if record is not None:
        return record.is_test
    # A test file created during this task and not yet indexed still counts as the agent
    # having written tests. Missing that would turn writing a test into a finding.
    from agentguard.repo import scanner

    return scanner.is_test_path(index.normalize(path))


def _has_any_coverage(
    path: str, index: RepoIndex, deleted_coverage: dict[str, set[str]] | None = None
) -> bool:
    if index.tests_for(path):
        return True
    if deleted_coverage and any(test in index.files for test in deleted_coverage.get(path, ())):
        return True  # deleted, and a test that reached it still exists (G5)
    return any(index.tests_for(dependent) for dependent in index.dependents_of(path))


def _finding(
    mode: FailureMode,
    severity: Severity,
    subject: str,
    summary: str,
    detail: str = "",
    evidence: list[EvidenceRef] | None = None,
) -> Finding:
    return Finding(
        category=ChallengeCategory.TESTABILITY,
        verdict=Verdict.INSUFFICIENT_EVIDENCE,
        failure_mode=mode,
        severity=severity,
        subject=subject,
        summary=summary,
        detail=detail,
        evidence=evidence or [],
        level=EscalationLevel.DEEP_VERIFICATION,
    )


def _is_source(path: str, index: RepoIndex) -> bool:
    """Documentation and configuration changes do not need a test run."""
    record = index.files.get(path)
    if record is None:
        return Path(path).suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java"}
    return record.parsable
