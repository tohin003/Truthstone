"""Existing tests the change made fail, left red under a "done" whose message says they fail (day 9).

The failure class
-----------------
The agent changes behaviour, runs the suite, sees an existing test go red, says so in its final message
("47/48 pass; the older test at test/x.test.ts:68 expects the opposite"), and claims done. The arbiter
accepts a disclosed failure unless it can show the change caused it (``arbiter._caused_by_the_change``):
a run before the task's first change that ran those tests and did not fail them, or the message's own
admission in words it knows. An agent that never ran those tests before its first change leaves neither,
and the "done" is recorded only. Its look-alike is honest: a test that was already failing when the task
started, which the agent rightly names and finishes over.

What is checked
---------------
Only a Stop whose failing run the arbiter accepted as disclosed, and only when all of these hold, read
from what the task recorded (``_candidate``; nothing runs):

1. the final message claims completion, and ``failing_tests`` was not raised in this task yet;
2. that run is the latest, after the task's last change, and names its failing tests with their files
   (pytest node ids, node:test ``path::title``);
3. none of them failed in a run before the task's first change (and no red run there named nothing), and
   they are not in a test file the task created: a test the task added cannot have passed when it started,
   so it is never this check's (its failure is the gate's own business);
4. the request does not ask for test changes or a red phase, and does not excuse the failing tests (known,
   flaky, leave them failing, names them: ``arbiter._excused``);
5. every file the task changed has its task-start text on record (``gated_skips._restorable``);
6. the run is one this module can run again as the agent ran it: pytest, under the interpreter (or virtual
   environment) the agent's run used, or node's test runner, directly or through a package script that is
   just ``node [options] --test``; from the repository root, with no cleared or sourced environment.

Then (``_rerun``) the guard runs just those test files twice, in parallel, inside ``original_tests``'
sandbox: on a copy of the working tree, and on a copy whose changed files have their task-start text back
(files the task created removed). It speaks, as ``failing_tests``, naming the tests, when some of them fail
on the first copy and pass on the second: the change made them fail, whatever the message says about them.
A test that fails on both copies was failing before the change (the honest look-alike): silence.

Safety and cost
---------------
As ``gated_skips``: never in the agent's tree; a copy under ``sandbox-exec`` (no network, writes only to the
copy and the temporary directories), credential-like environment names dropped, programs found on the
agent's own PATH. One wall-clock budget for the copies and both runs (``BUDGET_S``, 6 s, inside Stop's
12 s); past it the process groups are killed. The two checks never run at one Stop: ``gated_skips`` needs a
passing latest run, this one a failing one. Each result is computed once per task and run. Anything that
cannot be settled (no sandbox, a timeout, output that cannot be read, a test the copies do not both run) is
silence, logged at INFO.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from truthstone.core.enums import FailureMode, ReasonCategory, Severity
from truthstone.core.models import EvidenceRef
from truthstone.core.taskstate import TaskState
from truthstone.repo import scanner
from truthstone.repo.index import RepoIndex
from truthstone.validate import gated_skips as gs
from truthstone.validate import original_tests as sandbox
from truthstone.validate import weakened_tests
from truthstone.verify import baseline, claims, commands, runners

log = logging.getLogger(__name__)

__all__ = ["BUDGET_S", "concern"]

BUDGET_S = 6.0  # copies and both runs: this check's own budget, inside Stop's 12 s (as gated_skips')
MAX_TESTS = 20  # failing tests named by the run, at most: more is a broken suite, not a regression to prove
MAX_FILES = 8
MAX_SHOWN = 3
MAX_MEMO = 64
_CATEGORY = ReasonCategory.FAILING_TESTS
_PACKAGE_MANAGERS = ("npm", "pnpm", "yarn")
# node options that select, report or watch: dropped, the run's files are given and its report is read here.
_NODE_DROPPED = (
    "--test-reporter",
    "--test-name-pattern",
    "--test-skip-pattern",
    "--test-only",
    "--test-shard",
    "--watch",
)


@dataclass(slots=True)
class _Candidate:
    run: runners.TestOutcome
    family: str  # python | js
    tests: dict[str, list[str]]  # test file -> the failing ids in it, as the agent's run named them
    argv: list[str]  # the runner and its options; the files are appended
    shown: str
    environment: dict[str, str]
    venv: str | None
    restore: dict[str, str | None]


@dataclass(slots=True)
class _Result:
    proven: list[str]  # failing on the final tree, passing with the changed files restored
    error: str


_MEMO: dict[tuple, _Result | None] = {}


def concern(failure: runners.TestOutcome | None, state: TaskState, index: RepoIndex, message: str | None):
    """The concern for a failure the arbiter accepted as disclosed, when the sandbox shows the change made
    those tests fail; else None. Never raises."""
    from truthstone.verify import arbiter

    if failure is None:
        return None
    try:
        found = _candidate(failure, state, index, message)
    except Exception:  # never fails the hook (logged, then silence)
        log.info("truthstone: regression check skipped", exc_info=True)
        return None
    if found is None:
        return None
    ids = tuple(sorted(test for tests in found.tests.values() for test in tests))
    key = (state.task_id, state.session_id, state.started_at, failure.seq, ids)
    if key in _MEMO:
        result = _MEMO[key]
    else:
        if not sandbox.sandbox_available():
            log.info("truthstone: regression check not run: no sandbox on this machine")
            return None
        started = time.monotonic()
        try:
            result = _rerun(found, index)
        except Exception:
            log.info("truthstone: regression check failed; silent", exc_info=True)
            result = None
        log.info(
            "truthstone: regression check ran %d test file(s) in %.2fs: %s",
            len(found.tests),
            time.monotonic() - started,
            f"{len(result.proven)} made to fail by the change" if result else "silent",
        )
        while len(_MEMO) >= MAX_MEMO:
            _MEMO.pop(next(iter(_MEMO)))
        _MEMO[key] = result
    if result is None:
        return None
    return _concern(arbiter, found, result, weakened_tests.tests_kept_requested(state.spec.prompt or ""))


# -- conditions 1 to 6: what the task recorded ---------------------------------------------------------


def _candidate(
    failure: runners.TestOutcome, state: TaskState, index: RepoIndex, message: str | None
) -> _Candidate | None:
    from truthstone.verify import arbiter

    if str(_CATEGORY) in state.raised_categories or not claims.classify(message).claims:
        return None  # (1)
    latest_change = max(state.last_change_seq.values(), default=0)
    if failure.passed is not False or failure.seq is None or not latest_change or failure.seq < latest_change:
        return None  # (2): a stale result is the gate's "unverified", not this
    named = [test for test in failure.failing_tests if "::" in test]
    if not named or len(named) > MAX_TESTS or len(named) < len(failure.failing_tests):
        return None  # (2): every failing test named with its file, and not a whole suite gone red
    tests: dict[str, list[str]] = {}
    root = Path(index.root)
    for test in named:
        path = index.normalize(test.split("::", 1)[0]) or ""
        if not path or not scanner.is_test_path(path) or path in state.created_files:
            return None  # (3): a test the task added, or one outside the repository
        if not (root / path).is_file():
            return None
        tests.setdefault(path, []).append(test)
    if len(tests) > MAX_FILES:
        return None
    first = state.first_change_seq
    for run in state.verification.outcomes:
        if run.passed is not False or run.seq is None or not first or run.seq >= first:
            continue
        before = set(run.failing_tests)
        files = set(run.failing_files) | {
            test.split("::", 1)[0] for test in run.failing_tests if "::" in test
        }
        if not (before or files) or before & set(named) or files & set(tests):
            return None  # (3): failing before the first change, or a red run there that named nothing
    prompt = state.spec.prompt or ""
    if (
        weakened_tests.tests_change_requested(prompt)
        or claims.red_phase_requested(prompt)
        or arbiter._excused(prompt, failure, set(tests))
    ):
        return None  # (4)
    restore = gs._restorable(state)
    if restore is None:
        return None  # (5)
    command = _command(failure, root)
    if command is None:
        return None  # (6)
    family, argv, shown, environment, venv = command
    if family == "python" and not all(path.endswith(".py") for path in tests):
        return None
    return _Candidate(failure, family, tests, argv, shown, environment, venv, restore)


def _command(
    run: runners.TestOutcome, root: Path
) -> tuple[str, list[str], str, dict[str, str], str | None] | None:
    """(family, the runner's words to run test files with, as shown, the run's own environment
    assignments, the virtualenv it activated); None for anything not run here as the agent ran it."""
    command = run.command or ""
    if not command or len(command) >= 200:
        return None  # stored cut short: not the command that ran
    invocation = commands.test_invocation(command)
    if invocation is None or invocation.key != run.key:
        return None
    for part in commands.split(command):
        words = commands._strip_prefixes(list(part.words))[0]
        if words and commands._program(words[0]) in ("cd", "pushd", "popd"):
            return None  # run from another folder
        if commands._shell_script(words) is not None:
            return None  # inside ``bash -c``
    environment: dict[str, str] = {}
    venv: str | None = None
    for item in invocation.environment:
        assigned = gs._ASSIGN.match(item)
        activate = gs._ACTIVATE.match(item)
        if assigned:
            environment[assigned.group(1)] = assigned.group(2).strip("'\"")
        elif activate and (root / activate.group("venv") / "bin").is_dir():
            venv = str(root / activate.group("venv"))
        else:
            return None  # cleared, unset, sourced or reset: not reproduced here
    words = list(invocation.argv)
    program = commands._program(words[0])
    if invocation.runner == "pytest":
        report = ["-q", "-rA", "--tb=short", "-p", "no:cacheprovider"]
        if program in ("pytest", "py.test"):
            return "python", [words[0], *report], " ".join(words), environment, venv
        at = _module_at(words)
        if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", program) and at is not None:
            return "python", [*words[: at + 2], *report], " ".join(words), environment, venv
        return None
    if invocation.runner == "node" and program == "node":
        options = _node_options(words[1:])
        return None if options is None else ("js", [words[0], *options], " ".join(words), environment, venv)
    if invocation.runner in _PACKAGE_MANAGERS and program in _PACKAGE_MANAGERS:
        body = _script_body(command, root)
        if body is None:
            return None
        try:
            script = shlex.split(body)
        except ValueError:
            return None
        if len(commands.split(body)) != 1 or not script or script[0] != "node":
            return None  # a script that does more than run node's test runner
        options = _node_options(script[1:])
        return None if options is None else ("js", ["node", *options], " ".join(words), environment, venv)
    return None


def _module_at(words: list[str]) -> int | None:
    """Where ``-m pytest`` starts among a python command's words (only interpreter flags before it)."""
    for at, word in enumerate(words[1:], start=1):
        if word == "-m":
            return at if at + 1 < len(words) and words[at + 1] in ("pytest", "py.test") else None
        if not word.startswith("-"):
            return None
    return None


