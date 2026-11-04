"""Test-runner detection and result parsing (SPEC §19, §20).

A deliberate design choice sits at the centre of this module: **AgentGuard reads the
agent's own test output rather than running tests itself.**

The reasons are practical and they compound. Running a second test suite concurrently with
the agent's work invites conflicts over ports, fixtures, databases and temp files. It is
slow, on a path that is supposed to be invisible. And it is unnecessary: when the agent
runs `pytest` the output arrives in `PostToolUse`, and that output is ground truth about
whether the tests passed — far better evidence than a claim in a summary message.

It also catches the failure the SPEC cares most about. An agent that runs the suite, sees
two failures, and then says "all tests pass" has been contradicted by an artefact it
produced itself. No re-execution required.

Running the suite independently remains available for Level-3 verification
(`verification.run_tests`), off by default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentguard.repo.index import RepoIndex
from agentguard.repo.paths import relative_path
from agentguard.verify import commands, parsers


@dataclass(slots=True)
class TestRunner:
    name: str  # pytest | jest | vitest | go | cargo | npm
    command: str  # how the agent would invoke it
    evidence: str  # what made us believe it exists


@dataclass(slots=True)
class TestOutcome:
    """What a test command's output actually says."""

    runner: str
    passed: bool | None  # None = ran, but the outcome could not be determined
    total: int = 0
    failed: int = 0
    summary: str = ""
    command: str = ""
    exit_code: int | None = None  # the command's exit status, when the host reported one
    # Where the run sits on the task's timeline (G2a). None: an outcome recorded without
    # a position, which is never judged stale.
    seq: int | None = None
    family: str = ""  # the suite it verifies: python, js, go, rust, ... (commands.py)
    key: str = ""  # the normalised command: what makes two runs "the same run"
    scope: tuple[str, ...] = ()  # what narrowed it (paths, -k, --lf, ...); () = everything
    failing_files: tuple[str, ...] = ()  # test files the output names as failing (G4a)

    @property
    def is_failure(self) -> bool:
        return self.passed is False

    @property
    def suite(self) -> str:
        return self.family or self.runner


@dataclass(slots=True)
class VerificationState:
    """Everything observed about verification during one task, in order.

    ``outcomes`` holds the runs that reached a verdict and ``inconclusive`` the ones that
    did not (interrupted, unreadable, no tests). Nothing here is sticky: the gate reads
    the timeline (``assess_timeline``), so a failure that a later run fixed is history,
    not a verdict.
    """

    outcomes: list[TestOutcome] = field(default_factory=list)
    commands_seen: list[str] = field(default_factory=list)
    inconclusive: list[TestOutcome] = field(default_factory=list)

    @property
    def ran_tests(self) -> bool:
        return bool(self.outcomes)


# -- detection --------------------------------------------------------------------


def detect_runners(index: RepoIndex) -> list[TestRunner]:
    """Which test runners this repository actually has.

    Used to answer a question the Completion Gate must not get wrong: is "no tests were
    run" a problem, or does this project simply have no tests to run? Demanding tests
    that cannot exist would be exactly the nagging SPEC §39 forbids.
    """
    runners: list[TestRunner] = []
    files = index.files

    has_python_tests = any(r.is_test and r.lang == "python" for r in files.values())
    if has_python_tests or "pytest.ini" in files or "tox.ini" in files:
        runners.append(TestRunner("pytest", "pytest", "python test files present"))
    elif "pyproject.toml" in files:
        try:
            manifest = relative_path(index.root, "pyproject.toml")
            if manifest is None:
                return runners
            text = (index.root / manifest).read_text(encoding="utf-8")
            if "[tool.pytest" in text or "pytest" in text:
                runners.append(TestRunner("pytest", "pytest", "pytest configured in pyproject.toml"))
        except OSError:
            pass

    if "package.json" in files:
        try:
            import json

            manifest = relative_path(index.root, "package.json")
            if manifest is None:
                return runners
            data = json.loads((index.root / manifest).read_text(encoding="utf-8"))
            scripts = data.get("scripts") or {}
            dev = {**(data.get("devDependencies") or {}), **(data.get("dependencies") or {})}
            if "vitest" in dev:
                runners.append(TestRunner("vitest", "npx vitest run", "vitest in package.json"))
            elif "jest" in dev:
                runners.append(TestRunner("jest", "npx jest", "jest in package.json"))
            elif "test" in scripts:
                runners.append(TestRunner("npm", "npm test", "test script in package.json"))
        except (OSError, ValueError):
            pass

    if "go.mod" in files:
        runners.append(TestRunner("go", "go test ./...", "go.mod present"))
    if "Cargo.toml" in files:
        runners.append(TestRunner("cargo", "cargo test", "Cargo.toml present"))

    return runners


