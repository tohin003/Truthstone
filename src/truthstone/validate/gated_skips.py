"""Tests the change broke, left unrun behind an environment switch, under a "done" (day 5).

The failure class
-----------------
The agent's last full test run passes with some tests skipped, and the runner prints why: the
skip reason says "set NAME=1 to run". Nothing after the last change sets NAME. The agent says
done. With NAME set, the skipped tests fail, and because of the change: a validation that now
rejects a data file the gated end-to-end tests load, say. The Completion Gate saw a green full run
and passed it, because a skipped test is neither a failure nor a pass.

What is checked
---------------
At a Stop, cheaply and before anything runs (``_candidate``), all of:

1. the final message claims completion, and ``failing_tests`` was not raised in this task yet;
2. the latest passing full run (no selectors) after the task's last change counted skipped tests,
   and the skip reasons printed in that run's own output name exactly one environment switch, in
   an explicit form (``parsers.switch_skips``: ``set NAME=v``, ``export NAME=v``, ``NAME=v to
   run``, ``NAME=v to enable``; never a README, a CI file or a guess); no conclusive run after it
   failed (the gate decides those);
3. no test run after the last change set that switch, or could have (``source``, ``set -a``, an
   exporting ``declare``, an unknown environment);
4. neither the switch name nor the skip reasons suggest credentials or live services
   (``denied``): such tests are never run by the guard;
5. the final message does not say that those tests fail or were not run (``disclosed``; a plain
   "3 skipped" is not a disclosure that they fail);
6. the command is one this module can run again as the agent ran it (pytest, ``node --test``, or a
   package script that runs ``node --test``), from the repository root, and every file the task
   changed has its task-start text on record (``verify/baseline.py``).

Only then (``_rerun``) does the guard run that same command with the switch set, twice and in
parallel, inside ``original_tests``' sandbox: once on a copy of the working tree, once on a copy
whose changed files have their task-start text back (files the task created are removed). It
speaks, as ``failing_tests`` (b), when the first run fails in tests the agent's run skipped behind
the switch and the second run passes with those tests run: the change made them fail.

Safety and cost
---------------
Nothing runs unless 1 to 6 hold, so an ordinary Stop costs a scan of the task's recorded runs.
What runs is the agent's own test command plus one environment variable (and, for pytest, a report
option, ``-rfEs``, that only changes what is printed), never in the agent's tree: a copy, under
``sandbox-exec`` (macOS) with no network and writes allowed only to the copy and the temporary
directories (``original_tests._profile``), with environment variables whose names suggest
credentials dropped. Its program is found on the agent's own PATH (a login shell's, ``_agent_path``),
not only on the daemon's. Both runs share one wall-clock budget (``BUDGET_S``, the original-tests
check's); past it their process groups are killed; the restored-tree run is not waited for when the
gated tests pass. Each result is computed once per task and run. Anything that cannot be settled
(no sandbox, a timeout, a run that cannot be read) is silence, logged at INFO.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from truthstone.core.enums import FailureMode, ReasonCategory, Severity
from truthstone.core.models import EvidenceRef
from truthstone.core.taskstate import TaskState
from truthstone.repo.index import RepoIndex
from truthstone.validate import original_tests as sandbox
from truthstone.verify import baseline, claims, commands, parsers, runners

log = logging.getLogger(__name__)

__all__ = ["BUDGET_S", "concerns", "denied", "disclosed"]

BUDGET_S = sandbox.BUDGET_S  # copies and both runs: the per-check budget (Stop itself has 12 s, G32)
_CATEGORY = ReasonCategory.FAILING_TESTS
MAX_SHOWN = 3
MAX_MEMO = 64
_PACKAGE_MANAGERS = ("npm", "pnpm", "yarn")
_CROSS = chr(0x2716) + " "  # how node's spec reporter marks a failing test


# -- what the switch may not touch -------------------------------------------------------------------
#
# Tests are often kept behind a switch because they are slow or reach real services. The guard runs
# only those whose switch name and skip reasons suggest neither credentials nor live services.
DENIED_WORDS = frozenset(
    {
        "token", "tokens", "key", "keys", "apikey", "secret", "secrets", "password", "passwords", "passwd",
        "credential", "credentials", "creds", "auth", "oauth", "login",
        "network", "net", "internet", "online", "http", "https", "live", "prod", "production", "remote",
        "deploy", "deployment", "staging", "cloud", "external", "sandbox",
        "aws", "s3", "gcp", "gcloud", "gcs", "azure", "heroku", "vercel", "netlify", "cloudflare",
        "digitalocean", "firebase", "supabase",
    }
)  # fmt: skip
_DENIED_TEXT = re.compile(r"\b(?:" + "|".join(sorted(DENIED_WORDS)) + r")\b|://", re.I)


def denied(name: str, reasons: list[str] | tuple[str, ...] = ()) -> bool:
    """Whether a switch (its name, its skip reasons) suggests credentials or live services."""
    parts = {part for part in re.split(r"[^a-z0-9]+", name.lower()) if part}
    return bool(parts & DENIED_WORDS) or any(_DENIED_TEXT.search(reason) for reason in reasons)


# -- the final message ---------------------------------------------------------------------------------

_SENTENCES = re.compile(r"(?<=[.!?;])\s+|\n+")
_FAILS = re.compile(
    r"\b(?:fail(?:s|ed|ing|ures?)?|broken|break(?:s|ing)?|broke|red|erroring|errors?\s+out)\b", re.I
)
_NO_FAILURE = re.compile(
    r"\b(?:no|zero|0|without|none|nothing|never)\s+(?:\w+\s+){0,2}?(?:fail\w*|broken|break\w*|red)\b"
    r"|\bfail(?:ed|ures?|s)?\s*[:=]?\s*0\b"
    r"|\b(?:was|were|had\s+been|previously|used\s+to|no\s+longer)\s+(?:(?!already\b)\w+\s+){0,2}?"
    r"(?:fail\w*|red|broken)\b"
    r"|\b(?:fix(?:ed|es)?|resolv(?:ed|es)|repair(?:ed|s)?)\s+(?:\w+\s+){0,3}?fail\w*",
    re.I,
)
_NOT_RUN = re.compile(
    r"\bun(?:run|runnable|tested|verified|exercised)\b"
    r"|\bnot\s+(?:been\s+|yet\s+|being\s+)?(?:run|ran|executed|exercised|tested|verified|covered|enabled)\b"
    r"|\b(?:did(?:n'?t|\s+not)|have(?:n'?t|\s+not)|has(?:n'?t|\s+not)|could(?:n'?t|\s+not)|can'?t|cannot|"
    r"was(?:n'?t|\s+not)|were(?:n'?t|\s+not)|never)\s+(?:\w+\s+){0,2}?"
    r"(?:run|ran|execute[ds]?|exercised?|enabled?|set|tested|verif(?:y|ied)|cover(?:ed)?)\b"
    r"|\bwithout\s+(?:running|setting|enabling|exercising)\b",
    re.I,
)
_CAVEAT = re.compile(
    r"\bpass\w*\b[^.!?\n]{0,40}?\b(?:except|but\s+for|apart\s+from|other\s+than|aside\s+from|save\s+for)\b",
    re.I,
)
_ABOUT_TESTS = re.compile(r"\b(?:tests?|specs?|suites?|checks?|skip\w*|e2e|end-to-end|integration)\b", re.I)


def disclosed(message: str | None, name: str, tests: list[str] | tuple[str, ...] = ()) -> bool:
    """Whether the final message says the switch-gated tests fail or were not run: a sentence about
    tests (or naming the switch or one of ``tests``) with a failure word that is not negated ("0
    failed", "no failures"), a not-run phrase ("did not run", "without setting", "unverified"), or
    a pass with an exception. A count of skipped tests is neither."""
    if not isinstance(message, str) or not message.strip():
        return False
    names = [n for n in (_title(test) for test in tests) if len(n) >= 6]
    for sentence in _SENTENCES.split(message[: claims.MAX_MESSAGE]):
        about = _ABOUT_TESTS.search(sentence) or name in sentence or any(n in sentence for n in names)
        if not about:
            continue
        if _NOT_RUN.search(sentence) or claims._UNVERIFIED.search(sentence) or _CAVEAT.search(sentence):
            return True
        if _FAILS.search(_NO_FAILURE.sub(" ", sentence)):
            return True
    return False


def _title(test: str) -> str:
    """A test's own name: the title of ``path::title``, the name of a pytest id, a label as is."""
    return test.rsplit("::", 1)[-1].split("[", 1)[0].strip()


# -- the check -----------------------------------------------------------------------------------------


@dataclass(slots=True)
class _Candidate:
    run: runners.TestOutcome
    name: str
    value: str
    labels: tuple[str, ...]  # the tests the run skipped behind the switch, as its output names them
    reasons: tuple[str, ...]
    words: list[str]  # the agent's command, to run again (its program resolved at run time)
    shown: str  # that command, as the agent is told it
    environment: dict[str, str]  # the run's own assignments (``CI=1 npm test``)
    venv: str | None  # the virtualenv the run activated (``source .venv/bin/activate``)
    restore: dict[str, str | None]  # changed file -> its task-start text (None: the task created it)


@dataclass(slots=True)
class _Result:
    failing: list[str]  # gated tests that fail with the switch set, on the final tree
    summary: str
    error: str


_MEMO: dict[tuple, _Result | None] = {}


def concerns(state: TaskState, index: RepoIndex) -> list:
    """The switch-gated failing-tests concern of this task, if any (``verify/arbiter.py`` IntegrityCheck)."""
    from truthstone.verify import arbiter

    message = arbiter.final_message()
    try:
        found = _candidate(state, index, message)
    except Exception:  # an integrity check never fails the hook (logged, then silence)
        log.info("truthstone: switch-gated tests check skipped", exc_info=True)
        return []
    if found is None:
        return []
    key = (state.task_id, state.session_id, state.started_at, found.run.seq, found.name, found.value)
    if key in _MEMO:
        result = _MEMO[key]
    else:
        if not sandbox.sandbox_available():
            log.info("truthstone: switch-gated tests not run: no sandbox on this machine")
            return []
        started = time.monotonic()
        try:
            result = _rerun(found, index)
        except Exception:
            log.info("truthstone: switch-gated tests check failed; silent", exc_info=True)
            result = None
        log.info(
            "truthstone: switch-gated tests %s=%s run in %.2fs: %s",
            found.name,
            found.value,
            time.monotonic() - started,
            f"{len(result.failing)} failing" if result else "silent",
        )
        while len(_MEMO) >= MAX_MEMO:
            _MEMO.pop(next(iter(_MEMO)))
        _MEMO[key] = result
    if result is None:
        return []
    if disclosed(message, found.name, [*found.labels, *result.failing]):
        log.info("truthstone: switch-gated tests fail, and the final message says so")
        return []
    return [_concern(arbiter, found, result)]


def _candidate(state: TaskState, index: RepoIndex, message: str) -> _Candidate | None:
    """Conditions 1 to 6 (see the module docstring), from what the task recorded; nothing runs."""
    if str(_CATEGORY) in state.raised_categories:
        return None  # raised once already: it would not speak again
    if not claims.classify(message).claims:
        return None
    latest_change = max(state.last_change_seq.values(), default=0)
    if not latest_change:
        return None  # nothing changed: nothing to blame
    verification = state.verification
    conclusive = sorted(
        (r for r in verification.outcomes if r.passed is not None and r.seq is not None), key=lambda r: r.seq
    )
    full = [r for r in conclusive if r.passed is True and not r.scope and r.seq > latest_change]
    if not full:
        return None
    run = full[-1]
    if not run.switch_skips or not run.skipped or run.environment is None:
        return None
    if any(r.passed is False and r.seq > run.seq for r in conclusive):
        return None  # a later failure: the gate's own evidence decides
    switches = {switch for switch, _label, _reason in run.switch_skips}
    if len(switches) != 1:
        return None  # more than one switch: none is "the" switch
    switch = switches.pop()
    name, _, value = switch.partition("=")
    gated = [(label, reason) for item, label, reason in run.switch_skips if item == switch]
    labels, reasons = tuple(label for label, _ in gated), tuple(reason for _, reason in gated)
    others = [*verification.outcomes, *verification.inconclusive, *verification.background]
    if any(_may_set(other, name, run) for other in others if other.seq is None or other.seq > latest_change):
        return None
    if denied(name, reasons):
        log.info("truthstone: switch-gated tests not run: %s suggests credentials or live services", name)
        return None
    if disclosed(message, name, labels):
        return None
    root = Path(index.root)
    command = _command(run, root)
    if command is None:
        return None
    words, shown, environment, venv = command
    restore = _restorable(state)
    if restore is None:
        return None
    return _Candidate(run, name, value, labels, reasons, words, shown, environment, venv, restore)


_OPAQUE = re.compile(
    r"^(?:source|\.)\s|^set -a$|^(?:declare|typeset|readonly|local) -x$|^export(?:\s|$)|^unset$"
)


def _may_set(other: runners.TestOutcome, name: str, run: runners.TestOutcome) -> bool:
    """Whether a run after the last change set the switch, or may have."""
    if other.seq is None or other.environment is None:
        return True  # cannot tell
    if re.search(rf"(?<![\w$]){re.escape(name)}(?![\w])", other.command or ""):
        return True
    if any(re.search(rf"(?<![\w$]){re.escape(name)}(?![\w])", item) for item in other.environment):
        return True
    if other is run or any(item.startswith(name + "=") for item, _l, _r in other.switch_skips):
        return False  # it skipped them itself: the switch was not on
    return any(_OPAQUE.search(item) for item in other.environment)


_ACTIVATE = re.compile(r"^(?:source|\.)\s+(?:\./)?(?P<venv>[\w.-]+(?:/[\w.-]+)*)/bin/activate$")
_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _command(
    run: runners.TestOutcome, root: Path
) -> tuple[list[str], str, dict[str, str], str | None] | None:
    """The agent's own command, to run again from the repository root: (its words, as shown, its own
    environment assignments, the virtualenv it activated). None for anything this module does not
    run as the agent did: another folder, a ``bash -c`` script, an environment it cleared or
    sourced, a runner other than pytest, ``node --test`` or a package script that runs it."""
    command = run.command or ""
    if not command or len(command) >= 200:
        return None  # stored cut short: not the command that ran
    invocation = commands.test_invocation(command)
    if invocation is None or invocation.key != run.key or invocation.selectors:
        return None
    for part in commands.split(command):
        words = commands._strip_prefixes(list(part.words))[0]
        if words and commands._program(words[0]) in ("cd", "pushd", "popd"):
            return None  # run from another folder
        if commands._shell_script(words) is not None:
            return None  # inside ``bash -c``: where and how it ran is not read here
    environment: dict[str, str] = {}
    venv: str | None = None
    for item in invocation.environment:
        assigned = _ASSIGN.match(item)
        activate = _ACTIVATE.match(item)
        if assigned:
            environment[assigned.group(1)] = assigned.group(2).strip("'\"")
        elif activate and (root / activate.group("venv") / "bin").is_dir():
            venv = str(root / activate.group("venv"))
        else:
            return None  # cleared, unset, sourced or reset: not reproduced here
    words = list(invocation.argv)
    program = commands._program(words[0])
    shown = " ".join(words)
    if invocation.runner == "pytest" and any(commands._program(w) in ("pytest", "py.test") for w in words):
        # The agent's own options, then a report option (the last ``-r`` wins) that names every
        # failure, error and skip in the short summary: it changes what is printed, not what runs.
        return [*words, "-rfEs"], shown, environment, venv
    if invocation.runner == "node" and program == "node" and "--test" in words:
        return words, shown, environment, venv
    if (
        invocation.runner == "npm"
        and program in _PACKAGE_MANAGERS
        and sandbox._script_runs_node_test(command, root)
    ):
        return words, shown, environment, venv
    return None


# -- the agent's PATH ------------------------------------------------------------------------------------
#
# The daemon's own PATH is often not the agent's: the benchmark starts it with ``/usr/bin:/bin``, where
# neither node nor the task's Python is. Codex runs every command as ``$SHELL -lc``, so the agent's
# PATH is a login shell's: asked once per shell and HOME (inside the sandbox, within the budget),
# then the daemon's own PATH after it.

_PATHS: dict[tuple[str, str], str] = {}
_MARK = "truthstone-path:"


def _agent_path(deadline: float, writable: list[str]) -> str:
    shell = os.environ.get("SHELL") or "/bin/zsh"
    key = (shell, os.environ.get("HOME", ""))
    if key not in _PATHS:
        login = _login_path(shell, deadline, writable)
        if login:
            _PATHS[key] = login  # kept only when it answered: a busy machine asks again next time
    parts = [*_PATHS.get(key, "").split(os.pathsep), *os.environ.get("PATH", "").split(os.pathsep)]
    return os.pathsep.join(dict.fromkeys(part for part in parts if part.startswith("/")))


def _login_path(shell: str, deadline: float, writable: list[str]) -> str | None:
    """A login shell's PATH, or None (no such shell, no answer within a second, or no PATH)."""
    if not os.path.isabs(shell) or not os.access(shell, os.X_OK):
        return None
    timeout = min(1.0, deadline - time.monotonic())
    if timeout <= 0:
        return None
    env = {key: value for key, value in os.environ.items() if not denied(key)}
    try:
        process = subprocess.Popen(
            [
                sandbox.SANDBOX_EXEC,
                "-p",
                sandbox._profile(writable),
                shell,
                "-lc",
                f'printf "\\n{_MARK}%s\\n" "$PATH"',
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return None
    try:
        out, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _reap(process)
        return None
    for line in out.decode("utf-8", "replace").splitlines():
        if line.startswith(_MARK) and "/" in line:
            return line[len(_MARK) :].strip()
    return None


def _resolve(word: str, root: Path, path: str) -> str | None:
    """The program a command word names, as the agent's shell finds it: a path relative to the
    repository root, or the first match on ``path``."""
    if "/" in word:
        full = Path(word).expanduser()
        full = full if full.is_absolute() else root / full
        return str(full) if full.is_file() and os.access(full, os.X_OK) else None
    return shutil.which(word, path=path)


def _restorable(state: TaskState) -> dict[str, str | None] | None:
    """Every changed file's task-start text (None: created by the task), or None when one is not on
    record: a file first changed by a shell command, deleted, binary or too large."""
    out: dict[str, str | None] = {}
    for path in sorted(state.changed_files):
        base = state.file_baselines.get(path)
        if base is None or base.changed_before:
            return None
        if not base.exists:
            out[path] = None
            continue
        text = baseline.before_text(state, path)
        if text is None:
            return None
        out[path] = text
    return out or None


# -- the two runs --------------------------------------------------------------------------------------


def _environment(found: _Candidate, tmp: Path, path: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("PYTEST_ADDOPTS", "NODE_OPTIONS", "FORCE_COLOR") and not denied(key)
    }
    env["PATH"] = path
    if found.venv:
        env["VIRTUAL_ENV"] = found.venv
    env.update(found.environment)
    # Output only: no colour, and lines wide enough that pytest's summary keeps the failure message.
    env.update(PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1", COLUMNS="240", TMPDIR=str(tmp))
    env[found.name] = found.value
    return env


def _start(
    found: _Candidate, argv: list[str], path: str, cwd: Path, tmp: Path, writable: list[str], out: Path
) -> subprocess.Popen:
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


def _reap(process: subprocess.Popen) -> None:
    """Kill whatever is left of a run's process group (a server a test started, say)."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)
    if process.poll() is None:
        sandbox._kill(process)


def _rerun(found: _Candidate, index: RepoIndex) -> _Result | None:
    """Both runs, in parallel, within ``BUDGET_S``; the result when it speaks, else None."""
    deadline = time.monotonic() + BUDGET_S
    root = Path(index.root)
    work = Path(tempfile.mkdtemp(prefix="truthstone-gated-"))
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
        if time.monotonic() > deadline:
            return None
        writable = sorted({str(work.resolve()), os.path.realpath(tempfile.gettempdir()), "/private/tmp"})
        path = _agent_path(deadline, writable)
        if found.venv:
            path = os.pathsep.join([str(Path(found.venv) / "bin"), path])
        program = _resolve(found.words[0], root, path)
        if program is None:
            log.info("truthstone: switch-gated tests not run: %s is not on the agent's PATH", found.words[0])
            return None
        argv = [program, *found.words[1:]]
        outputs = (work / "final.out", work / "base.out")
        processes = [
            _start(found, argv, path, final, work / "final-tmp", writable, outputs[0]),
            _start(found, argv, path, base, work / "base-tmp", writable, outputs[1]),
        ]
        if not _finished(processes[0], deadline):
            return None
        final_out = _read(outputs[0])
        failing = _gated_failures(found, final_out)
        if not failing:
            return (
                None  # the gated tests pass with the change (or the run cannot be read): no need of the other
            )
        if not _finished(processes[1], deadline):
            return None
        return _judge(found, final_out, _read(outputs[1]), failing, final, os.path.dirname(program))
    finally:
        for process in processes:
            _reap(process)
        shutil.rmtree(work, ignore_errors=True)


def _read(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(sandbox.MAX_OUTPUT_BYTES).decode("utf-8", "replace")
    except OSError:
        return ""


def _finished(process: subprocess.Popen, deadline: float) -> bool:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return False
    try:
        process.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        return False
    return True


def _gated_failures(found: _Candidate, final_out: str) -> list[str]:
    """The gated tests that fail on the final tree with the switch set; empty when the run passed,
    failed only elsewhere, or cannot be read."""
    after = parsers.parse(found.run.runner, final_out)
    if after is None:
        log.info("truthstone: switch-gated tests: the run could not be read; silent")
        return []
    if after.status != "failed":
        return []
    return [test for test in parsers.failing_tests(final_out) if _gated(test, found.labels)]


def _judge(
    found: _Candidate, final_out: str, base_out: str, failing: list[str], final: Path, bin_dir: str = ""
) -> _Result | None:
    """Speaks when the restored tree passes with the switch on, and ran the gated tests there (none
    still skipped behind the switch). Anything else, including output that cannot be read, is None."""
    before = parsers.parse(found.run.runner, base_out)
    if before is None or before.status != "passed":
        return None  # unreadable, or it failed without the change too: not this change's doing
    switch = f"{found.name}={found.value}"
    still = [label for item, label, _r in parsers.switch_skips(base_out) if item == switch]
    if any(_gated(test, still) for test in failing):
        return None  # the switch did nothing on the restored tree
    after = parsers.parse(found.run.runner, final_out)
    # Shown relative: the copy's own paths, and the runner's install folder (``.../bin/node`` is node).
    prefixes = {str(final.resolve()) + "/", str(final) + "/"} | (
        {bin_dir + "/"} if len(bin_dir) > 1 else set()
    )
    failing = [_relative(test, prefixes) for test in failing]
    return _Result(failing, after.line if after else "", _first_error(final_out, failing[0], prefixes))


def _gated(test: str, labels: list[str] | tuple[str, ...]) -> bool:
    """Whether a failing test id (``path::title`` or a pytest node id) is one the agent's run skipped
    behind the switch, by how its output named those: a title, a node id, or ``path:line``."""
    path, _, rest = test.partition("::")
    title = _title(test)
    for label in labels:
        if "::" in label:
            if label.split("[", 1)[0] == test.split("[", 1)[0]:
                return True
        elif re.fullmatch(r"\S+:\d+", label):
            where = label.rsplit(":", 1)[0]
            if path == where or path.endswith("/" + where) or where.endswith("/" + path):
                return True
        elif label in (rest, title):
            return True
    return False


def _relative(text: str, prefixes: set[str]) -> str:
    for prefix in sorted(prefixes, key=len, reverse=True):  # /private/var/... before /var/...
        text = text.replace(prefix, "")
    return text


def _first_error(output: str, test: str, prefixes: set[str]) -> str:
    """The first line the runner printed under the failing test: pytest's short-summary message, or
    the first line under node's failing ``<cross> <title>`` (spec) or its ``error:`` (TAP)."""
    title = _title(test)
    lines = parsers.clean(output).split("\n")
    for at, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("FAILED ", "ERROR ")) and title in stripped and " - " in stripped:
            return _clip(_relative(stripped.split(" - ", 1)[1], prefixes))
        spec_failure = at > 0 and lines[at - 1].strip().startswith("test at")
        if title and spec_failure and stripped.startswith(_CROSS + title):
            # Its first two lines: node's own phrase ("Got unwanted exception.", "Command failed: ...")
            # often leaves the reason to the next one. Never a stack frame.
            follow = [later.strip() for later in lines[at + 1 : at + 6] if later.strip()]
            follow = [text for text in follow if not text.startswith("at ")][:2]
            return _clip(_relative(" | ".join(follow), prefixes), 240)
        if stripped.startswith("not ok ") and title in stripped:
            for n, later in enumerate(lines[at + 1 : at + 40], start=at + 1):
                if not later.strip().startswith("error:"):
                    continue
                rest = later.strip()[len("error:") :].strip()
                if rest in ("|-", "|", ">-", ">"):  # a YAML block: its more-indented lines
                    indent = len(later) - len(later.lstrip())
                    block = []
                    for follow in lines[n + 1 : n + 6]:
                        if follow.strip() and len(follow) - len(follow.lstrip()) <= indent:
                            break
                        block.append(follow.strip())
                    rest = " | ".join(part for part in block if part)
                return _clip(_relative(rest.strip("'\""), prefixes), 240)
    return ""


def _clip(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


# -- what the agent is told ------------------------------------------------------------------------------


def _concern(arbiter, found: _Candidate, result: _Result) -> object:
    switch = f"{found.name}={found.value}"
    listing = "\n".join(f"  - {test}" for test in result.failing[:MAX_SHOWN])
    more = f"\n  - and {len(result.failing) - MAX_SHOWN} more" if len(result.failing) > MAX_SHOWN else ""
    error = f"\n  first error: {result.error}" if result.error else ""
    text = (
        f"Your last full run, `{found.shown}`, skipped tests whose skip reason says to set {switch}, and "
        "no run after your last change set it. Truthstone ran "
        f"`{switch} {found.shown}` on a copy of your tree, and these fail:\n{listing}{more}{error}\n"
        "With the files this task changed restored to how the task found them, the same run passes: "
        "this change makes them fail."
    )
    finish = (
        f"Accepted finishes: fix the cause, check with `{switch} {found.shown}`, and finish; or finish "
        f'with "not done: <which tests fail with {switch}, and why>".'
    )
    finding = arbiter.finding(
        _CATEGORY,
        Severity.HIGH,
        summary=(
            f"{len(result.failing)} test(s) skipped behind {found.name} fail with it set, "
            "because of the change"
        ),
        detail=f"`{switch} {found.shown}`: {result.summary}; " + "; ".join(result.failing[:8]),
        evidence=[
            EvidenceRef(source="tests", path=test.partition("::")[0] or None, symbol=_title(test))
            for test in result.failing[:MAX_SHOWN]
        ],
        mode=FailureMode.OVERLOOKED_REGRESSION,
    )
    return arbiter.Concern(_CATEGORY, text, finding, finish=finish)