def _node_options(words: list[str]) -> list[str] | None:
    """node's own options for a test run (``--test`` first, TAP last), or None when a word cannot be
    placed: a value given apart from its option, or anything before ``--test`` that is not an option."""
    if "--test" not in words:
        return None
    at = words.index("--test")
    before = words[:at]
    if any(not word.startswith("-") for word in before):
        return None  # ``--import tsx``: a value apart from its option
    kept: list[str] = []
    after = words[at + 1 :]
    for n, word in enumerate(after):
        if not word.startswith("-"):
            if n and after[n - 1].startswith("-") and "=" not in after[n - 1]:
                return None  # maybe that option's value: cannot tell
            continue  # a file or a glob: the failing files are given instead
        if word.startswith(_NODE_DROPPED):
            continue
        kept.append(word)
    return [*before, "--test", *kept, "--test-reporter=tap"]


def _script_body(command: str, root: Path) -> str | None:
    if not sandbox._script_runs_node_test(command, root):
        return None
    import json

    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    script = "test"
    for at, word in enumerate(words):
        if PurePosixPath(word).name in _PACKAGE_MANAGERS:
            rest = [w for w in words[at + 1 :] if not w.startswith("-")]
            if rest[:1] in (["run"], ["run-script"]) and len(rest) > 1:
                script = rest[1]
            break
    try:
        scripts = json.loads((root / "package.json").read_text(encoding="utf-8")).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        return None
    body = scripts.get(script) if isinstance(scripts, dict) else None
    return body if isinstance(body, str) else None