# -- recognising a test command ---------------------------------------------------
#
# By command position, never by substring (G3a): `grep -n pytest pyproject.toml` is not a
# test run, and `node --test` is. The rules live in `verify/commands.py`.


def is_test_command(command: str) -> bool:
    return commands.is_test_command(command or "")


def runner_for_command(command: str) -> str:
    invocation = commands.test_invocation(command or "")
    return invocation.runner if invocation is not None else "unknown"


# -- parsing output ---------------------------------------------------------------


def output_text(result: Any) -> str:
    """Flatten a tool result into the text a test runner printed.

    Claude Code delivers Bash results as a dict — ``{"stdout": ..., "stderr": ...}`` —
    and pytest writes its summary line to stdout while a failing runner often writes to
    stderr, so both are needed. Confirmed against a captured live payload.
    """
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        keys = [key for key in _TEXT_KEYS if key in result]
        if not keys:
            return str(result)
        return "\n".join(str(result[key]) for key in keys if result[key])
    return "" if result is None else str(result)


_TEXT_KEYS = ("stdout", "stderr", "output", "content")


def parse_output(command: str, output: str) -> TestOutcome:
    """Read a test command's output. `passed=None` means we could not tell.

    Never guesses (G3b). Only a framework's own summary line counts, the last one wins,
    and a run that ran no tests says so in its summary while staying ``passed=None`` —
    "no tests" is never a failure, and never a pass. The Completion Gate treats "could
    not tell" as "not verified" rather than as a failure: accusing an agent of breaking
    tests on the strength of an unparsed string would be worse than silence.
    """
    command = command or ""
    invocation = commands.test_invocation(command)
    runner = invocation.runner if invocation is not None else "unknown"
    outcome = TestOutcome(runner=runner, passed=None, command=command.strip()[:200])
    if invocation is not None:
        outcome.family, outcome.key, outcome.scope = invocation.family, invocation.key, invocation.selectors
    summary = parsers.parse(runner, output or "")
    if summary is None:
        return outcome
    outcome.total = summary.total
    outcome.failed = summary.failed + summary.errors
    if summary.status == "no_tests":
        outcome.summary = f"no tests ran ({summary.line})" if summary.line else "no tests ran"
        return outcome
    outcome.passed = summary.status == "passed"
    outcome.summary = summary.line
    if outcome.passed is False:
        outcome.failing_files = parsers.failing_files(output or "")
    return outcome


# -- exit status first (G1) ----------------------------------------------------------------
#
# A failing run's exit status is the strongest evidence there is, and on Claude Code it
# is often the only evidence: a non-zero Bash exit arrives as PostToolUseFailure, and
# text parsing alone classified only 73 of 281 such real runs (docs/IMPROVEMENTS.md G1).
# But a status belongs to the runner only when the runner is what the command returns
# (`commands.TestInvocation.exit_reliable`): `pytest | tail` exits with tail's status.

# Statuses that say nothing about the tests: the command timed out (124), could not be
# executed (126) or found (127), or was stopped by a signal (SIGHUP 129, SIGINT 130,
# SIGKILL 137, SIGPIPE 141 — `| head` closing early — SIGTERM 143).
NO_VERDICT_EXIT = frozenset({124, 126, 127, 129, 130, 137, 141, 143})


def exit_verdict(runner: str, exit_code: int) -> bool | None:
    """False when this non-zero status means the tests failed; None when it does not say.

    pytest: 1 is failures; 2 interrupted or collection errors, 3 internal error, 4 usage
    error, 5 no tests collected — the text decides those. cargo fails tests with 101,
    nextest with 100 (101: build failed), go with 1 (2: build failed); unittest 5 is
    "no tests". Every other runner fails tests with any non-zero status.
    """
    if exit_code == 0 or exit_code in NO_VERDICT_EXIT:
        return None
    if runner in ("pytest", "hatch"):
        return False if exit_code == 1 else None
    if runner in ("unittest", "django"):
        return False if exit_code == 1 else None
    if runner == "cargo":
        return False if exit_code == 101 else None
    if runner == "nextest":
        return None if exit_code == 4 else False
    if runner == "go":
        return False if exit_code in (1, 2) else None
    return False


