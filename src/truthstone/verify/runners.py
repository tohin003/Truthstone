"""Test-runner detection and result parsing (SPEC §19, §20).

A deliberate design choice sits at the centre of this module: **Truthstone reads the
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

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from truthstone.repo.index import RepoIndex
from truthstone.repo.paths import relative_path
from truthstone.verify import commands, parsers


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
    background: bool = False  # launched to run on after the command returned (G7)
    # The failing tests the output names, as node ids (G2b): a failure whose tests a later
    # passing run covers, one by one, is fixed even when that run was narrower.
    failing_tests: tuple[str, ...] = ()
    # The environment changes the run was launched with (``commands.TestInvocation.environment``;
    # day 5): () for none, None when not known (a run rebuilt from storage, whose stored command
    # may be cut short). And the tests its summary counted as skipped, None without a summary.
    environment: tuple[str, ...] | None = None
    skipped: int | None = None
    # The skipped tests whose printed skip reason names the environment switch that runs them
    # (``parsers.switch_skips``; day 5): (``NAME=value``, the test as the output names it, the
    # reason). Read only from a run that counted skips; empty for a run rebuilt from storage.
    switch_skips: tuple[tuple[str, str, str], ...] = ()

    @property
    def is_failure(self) -> bool:
        return self.passed is False

    @property
    def suite(self) -> str:
        return self.family or self.runner


# -- the stored verification detail (R14) ------------------------------------------------
#
# A conclusive run is persisted as a verification row, and after a daemon restart the
# engine rebuilds the task's `TestOutcome`s from it. G2a's timeline compares runs by
# family, key and scope, so the row has to carry all of them, not just a summary line.
# The store keeps a string to 200 characters and a list to 10 items (`summarize_value`)
# and cuts the whole JSON at 4,000 bytes, so the detail is bounded here, below those
# limits: whatever a reader gets back is exactly what was written.

DETAIL_KEYS = (
    "command", "summary", "failed", "runner", "passed", "total", "exit_code", "family", "key",
    "scope", "failing_files",
)
DETAIL_TEXT = 200  # characters kept of each string: the store's own limit
DETAIL_ITEMS = 10  # items kept of each list: the store's own limit
DETAIL_BYTES = 3_500  # under the row's 4,000 bytes, with room for redaction markers


def outcome_detail(outcome: TestOutcome) -> dict[str, Any]:
    """The verification detail stored for a conclusive run, bounded so it round-trips.

    ``{"command", "summary", "failed", "runner", "passed", "total", "exit_code",
    "family", "key", "scope", "failing_files"}``. Long lists are capped (the latest
    items dropped first, until the JSON fits ``DETAIL_BYTES``).
    """

    def text(value: Any) -> str:
        return str(value or "")[:DETAIL_TEXT]

    def count(value: Any) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    detail: dict[str, Any] = {
        "command": text(outcome.command),
        "summary": text(outcome.summary),
        "failed": count(outcome.failed),
        "runner": text(outcome.runner),
        "passed": bool(outcome.passed),
        "total": count(outcome.total),
        "exit_code": outcome.exit_code if isinstance(outcome.exit_code, int) else None,
        "family": text(outcome.family),
        "key": text(outcome.key),
        "scope": [text(item) for item in outcome.scope[:DETAIL_ITEMS]],
        "failing_files": [text(item) for item in outcome.failing_files[:DETAIL_ITEMS]],
    }
    while len(json.dumps(detail, default=str)) > DETAIL_BYTES:
        longest = max(("scope", "failing_files"), key=lambda name: len(detail[name]))
        if not detail[longest]:
            break  # only the fixed-size strings are left, and they always fit
        detail[longest].pop()
    return detail


def outcome_from_detail(detail: dict[str, Any], status: str = "") -> TestOutcome | None:
    """A `TestOutcome` rebuilt from a stored detail, or None when it says too little.

    Rows written before the full detail (``{"command", "summary", "failed"}``) still
    rebuild: the command is re-read for its runner, family, key and scope, and the row's
    ``status`` ("passed" / "failed") gives the verdict when ``passed`` is missing.
    """
    if not isinstance(detail, dict):
        return None
    command = detail.get("command")
    if not isinstance(command, str) or not command:
        return None
    passed = detail.get("passed")
    if not isinstance(passed, bool):
        if status not in ("passed", "failed"):
            return None
        passed = status == "passed"

    def text(name: str) -> str:
        value = detail.get(name)
        return value if isinstance(value, str) else ""

    def count(name: str) -> int:
        value = detail.get(name)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    def items(name: str) -> tuple[str, ...]:
        value = detail.get(name)
        return tuple(item for item in value if isinstance(item, str)) if isinstance(value, list) else ()

    invocation = commands.test_invocation(command)
    exit_code = detail.get("exit_code")
    return TestOutcome(
        runner=text("runner") or (invocation.runner if invocation else "unknown"),
        passed=passed,
        total=count("total"),
        failed=count("failed"),
        summary=text("summary"),
        command=command,
        exit_code=exit_code if isinstance(exit_code, int) and not isinstance(exit_code, bool) else None,
        family=text("family") or (invocation.family if invocation else ""),
        key=text("key") or (invocation.key if invocation else ""),
        scope=items("scope") if "scope" in detail else (invocation.selectors if invocation else ()),
        failing_files=items("failing_files"),
    )


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
    # Runs launched into the background (`run_in_background`, a trailing `&`): pending,
    # not unreadable. Whether one is still running is the host's to say at Stop (G7).
    background: list[TestOutcome] = field(default_factory=list)

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
        outcome.environment = invocation.environment
    summary = parsers.parse(runner, output or "")
    if summary is None:
        return outcome
    outcome.total = summary.total
    outcome.failed = summary.failed + summary.errors
    outcome.skipped = summary.skipped
    if summary.skipped:
        outcome.switch_skips = parsers.switch_skips(output or "")
    if summary.status == "no_tests":
        outcome.summary = f"no tests ran ({summary.line})" if summary.line else "no tests ran"
        return outcome
    outcome.passed = summary.status == "passed"
    outcome.summary = summary.line
    if outcome.passed is False:
        outcome.failing_files = parsers.failing_files(output or "")
        outcome.failing_tests = parsers.failing_tests(output or "")
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
    if invocation.background:
        outcome.passed, outcome.background = None, True
        outcome.summary = "launched in the background; no result yet"
        return outcome
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
        outcome.failing_tests = outcome.failing_tests or parsers.failing_tests(text)
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
    """What the task's test runs say, read in order. At most one verdict is set."""

    failing: TestOutcome | None = None  # the latest conclusive run of a suite failed
    open_failure: TestOutcome | None = None  # a failure no later passing run covered...
    narrower_pass: TestOutcome | None = None  # ...because the latest pass was narrower
    stale: list[str] = field(default_factory=list)  # changed after the last pass that checked them
    stale_against: TestOutcome | None = None  # the latest pass the stale files were checked by
    # Changed files that no passing run reached: every pass named test paths that do not
    # include a test covering them (G2b).
    unreached: list[str] = field(default_factory=list)
    latest_pass: TestOutcome | None = None
    changed_after_failure: list[str] = field(default_factory=list)
    # Failing runs that only cleared part of the environment, read past (day 5, ``probes_set_aside``).
    set_aside: list[TestOutcome] = field(default_factory=list)

    @property
    def conclusive(self) -> bool:
        return self.failing is not None or self.latest_pass is not None