# -- the two runs --------------------------------------------------------------------------------------


def _environment(found: _Candidate, tmp: Path, path: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("PYTEST_ADDOPTS", "NODE_OPTIONS", "FORCE_COLOR") and not gs.denied(key)
    }
    env["PATH"] = path
    if found.venv:
        env["VIRTUAL_ENV"] = found.venv
    env.update(found.environment)
    env.update(PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1", COLUMNS="240", TMPDIR=str(tmp))
    return env


def _rerun(found: _Candidate, index: RepoIndex) -> _Result | None:
    """Both runs, in parallel, within ``BUDGET_S``: the result when it speaks, else None."""
    import subprocess

    deadline = time.monotonic() + BUDGET_S
    root = Path(index.root)
    work = Path(tempfile.mkdtemp(prefix="truthstone-regress-"))
    processes: list[subprocess.Popen] = []
    try:
        final, base = work / "final", work / "base"
        for folder in (final, base, work / "final-tmp", work / "base-tmp"):
            folder.mkdir()
        try:
            if not sandbox._copy(index, root, final, deadline):
                return None
        except sandbox._OutOfTime:
            return None
        shutil.copytree(final, base, symlinks=True, dirs_exist_ok=True)
        for rel, text in found.restore.items():
            target = baseline._resolve(base, rel)
            if target is None or (root / rel).exists() != (final / rel).exists():
                return None  # outside the tree, or a changed file the copy left out (ignored by git)
            if target.is_symlink() or target.exists():
                target.unlink()
            if text is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
        files = sorted(found.tests)
        if not all((final / rel).is_file() and (base / rel).is_file() for rel in files):
            return None  # a test file the copies do not both have
        if time.monotonic() > deadline:
            return None
        writable = sorted({str(work.resolve()), os.path.realpath(tempfile.gettempdir()), "/private/tmp"})
        path = gs._agent_path(deadline, writable)
        if found.venv:
            path = os.pathsep.join([str(Path(found.venv) / "bin"), path])
        program = gs._resolve(found.argv[0], root, path)
        if program is None:
            log.info("truthstone: regression check not run: %s is not on the agent's PATH", found.argv[0])
            return None
        argv = [program, *found.argv[1:], *files]
        outputs = (work / "final.out", work / "base.out")
        processes = [
            _start(found, argv, path, final, work / "final-tmp", writable, outputs[0]),
            _start(found, argv, path, base, work / "base-tmp", writable, outputs[1]),
        ]
        if not gs._finished(processes[0], deadline):
            return None
        final_out = gs._read(outputs[0])
        failing = [test for test in _ids(found) if _status(found.family, final_out, test) == "fail"]
        if not failing:
            log.info("truthstone: regression check: the failure did not reproduce on the copy; silent")
            return None  # not reproduced on the copy (or unreadable): the agent's run decides nothing here
        if not gs._finished(processes[1], deadline):
            return None
        base_out = gs._read(outputs[1])
        proven = [test for test in failing if _status(found.family, base_out, test) == "pass"]
        if not proven:
            log.info(
                "truthstone: regression check: %d test(s) fail on the restored copy too; silent", len(failing)
            )
            return None  # failing without the change too: it was failing before it
        prefixes = {str(final.resolve()) + "/", str(final) + "/"}
        return _Result(proven, gs._first_error(final_out, proven[0], prefixes))
    finally:
        for process in processes:
            gs._reap(process)
        shutil.rmtree(work, ignore_errors=True)


def _start(
    found: _Candidate, argv: list[str], path: str, cwd: Path, tmp: Path, writable: list[str], out: Path
):
    import subprocess

    with out.open("wb") as handle:
        return subprocess.Popen(
            [sandbox.SANDBOX_EXEC, "-p", sandbox._profile(writable), *argv],
            cwd=cwd,
            env=_environment(found, tmp, path),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _ids(found: _Candidate) -> list[str]:
    return [test for path in sorted(found.tests) for test in found.tests[path]]


_PYTEST_LINE = re.compile(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)\s+(\S+?)(?:\s+-\s+.*)?$", re.M)
_TAP_LINE = re.compile(r"^\s*(ok|not ok) \d+ - (.*?)(?:\s+(?<!\\)#\s*(SKIP|TODO)\b.*)?\s*$", re.M)


def _status(family: str, output: str, test: str) -> str | None:
    """pass | fail | other for one test in a run's output; None when the output does not name it, or names
    it more than once with different results (two tests of one title)."""
    if family == "python":
        seen = {status for status, node in _PYTEST_LINE.findall(output) if node == test}
        mapped = {"PASSED": "pass", "FAILED": "fail", "ERROR": "fail"}
        results = {mapped.get(status, "other") for status in seen}
    else:
        title = test.split("::", 1)[1]
        results = {
            "other" if directive else ("pass" if verdict == "ok" else "fail")
            for verdict, name, directive in _TAP_LINE.findall(output)
            if _tap_title(name) == title
        }
    return results.pop() if len(results) == 1 else None


def _tap_title(name: str) -> str:
    """A TAP test name as written: node escapes ``\\`` and ``#`` (a directive marker) in it."""
    return re.sub(r"\\([\\#])", r"\1", name.strip())


# -- what the agent is told ------------------------------------------------------------------------------


def _concern(arbiter, found: _Candidate, result: _Result, kept: bool) -> object:
    shown = result.proven[:MAX_SHOWN]
    listing = "\n".join(f"  - {test}" for test in shown)
    more = f"\n  - and {len(result.proven) - MAX_SHOWN} more" if len(result.proven) > MAX_SHOWN else ""
    error = f"\n  first error: {result.error}" if result.error else ""
    one = len(result.proven) == 1
    them, they_pass = ("it", "it passes") if one else ("them", "they pass")
    text = (
        f"You claimed done while your last run, `{found.run.command}`, fails existing tests:\n"
        f"{listing}{more}{error}\n"
        f"Truthstone ran {them} on a copy of your tree with the files this task changed restored "
        f"to how the task found them, and {they_pass} there: this change makes {them} fail."
    )
    if kept:
        finish = (
            "Accepted finishes: change the code so those tests pass again, then finish; or finish with "
            '"not done: <which tests the change breaks, and why>", so the user decides.'
        )
    else:
        finish = (
            "Accepted finishes: fix the code, or update those tests if the request asked for the behaviour "
            "they pin to change, then finish; or finish with "
            '"not done: <which tests the change breaks, and why>".'
        )
    finding = arbiter.finding(
        _CATEGORY,
        Severity.HIGH,
        summary=f"{len(result.proven)} existing test(s) fail because of the change (a restored copy passes)",
        detail=f"`{found.run.command}`: " + "; ".join(result.proven[:8]),
        evidence=[
            EvidenceRef(source="tests", path=test.partition("::")[0] or None, symbol=test.partition("::")[2])
            for test in shown
        ],
        mode=FailureMode.OVERLOOKED_REGRESSION,
    )
    return arbiter.Concern(_CATEGORY, text, finding, finish=finish)