def result_fields(result: Any) -> tuple[str, int | None, bool]:
    """(text, exit status, interrupted) from any shape a host delivers.

    The adapter contract is ``{"stdout", "exit_code", "interrupted"}`` (``exit_code`` may
    be None: Codex reports none for Bash). A Claude Code PostToolUse result
    (``{stdout, stderr, interrupted, …}``) has no status, and a plain string is just text.
    """
    if not isinstance(result, dict):
        return output_text(result), None, False
    code = result.get("exit_code", result.get("exitCode"))
    if not isinstance(code, int) or isinstance(code, bool):
        code = None
    return output_text(result), code, bool(result.get("interrupted"))


def outcome_from_result(command: str, result: Any) -> TestOutcome | None:
    """What a shell command's result says about the tests, or None if it ran no tests.

    1. **Interrupted** → ``passed=None``: a stopped run is inconclusive, never a failure.
    2. **The status is known and is the runner's**: 0 takes the parser's verdict (if
       any); a non-zero status fails the run where it means failure for that runner
       (``exit_verdict``). Where it does not (timeouts, pytest's 2 to 5), the text may
       still show a failure — a collection error under pytest's 2 — but never a pass:
       a run that exited non-zero did not pass.
    3. **The status is unknown or belongs to something else** (``| tail``, ``; true``,
       ``|| echo``) → the text's verdict only.
    """
    invocation = commands.test_invocation(command or "")
    if invocation is None:
        return None
    text, exit_code, interrupted = result_fields(result)
    outcome = parse_output(command, text)
    outcome.exit_code = exit_code
    if interrupted:
        outcome.passed = None
        outcome.summary = "the run was interrupted" + (f" ({outcome.summary})" if outcome.summary else "")
        return outcome
    if exit_code is None or exit_code == 0 or not invocation.exit_reliable:
        return outcome
    verdict = exit_verdict(invocation.runner, exit_code)
    if verdict is False:
        outcome.passed = False
        outcome.failed = max(outcome.failed, 1)
        outcome.summary = f"exit status {exit_code}" + (f"; {outcome.summary}" if outcome.summary else "")
        outcome.failing_files = outcome.failing_files or parsers.failing_files(text)
    elif outcome.passed is True:
        outcome.passed = None
        outcome.summary = f"exit status {exit_code} after: {outcome.summary}"
    elif not outcome.summary:
        outcome.summary = f"exit status {exit_code}"
    return outcome


# -- the timeline (G2a) --------------------------------------------------------------------
#
# `any_failed` never forgot, so fail -> fix -> pass ended in "your tests are failing":
# probe B, and 62 of 81 real VERIFICATION_FAILED blocks in the lead's corpus were false
# because the latest run was green (docs/IMPROVEMENTS.md G2a). And a pass was accepted
# however much changed after it (probe C). Pebble's rule (guard.py:710-756): the latest
# run decides, and only a run on the current files counts.


@dataclass(slots=True)
class Timeline:
    """What the task's test runs say, read in order. At most one field is set."""

    failing: TestOutcome | None = None  # the latest conclusive run of a suite failed
    open_failure: TestOutcome | None = None  # a failure no later passing run covered...
    narrower_pass: TestOutcome | None = None  # ...because the latest pass was narrower
    stale: list[str] = field(default_factory=list)  # changed after the latest pass
    latest_pass: TestOutcome | None = None
    changed_after_failure: list[str] = field(default_factory=list)

    @property
    def conclusive(self) -> bool:
        return self.failing is not None or self.latest_pass is not None


def covers(later: TestOutcome, earlier: TestOutcome) -> bool:
    """Whether a passing run re-checked everything an earlier run checked.

    The whole suite covers anything; the same command covers itself; otherwise the later
    run may not add a filter the earlier one lacked (``-k``, ``--lf``, ``-run``), and
    every path the earlier run named must lie inside a path the later one named.
    """
    if not later.scope or (later.key and later.key == earlier.key):
        return True
    if not earlier.scope:
        return False
    later_paths, later_filters = _split_scope(later.scope)
    earlier_paths, earlier_filters = _split_scope(earlier.scope)
    if not later_filters <= earlier_filters:
        return False
    if not later_paths:
        return True
    if not earlier_paths:
        return False
    return all(any(_inside(path, outer) for outer in later_paths) for path in earlier_paths)