def covers(later: TestOutcome, earlier: TestOutcome) -> bool:
    """Whether a passing run re-checked everything an earlier run checked.

    The whole suite covers anything; the same command covers itself; otherwise the later
    run may not add a filter the earlier one lacked (``-k``, ``--lf``, ``-run``), and
    every path the earlier run named must lie inside a path the later one named. So a
    filtered or ``::id`` run supersedes only the identical command or a narrower one.
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
    return path == outer or path.startswith((outer + "/", outer + "::", outer + ".", outer + "["))


# -- failing test ids (G2b) ------------------------------------------------------------------


def _same_file(file: str, selector: str) -> bool:
    """A test file and a command-line path naming it, either possibly relative to a
    different folder (``cd backend && pytest tests/x.py`` against ``backend/tests/x.py``)."""
    if not file or not selector:
        return False
    return file == selector or file.endswith("/" + selector) or selector.endswith("/" + file)


def _id_within(test_id: str, selector: str) -> bool:
    """Whether a run naming ``selector`` (a folder, file or node id) ran ``test_id``."""
    selector = selector.removesuffix("/...")
    test_file, _, test_rest = test_id.partition("::")
    selector_file, _, selector_rest = selector.partition("::")
    in_folder = test_file.startswith(selector_file + "/") or ("/" + selector_file + "/") in ("/" + test_file)
    if not (_same_file(test_file, selector_file) or (in_folder and not selector_rest)):
        return False
    if not selector_rest or in_folder:
        return True
    return test_rest == selector_rest or test_rest.startswith((selector_rest + "::", selector_rest + "["))


def _ids_cleared(failure: TestOutcome, later: list[TestOutcome]) -> bool:
    """Every test a failing run named was re-run by a later passing run (G2b).

    Only when the output named all of its failures (as many ids as the summary counted),
    and only by runs whose paths name them: a ``-k``/``-m``/``--lf`` run says nothing
    about which tests it ran.
    """
    ids = set(failure.failing_tests)
    if not ids or failure.failed <= 0 or len(ids) < failure.failed:
        return False

    def ran(run: TestOutcome, test_id: str) -> bool:
        if not run.scope:
            return True
        paths, filters = _split_scope(run.scope)
        return not filters and any(_id_within(test_id, path) for path in paths)

    return all(any(run.passed and ran(run, test_id) for run in later) for test_id in ids)


# -- what a narrowed run verifies (G2b) ------------------------------------------------------
#
# A run with path arguments verifies only what those paths reach: Truthstone itself
# suggests `pytest tests/test_x.py`, and that must verify the files test_x covers, while
# `pytest tests/test_unrelated.py` must not (D1 scenario C; Pebble guard.py:121-155, where
# a narrowed pass is no evidence at all). Only runners whose positional arguments are test
# paths, path patterns or packages are judged; anything the gate cannot read — a `-k`/
# `-m`/`--lf` filter alone, a glob, a path the index does not know, another runner's
# arguments — counts as reaching the file: could not tell is never a block.

SELECTOR_STYLE: dict[str, str] = {
    "pytest": "path",
    "unittest": "module",
    "mocha": "path",
    "node": "path",
    "deno": "path",
    "rspec": "path",
    "minitest": "path",
    "phpunit": "path",
    "mix": "path",
    "jest": "pattern",
    "vitest": "pattern",
    "bun": "pattern",
    "npm": "pattern",
    "playwright": "pattern",
    "go": "package",
}
_GLOB = re.compile(r"[*?{]")
_LINE = re.compile(r":\d+(?::\d+)?$")


def selector_target(selector: str, style: str) -> str:
    """The file or folder a command-line selector names: ``tests/x.py::t`` -> ``tests/x.py``,
    ``spec/x_spec.rb:12`` -> ``spec/x_spec.rb``, ``tests.test_x.T`` -> ``tests/test_x/T``."""
    target = selector.partition("::")[0]
    if style == "path":
        target = _LINE.sub("", target)
    elif style == "module" and "/" not in target and not target.endswith(".py"):
        target = target.replace(".", "/")
    elif style == "package":
        target = target.removesuffix("/...")
    return target


def selects(selector: str, test: str, style: str) -> bool:
    """Whether a run naming ``selector`` runs the test file ``test`` (or the changed file
    itself: a doctest module, ``vitest related src/x.ts``)."""
    target = selector_target(selector, style)
    if not target or target == ".":
        return False
    if style == "pattern":
        return target in test
    if style == "package":
        folder = test.rpartition("/")[0]
        return _same_file(folder, target) or folder.startswith(target + "/")
    if style == "module" and not test.endswith(".py"):
        return False
    stem = test.removesuffix(".py") if style == "module" else test
    if _same_file(stem, target) or _same_file(test, target):
        return True
    if style == "module" and target.startswith(stem + "/"):
        return True  # a class or method inside the module
    return test.startswith(target + "/") or ("/" + target + "/") in ("/" + test)


def run_reaches(
    run: TestOutcome,
    path: str,
    tests: set[str] | frozenset[str],
    known: Callable[[str, str], bool],
) -> bool:
    """Whether a run verifies a change to ``path``, given the test files that cover it.

    ``known(target, style)`` says whether a selector names something the index knows (a
    file, a folder of files, a pattern matching a test file). Only when every selector is
    known and none reaches a covering test (or the file itself) is the answer False.
    """
    if not run.scope:
        return True
    paths, _ = _split_scope(run.scope)
    style = SELECTOR_STYLE.get(run.runner)
    if not paths or style is None or any(_GLOB.search(item) for item in paths):
        return True
    targets = {path, *tests}
    if any(selects(selector, test, style) for selector in paths for test in targets):
        return True
    return not all(known(selector_target(selector, style), style) for selector in paths)


# -- a cleared-environment probe (day 5) ---------------------------------------------------------
#
# Having run the suite green, an agent sometimes probes how the code fares with part of its
# environment taken away: a search path or a setting cleared (`NAME= pytest`), a variable unset
# (`env -u NAME pytest`). That run fails for what was taken away, and because it came last it
# decided the suite: an honest "the tests pass" was held over the probe. The same two runs read in
# the other order (probe, then the plain run) already passed. So a failing run whose environment
# changes all clear or unset something is read past when the suite's latest plain run (no change
# to the environment at all):
#   * passed after the task's last file change, so it ran the code the probe ran;
#   * covers the probe (``covers``: the whole suite, the same command, or a wider one);
#   * counted no skipped test and at least as many tests as the probe ran: every test the probe
#     ran, it ran and passed.
# Everything else decides as before. A run that *sets* a value (`FLAG=1 pytest`) is never read past:
# setting a value is how gated tests and code paths are switched on, and those the plain run never
# exercised. Nor is a probe after a later change, a probe wider than the plain run, a probe whose
# counts are unknown, or one beside a plain run that failed, skipped tests or is stale.


def probes_set_aside(suite_runs: list[TestOutcome], latest_change: int) -> list[TestOutcome]:
    """The failing cleared-environment runs of one suite (in order) that its latest plain pass
    already answers (see above)."""
    plain = [run for run in suite_runs if run.environment == ()]
    if not plain:
        return []
    anchor = plain[-1]
    if not (
        anchor.passed is True
        and anchor.seq is not None
        and anchor.seq > latest_change
        and anchor.skipped == 0
        and anchor.total > 0
    ):
        return []
    return [
        run
        for run in suite_runs
        if run.passed is False
        and run.seq is not None
        and run.seq > anchor.seq
        and commands.clears_only(run.environment or ())
        and covers(anchor, run)
        and 0 < run.total <= anchor.total
    ]


def assess_timeline(
    verification: VerificationState,
    last_change_seq: dict[str, int],
    candidates: set[str],
    reaches: Callable[[TestOutcome, str], bool] | None = None,
    unchanged_since: Callable[[str, TestOutcome], bool] | None = None,
) -> Timeline:
    """Read the runs per suite, in order; ``candidates`` are the changed files a re-run
    would check (the gate filters out files no test reaches).

    0. A failing run that only cleared part of the environment, after a plain pass on the same
       code that ran every test it ran, is read past (``probes_set_aside``): ``set_aside``.
    1. A suite's latest conclusive run failed → ``failing`` (the most recent such run).
    2. The latest runs passed, but an earlier failure was never re-run by a pass that
       covers it (the green run was narrower) → ``open_failure``/``narrower_pass``. A
       failure whose output named every failing test is also closed when later passes
       re-ran each of those tests (G2b).
    3. Otherwise, per candidate (G2b): a run after its last change that ``reaches`` it
       verifies it — any recognised run, even one whose result could not be read: could
       not tell is never a failure. Failing that, if a pass before the change reached it,
       it is ``stale`` — unless ``unchanged_since`` says its code is what that pass ran
       on (a comment-only edit). If no pass ever reached it, it is ``unreached``.

    ``reaches`` defaults to "every run reaches every file" and ``unchanged_since`` to
    "never": G2a's behaviour.
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
    latest_change = max(last_change_seq.values(), default=0)
    set_aside: list[TestOutcome] = []
    for suite_runs in suites.values():
        probes = probes_set_aside(suite_runs, latest_change)
        if probes:
            set_aside.extend(probes)
            suite_runs = [run for run in suite_runs if not any(run is probe for probe in probes)]
        latest = suite_runs[-1]
        if latest.passed is False:
            failing.append(latest)
            continue
        passes.append(latest)
        for index, run in enumerate(suite_runs):
            if run.passed is not False:
                continue
            later = [other for other in suite_runs[index + 1 :] if other.passed]
            if not any(covers(other, run) for other in later) and not _ids_cleared(run, later):
                open_failures.append((run, latest))

    if failing:
        worst = max(failing, key=lambda outcome: position[id(outcome)])
        after = (
            sorted(p for p in candidates if last_change_seq.get(p, 0) > worst.seq)
            if worst.seq is not None
            else []
        )
        return Timeline(failing=worst, changed_after_failure=after, set_aside=set_aside)
    latest_pass = max(passes, key=lambda outcome: position[id(outcome)])
    if open_failures:
        failure, narrower = max(open_failures, key=lambda pair: position[id(pair[0])])
        return Timeline(
            open_failure=failure, narrower_pass=narrower, latest_pass=latest_pass, set_aside=set_aside
        )
    if any(outcome.seq is None for outcome in runs):
        return Timeline(latest_pass=latest_pass, set_aside=set_aside)  # runs recorded without a position

    reach = reaches or (lambda run, path: True)
    unchanged = unchanged_since or (lambda path, run: False)
    passing = [outcome for outcome in runs if outcome.passed]
    unread = [
        outcome
        for outcome in (*verification.inconclusive, *verification.background)
        if outcome.seq is not None
    ]
    stale: list[str] = []
    against: list[TestOutcome] = []
    unreached: list[str] = []
    for path in sorted(candidates):
        changed_at = last_change_seq.get(path, 0)
        if any(run.seq > changed_at and reach(run, path) for run in (*passing, *unread)):
            continue
        before = [run for run in passing if run.seq <= changed_at and reach(run, path)]
        if not before:
            unreached.append(path)
        elif not unchanged(path, before[-1]):
            stale.append(path)
            against.append(before[-1])
    return Timeline(
        stale=stale,
        stale_against=max(against, key=lambda run: run.seq) if against else None,
        unreached=unreached,
        latest_pass=latest_pass,
        set_aside=set_aside,
    )


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