def _split_scope(scope: tuple[str, ...]) -> tuple[set[str], set[str]]:
    """(paths, filters). ``-k=x``, ``--lf`` and ``workspace=api`` are filters."""
    filters = {item for item in scope if item.startswith("-") or _OPTION_LIKE.match(item)}
    return set(scope) - filters, filters


_OPTION_LIKE = re.compile(r"^[\w.-]+=")


def _inside(path: str, outer: str) -> bool:
    outer = outer.removesuffix("/...")
    return path == outer or path.startswith((outer + "/", outer + "::", outer + "."))


def assess_timeline(
    verification: VerificationState, last_change_seq: dict[str, int], candidates: set[str]
) -> Timeline:
    """Read the runs per suite, in order; ``candidates`` are the changed files a re-run
    would check (the gate filters out files no test reaches).

    1. A suite's latest conclusive run failed → ``failing`` (the most recent such run).
    2. The latest runs passed, but an earlier failure was never re-run by a pass that
       covers it (the green run was narrower) → ``open_failure``/``narrower_pass``.
    3. Otherwise a candidate changed after the latest run on record → ``stale``. Any
       recognised run counts as "a run after the change", even one whose result could
       not be read: could not tell is never a failure.
    """
    runs = [outcome for outcome in verification.outcomes if outcome.passed is not None]
    if not runs:
        return Timeline()
    position = {id(outcome): index for index, outcome in enumerate(runs)}
    suites: dict[str, list[TestOutcome]] = {}
    for outcome in runs:
        suites.setdefault(outcome.suite, []).append(outcome)

    failing: list[TestOutcome] = []
    open_failures: list[tuple[TestOutcome, TestOutcome]] = []
    passes: list[TestOutcome] = []
    for suite_runs in suites.values():
        latest = suite_runs[-1]
        if latest.passed is False:
            failing.append(latest)
            continue
        passes.append(latest)
        for index, run in enumerate(suite_runs):
            if run.passed is False and not any(
                later.passed and covers(later, run) for later in suite_runs[index + 1 :]
            ):
                open_failures.append((run, latest))

    if failing:
        worst = max(failing, key=lambda outcome: position[id(outcome)])
        after = (
            sorted(p for p in candidates if last_change_seq.get(p, 0) > worst.seq)
            if worst.seq is not None
            else []
        )
        return Timeline(failing=worst, changed_after_failure=after)
    latest_pass = max(passes, key=lambda outcome: position[id(outcome)])
    if open_failures:
        failure, narrower = max(open_failures, key=lambda pair: position[id(pair[0])])
        return Timeline(open_failure=failure, narrower_pass=narrower, latest_pass=latest_pass)
    if any(outcome.seq is None for outcome in runs):
        return Timeline(latest_pass=latest_pass)  # runs recorded without a position
    seen = [outcome.seq for outcome in verification.inconclusive if outcome.seq is not None]
    last_run = max([*(outcome.seq for outcome in passes if outcome.seq is not None), *seen])
    stale = sorted(path for path in candidates if last_change_seq.get(path, 0) > last_run)
    return Timeline(stale=stale, latest_pass=latest_pass)


def affected_tests(
    index: RepoIndex,
    changed: set[str],
    limit: int = 20,
    deleted_coverage: dict[str, set[str]] | None = None,
) -> list[str]:
    """Tests covering the changed files, plus tests of their direct dependents.

    A deleted file is gone from the index, so ``deleted_coverage`` supplies the tests
    that reached it when it was deleted (G5) — those that still exist.
    """
    tests: set[str] = set()
    for path in changed:
        tests.update(index.tests_for(path))
        for dependent in index.dependents_of(path):
            tests.update(index.tests_for(dependent))
        if deleted_coverage and path in deleted_coverage:
            tests.update(test for test in deleted_coverage[path] if test in index.files)
    return sorted(tests)[:limit]


def suggested_command(runners: list[TestRunner], tests: list[str]) -> str:
    """The most specific command that would verify these changes."""
    if not runners:
        return ""
    runner = runners[0]
    if runner.name == "pytest" and tests:
        return f"pytest {' '.join(tests[:6])}"
    return runner.command


def workspace_root(index: RepoIndex) -> Path:
    return index.root
