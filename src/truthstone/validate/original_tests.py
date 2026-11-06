"""Existing tests rewritten for behaviour the request did not ask for (day 3, ``original_tests_fail``).

The failure class
-----------------
The request asks for a change and names its inputs ("``slugify("Hello World")`` should give
``hello-world``"). The agent's change also alters what the code does for inputs the request
never mentions, the tests that pinned the old behaviour for those inputs go red, and the agent
rewrites them: a changed expectation, a renamed and recomputed test, a helper or a data file
that now feeds the tests different values. Its own run is green. The original tests, and every
caller that relied on the old behaviour, are not.

A requested behaviour change also makes old tests fail, and updating them is then right. What
separates the two here is the request itself: a legitimate update concerns inputs or values the
request names, a rewrite for unrequested behaviour concerns inputs it never mentions.

What is checked, deterministically
----------------------------------
At a completion claim, when the request does not ask for test changes and names at least one
concrete example (a backticked or quoted span, a code-like identifier, a call, a flag, a path,
a hyphenated token or a number):

1. An existing test file the task changed through the edit tool (the guard's own baseline, so
   never one changed only by a shell command) was changed beyond pure additions: an existing
   test's body changed, a test was deleted or renamed, a module-level statement changed, or the
   file was deleted (``weakened_tests.changes``). A data file under a test directory that changed
   counts too; the test files that name it are run with it.
2. Those files get their baseline text back in a **copy** of the working tree, and only the
   test files among them are run there, with the runner this session itself used (pytest, with
   the interpreter its own runs used; ``node --test``). Any other runner: silence.
3. A test that fails there with an **assertion failure** (not an import, collection or load
   error, and not a test that already failed before the task's first change) is a candidate.
4. It speaks when, for at least one candidate, the request mentions none of the test's input
   literals (strings, numbers of 3+ digits or with a decimal point, keyword-argument and
   object-literal keys, all outside the expected side of its assertions) and none of the values
   its failure report shows. "Mentions": equal, or one inside the other at token boundaries
   (an example inside a value needs 3+ characters with a letter).

Opt-in
------
Off unless ``[challenge] original_tests = true``. Its exemption rests on the request naming the
inputs a legitimate update concerns, and a request that changes behaviour in prose names none of
them: "raise the maximum discount from 50% to 60%" makes a capped-discount test expect another
total, "make the session last 2 hours" turns an expected 60 into 120, "clamp negative quantities
instead of throwing" turns a rejection into a value. Each of those updates speaks here, so the
check stays off until that is settled.

Safety and cost
---------------
Repository code never runs in the agent's working tree, and never unconfined: the copy is run
under ``sandbox-exec`` (macOS) with no network and writes allowed only to the copy and the
temporary directories. Where ``sandbox-exec`` is not available the check is silent. The whole
check (copy and runs) has a hard wall-clock budget, ``BUDGET_S``; past it the process group is
killed and the check is silent. It speaks once per task, on a completion claim; anything it
cannot settle (an unknown runner, a timeout, an error) is silence.
"""

from __future__ import annotations

import ast
import contextlib
import json
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath

from truthstone.core.enums import FailureMode, ReasonCategory, Severity
from truthstone.core.models import EvidenceRef
from truthstone.core.taskstate import TaskState
from truthstone.repo import scanner
from truthstone.repo.index import RepoIndex
from truthstone.validate import weakened_tests

log = logging.getLogger(__name__)

__all__ = ["BUDGET_S", "concerns", "mentioned", "request_examples", "sandbox_available"]

BUDGET_S = 2.5  # the whole check: copy and runs (the Stop forwarder gives up at 4 s)
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
MAX_COPY_FILES = 20_000
MAX_COPY_BYTES = 256_000_000
MAX_READER_FILES = 400  # test files read to find the ones that name a changed data file
MAX_OUTPUT_BYTES = 2_000_000

_PY = weakened_tests._PY
_JS = weakened_tests._JS
_DOCS = (".md", ".rst", ".adoc")
_CATEGORY = ReasonCategory.ORIGINAL_TESTS_FAIL


def concerns(state: TaskState, index: RepoIndex) -> list:
    """The original-tests concern of this task, if any (``verify/arbiter.py`` IntegrityCheck)."""
    from truthstone.verify import arbiter, claims

    if str(_CATEGORY) in state.raised_categories:
        return []  # once per task: never run the tests again
    if not claims.classify(arbiter.final_message()).claims:
        return []  # no completion claim, nothing to hold (and nothing to run)
    prompt = state.spec.prompt or ""
    if weakened_tests.tests_change_requested(prompt):
        return []
    examples = request_examples(prompt)
    if not examples:
        return []  # a request that names nothing gives nothing to tell its inputs from others
    code, data = _rewritten(arbiter.changed_texts(state, index))
    if not code and not data:
        return []
    if not sandbox_available():
        return []  # repository code is never run unconfined
    try:
        found = _failing_originals(state, index, code, data)
    except Exception:  # an integrity check never fails the hook (logged, then silence)
        log.info("truthstone: original-tests check skipped", exc_info=True)
        return []
    if not found:
        return []
    early_ids, early_files = weakened_tests._failed_earlier(state, until=state.first_change_seq or 0)
    unnamed = []
    for item in found:
        if _failed_before(item, early_ids, early_files):
            continue
        # Small numbers count too, matched exactly (a request "from 30 to 60" names the input 30).
        inputs = [v for v in item.inputs if _usable(v) or _NUMERIC.match(v.strip())]
        values = [v for v in item.values if _usable(v) or _NUMERIC.match(v.strip())]
        if any(_mention(v, examples) for v in [*inputs, *values]):
            continue  # the request names what this test checks: its update may be the request's
        item.unnamed = inputs or values
        unnamed.append(item)
    if not unnamed:
        return []
    return [_concern(arbiter, unnamed)]


# -- the request's concrete examples ------------------------------------------------------------------

_BACKTICK = re.compile(r"`([^`\n]{1,200})`")
_DQUOTE = re.compile(r'"([^"\n]{1,200})"|“([^”\n]{1,200})”')
_SQUOTE = re.compile(r"(?:(?<=^)|(?<=[\s(\[{,=:]))'([^'\n]{1,100})'(?=[\s)\]},.;:!?]|$)", re.M)
_WORD = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*")
_CALL = re.compile(r"\b([A-Za-z_][\w.]*)\(")
_FLAG = re.compile(r"(?<![\w-])--?[A-Za-z][\w-]*")
_PATH = re.compile(r"(?<![\w/])[\w.-]+/[\w./-]*\w")
_KEBAB = re.compile(r"(?<![\w-])[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+(?![\w-])")
_NUMBER = re.compile(r"(?<![\w.])[€$£]?\s?\d+(?:[.,]\d+)*%?")
_NUMERIC = re.compile(r"^-?\d+(?:\.\d+)?$")
_QUOTED_INSIDE = re.compile(r'"([^"]{1,100})"|\'([^\']{1,100})\'')


def _code_like(token: str) -> bool:
    """An identifier as code spells it: snake_case, camelCase, dotted, or with a digit."""
    return (
        "_" in token
        or "." in token
        or re.search(r"[a-z][A-Z]", token) is not None
        or re.search(r"[A-Za-z]\d|\d[A-Za-z]", token) is not None
    )


def request_examples(prompt: str | None) -> set[str]:
    """The concrete inputs and examples a request names: backticked and quoted spans, code-like
    identifiers, calls, flags, paths, hyphenated tokens and numbers (and the quoted strings and
    code-like tokens inside those spans)."""
    text = (prompt or "")[:20_000]
    out: set[str] = set()
    out.update(m.group(1).strip() for m in _BACKTICK.finditer(text))
    out.update(m.group(1) or m.group(2) for m in _DQUOTE.finditer(text))
    out.update(m.group(1) for m in _SQUOTE.finditer(text))
    out.update(token for token in _WORD.findall(text) if _code_like(token))
    out.update(m.group(1) for m in _CALL.finditer(text))
    for pattern in (_FLAG, _PATH, _KEBAB):
        out.update(pattern.findall(text))
    out.update(m.group().strip() for m in _NUMBER.finditer(text))
    inner: set[str] = set()
    for example in out:
        inner.update(m.group(1) or m.group(2) for m in _QUOTED_INSIDE.finditer(example))
        inner.update(token for token in _WORD.findall(example) if _code_like(token))
    return {e for e in (" ".join(x.split()) for x in out | inner) if e}


def _bounded(needle: str, hay: str) -> bool:
    return re.search(rf"(?<![0-9A-Za-z]){re.escape(needle)}(?![0-9A-Za-z])", hay) is not None


def mentioned(value: str, examples: set[str]) -> str | None:
    """The example that mentions ``value``: equal to it, ``value`` inside it at token boundaries,
    or it (3+ characters, with a letter) inside ``value`` at token boundaries. None if none."""
    v = " ".join(value.split())
    if len(v) < 2 or not re.search(r"[0-9A-Za-z€$£]", v):
        return None
    for example in examples:
        if v == example or _bounded(v, example):
            return example
        if len(example) >= 3 and re.search(r"[A-Za-z]", example) and _bounded(example, v):
            return example
    return None


def _mention(value: str, examples: set[str]) -> str | None:
    v = value.strip()
    if _NUMERIC.match(v):  # a number is the same number, never a digit of another one
        whole = re.compile(rf"(?<![\d.]){re.escape(v)}(?![\d])")
        return next((e for e in examples if e == v or whole.search(e)), None)
    return mentioned(value, examples)


def _usable(value: str) -> bool:
    v = value.strip()
    if _NUMERIC.match(v):
        return len(v.lstrip("-")) >= 3 or "." in v
    return len(v) >= 2 and re.search(r"[0-9A-Za-z€$£]", v) is not None


# -- what the task rewrote ----------------------------------------------------------------------------


def _rewritten(
    texts: dict[str, tuple[str | None, str | None]],
) -> tuple[dict[str, tuple[str, frozenset[str] | None]], dict[str, str]]:
    """(test-code files, test data files) the task changed beyond pure additions, each with its
    baseline text; a test-code file also with the tests the change touched (None: the whole file,
    for a change outside any test: a helper, a constant, a table, the file deleted). Only files
    with a baseline: an edit-tool change to a file that existed."""
    code: dict[str, tuple[str, frozenset[str] | None]] = {}
    data: dict[str, str] = {}
    for path, (before, after) in texts.items():
        if before is None or not scanner.is_test_path(path):
            continue
        lower = path.lower()
        if lower.endswith(_PY + _JS):
            touched = _touched(path, before, after)
            if touched != frozenset():
                code[path] = (before, touched)
        elif not lower.endswith(_DOCS):
            data[path] = before
    return code, data


def _touched(path: str, before: str, after: str | None) -> frozenset[str] | None:
    """The existing tests the change touched beyond pure additions (empty: none), or None when the
    change reaches the whole file."""
    if after is None:
        return None  # deleted
    items = weakened_tests.changes(path, before, after)
    if items is None:
        return None  # cannot tell: every original test may say it
    tests: set[str] = set()
    for item in items:
        added = item.kind == "test-changed" and item.detail == weakened_tests._EDITED_ADDED
        if added or item.kind == "import-extended":
            continue  # an addition: the original test still runs as it was
        if not item.test:
            return None  # module-level code every test may run against
        tests.add(item.test)
    if path.lower().endswith(_JS):
        old, new = weakened_tests._js_tests(before), weakened_tests._js_tests(after)
        tests.update(title for title in old if title not in new)  # deleted or renamed
    return frozenset(tests)


# -- the session's own runners ------------------------------------------------------------------------

_PY_MODULE_RUN = re.compile(
    r"(?:^|[\s;&|(])((?:[^\s;&|()'\"]*/)?python(?:\d+(?:\.\d+)*)?)(?:\s+-[A-Za-z]+)*\s+-m\s+(?:pytest|py\.test)\b"
)
_PYTEST_RUN = re.compile(r"(?:^|[\s;&|(])((?:[^\s;&|()'\"]*/)?(?:pytest|py\.test))(?=\s|$|[;&|)])")
_NODE_TEST = re.compile(r"\bnode\b[^;&|]*?\s--test\b")
_PACKAGE_MANAGERS = ("npm", "pnpm", "yarn", "bun")


def _runners(state: TaskState, root: Path) -> dict[str, list[str]]:
    """family -> the command prefix to run test files with: pytest under the interpreter this
    session's own runs used (else ``python`` on PATH), ``node --test`` when the session ran
    node:test (directly or through a package script). A runner the session never used: none."""
    runs = [*state.verification.outcomes, *getattr(state.verification, "inconclusive", [])]
    runs.sort(key=lambda run: run.seq if run.seq is not None else -1)
    out: dict[str, list[str]] = {}
    for run in reversed(runs):
        command = run.command or ""
        if "python" not in out and run.runner == "pytest":
            python = _python_for(command, root)
            if python:
                out["python"] = [
                    python, "-m", "pytest", "-q", "-rA", "--tb=short", "-p", "no:cacheprovider",
                    "--continue-on-collection-errors",
                ]
        if "js" not in out and (
            run.runner == "node"
            or (run.runner in _PACKAGE_MANAGERS and _script_runs_node_test(command, root))
        ):
            node = shutil.which("node")
            if node:
                out["js"] = [node, "--test", "--test-reporter=tap"]
    return out


def _python_for(command: str, root: Path) -> str | None:
    """The interpreter a pytest command ran under: ``<python> -m pytest``'s, or the one a
    ``pytest`` script names on its first line; else ``python`` on PATH."""
    found = _PY_MODULE_RUN.search(command)
    if found:
        python = _executable(found.group(1), root)
        if python:
            return python
    else:
        script = _PYTEST_RUN.search(command)
        if script:
            path = _executable(script.group(1), root)
            python = _shebang(path) if path else None
            if python:
                return python
    return shutil.which("python") or shutil.which("python3")


def _executable(token: str, root: Path) -> str | None:
    if "/" in token:
        path = Path(token).expanduser()
        path = path if path.is_absolute() else root / path
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(token)


def _shebang(path: str) -> str | None:
    try:
        with open(path, "rb") as handle:
            first = handle.readline(400).decode("utf-8", "replace")
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    parts = first[2:].split()
    if not parts:
        return None
    if PurePosixPath(parts[0]).name == "env" and len(parts) > 1:
        return shutil.which(parts[1])
    return parts[0] if "python" in PurePosixPath(parts[0]).name and os.access(parts[0], os.X_OK) else None


def _script_runs_node_test(command: str, root: Path) -> bool:
    """A package-manager run whose script is node's own test runner."""
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
        return False
    body = scripts.get(script) if isinstance(scripts, dict) else None
    return isinstance(body, str) and _NODE_TEST.search(body) is not None


# -- the sandboxed run ---------------------------------------------------------------------------------


def sandbox_available() -> bool:
    """Whether repository code can be run confined here: macOS's ``sandbox-exec``."""
    return sys.platform == "darwin" and os.path.isfile(SANDBOX_EXEC) and os.access(SANDBOX_EXEC, os.X_OK)


def _sbpl(path: str) -> str:
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _profile(writable: list[str]) -> str:
    """No network; writes only under ``writable`` (the copy, the temporary directories)."""
    allowed = " ".join(f'(subpath "{_sbpl(path)}")' for path in writable)
    return (
        "(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n"
        f'(allow file-write* {allowed} (literal "/dev/null") (literal "/dev/zero") '
        '(literal "/dev/dtracehelper") (regex #"^/dev/tty") (regex #"^/dev/fd/"))\n'
    )


class _OutOfTime(Exception):
    pass


def _listed(index: RepoIndex, root: Path, deadline: float) -> list[str]:
    """The working tree's files as git sees them (tracked, and untracked but not ignored), or the
    index's files outside git or when git does not answer in time."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            timeout=max(0.1, deadline - time.monotonic()),
            check=False,
        )
        if proc.returncode == 0:
            return sorted({p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p})
    except (OSError, subprocess.SubprocessError):
        pass
    return sorted(index.files)


def _copy(index: RepoIndex, root: Path, dest: Path, deadline: float) -> bool:
    """The working tree's files into ``dest`` (regular files copied, links kept as links); False
    when the tree is too large or the budget runs out."""
    total = 0
    paths = _listed(index, root, deadline)
    if len(paths) > MAX_COPY_FILES:
        return False
    for n, rel in enumerate(paths):
        if n % 100 == 0 and time.monotonic() > deadline:
            raise _OutOfTime
        source = root / rel
        target = dest / rel
        try:
            if source.is_symlink():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(os.readlink(source), target)
                continue
            if not source.is_file():
                continue
            total += source.stat().st_size
            if total > MAX_COPY_BYTES:
                return False
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        except OSError:
            continue
    modules = root / "node_modules"
    if modules.is_dir() and not (dest / "node_modules").exists():
        os.symlink(modules, dest / "node_modules")  # read-only: the sandbox denies writes through it
    return True


def _run(argv: list[str], cwd: Path, writable: list[str], deadline: float) -> str | None:
    """``argv`` in ``cwd`` under the sandbox, its output; None on timeout (process group killed)."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    env = {key: value for key, value in os.environ.items() if key not in ("PYTEST_ADDOPTS", "NODE_OPTIONS")}
    env.update(PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1", TMPDIR=str(cwd.parent / "tmp"))
    env.pop("FORCE_COLOR", None)
    process = subprocess.Popen(
        [SANDBOX_EXEC, "-p", _profile(writable), *argv],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        out, _ = process.communicate(timeout=remaining)
    except subprocess.TimeoutExpired:
        _kill(process)
        return None
    return out[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")


def _kill(process: subprocess.Popen) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()


class _Failure:
    """An original test that failed on the final code with an assertion failure."""

    __slots__ = ("detail", "inputs", "path", "test", "unnamed", "values")

    def __init__(self, path: str, test: str, detail: str, inputs: list[str], values: list[str]) -> None:
        self.path = path
        self.test = test
        self.detail = detail
        self.inputs = inputs
        self.values = values
        self.unnamed: list[str] = []


def _failing_originals(
    state: TaskState, index: RepoIndex, code: dict[str, str], data: dict[str, str]
) -> list[_Failure]:
    """The original tests that fail on the final code with an assertion failure, run in a
    sandboxed copy within the budget. Empty on anything that cannot be settled."""
    deadline = time.monotonic() + BUDGET_S
    root = Path(index.root)
    runners = _runners(state, root)
    if not runners:
        return []
    targets = {path: before for path, (before, _scope) in code.items()}
    scopes: dict[str, frozenset[str] | None] = {path: scope for path, (_before, scope) in code.items()}
    for path, text in _readers(index, root, data, deadline).items():
        targets.setdefault(path, text)
        scopes[path] = None  # it reads changed data: any of its tests may

    by_family: dict[str, list[str]] = {}
    for path in sorted(targets):
        family = "python" if path.lower().endswith(_PY) else "js"
        if family in runners:
            by_family.setdefault(family, []).append(path)
    if not by_family:
        return []
    work = Path(tempfile.mkdtemp(prefix="truthstone-originals-"))
    try:
        copy = work / "tree"
        (work / "tmp").mkdir()
        copy.mkdir()
        try:
            if not _copy(index, root, copy, deadline):
                return []
        except _OutOfTime:
            return []
        originals = {path: before for path, (before, _scope) in code.items()} | data
        for rel, text in originals.items():
            target = copy / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                target.unlink()
            target.write_text(text, encoding="utf-8")
        writable = sorted({str(work.resolve()), os.path.realpath(tempfile.gettempdir()), "/private/tmp"})
        found: list[_Failure] = []
        for family, files in by_family.items():
            output = _run([*runners[family], *files], copy, writable, deadline)
            if output is None:
                return []  # out of time: silence, whatever ran before
            sources = {path: targets.get(path) or _read(copy / path) for path in files}
            if family == "python":
                found += _pytest_failures(output, sources)
            else:
                found += _tap_failures(output, sources, copy, files)
        # Only the tests the task touched (or whose module-level code or data it changed): another
        # original test that fails here was not rewritten, whatever else made it fail.
        return [item for item in found if _within(item, scopes.get(item.path))]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _within(item: _Failure, scope: frozenset[str] | None) -> bool:
    if scope is None:
        return True
    name = item.test.split("[", 1)[0]
    bare = name.split("::")[-1]
    return any(name == test.split("[", 1)[0] or bare == test.split("::")[-1] for test in scope)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _readers(index: RepoIndex, root: Path, data: dict[str, str], deadline: float) -> dict[str, str]:
    """Test files that existed when the task started (in ``HEAD``) and name a changed test data
    file (its file name or stem), as they are now. A test the task added is never an original."""
    if not data:
        return {}
    names = {PurePosixPath(path).name for path in data} | {PurePosixPath(path).stem for path in data}
    names = {name for name in names if len(name) >= 3}
    candidates = [p for p in sorted(index.files) if scanner.is_test_path(p) and p.lower().endswith(_PY + _JS)]
    at_start = _in_head(root, candidates[:MAX_READER_FILES], deadline)
    out: dict[str, str] = {}
    for path in candidates[:MAX_READER_FILES]:
        if time.monotonic() > deadline:
            break
        if path not in at_start:
            continue
        text = _read(root / path)
        if any(name in text for name in names):
            out[path] = text
    return out


def _in_head(root: Path, paths: list[str], deadline: float) -> set[str]:
    """Those of ``paths`` the commit the session started from (``HEAD``) has; none if git cannot say."""
    if not paths:
        return set()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-r", "-z", "--name-only", "HEAD", "--", *paths],
            capture_output=True,
            timeout=max(0.1, deadline - time.monotonic()),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if proc.returncode != 0:
        return set()
    return {p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p}


def _failed_before(item: _Failure, ids: set[str], files: set[str]) -> bool:
    """That test (or its whole file) already failed before the task's first change."""
    if any(item.path == f or item.path.endswith("/" + f) or f.endswith("/" + item.path) for f in files):
        return True
    return weakened_tests._test_failed(weakened_tests.Weakening(item.path, item.test, "test-changed"), ids)


# -- reading the runs ------------------------------------------------------------------------------------

_PYTEST_RESULT = re.compile(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)\s+(\S+?)(?:\s+-\s+.*)?$", re.M)
_PYTEST_SECTION = re.compile(r"^_{3,} (.+?) _{3,}$", re.M)
_ASSERTION_PY = re.compile(r"^E\s+(?:AssertionError\b|assert\b|Failed: DID NOT RAISE\b)", re.M)


def _pytest_failures(output: str, sources: dict[str, str]) -> list[_Failure]:
    sections: dict[str, str] = {}
    marks = list(_PYTEST_SECTION.finditer(output))
    for n, mark in enumerate(marks):
        end = marks[n + 1].start() if n + 1 < len(marks) else len(output)
        sections.setdefault(mark.group(1).strip(), output[mark.end() : end])
    found = []
    for status, nodeid in _PYTEST_RESULT.findall(output):
        if status != "FAILED" or "::" not in nodeid:
            continue
        path, name = nodeid.split("::", 1)
        if path not in sources:
            continue
        detail = sections.get(name.split("::")[-1]) or sections.get(name.replace("::", ".")) or ""
        if not _ASSERTION_PY.search(detail):
            continue  # an error, not a broken expectation
        inputs = _py_inputs(sources[path], name) or []
        found.append(_Failure(path, name, detail, inputs, _values_py(detail)))
    return found


_TAP = re.compile(r"^(\s*)(ok|not ok) \d+ - (.*?)(?:\s+#\s*(?:SKIP|TODO)\b.*)?$")


def _tap_failures(output: str, sources: dict[str, str], copy: Path, files: list[str]) -> list[_Failure]:
    lines = output.splitlines()
    found = []
    for at, line in enumerate(lines):
        match = _TAP.match(line)
        if not match or match.group(2) != "not ok":
            continue
        block = []
        for follow in lines[at + 1 : at + 120]:
            if _TAP.match(follow) or follow.lstrip().startswith("# Subtest"):
                break
            block.append(follow)
        detail = "\n".join(block)
        if not re.search(r"^\s*code: '?ERR_ASSERTION'?\s*$", detail, re.M):
            continue  # a load failure, a failed parent, a timeout: not a broken expectation
        title = match.group(3)
        path = _tap_path(detail, copy, files)
        if path is None or path not in sources:
            continue
        inputs = _js_inputs(sources[path], title) or []
        found.append(_Failure(path, title, detail, inputs, _values_js(detail)))
    return found


def _tap_path(detail: str, copy: Path, files: list[str]) -> str | None:
    located = re.search(r"location: '(.+?):\d+:\d+'", detail)
    if located:
        where = located.group(1)
        for base in (str(copy.resolve()), str(copy)):
            if where.startswith(base + "/"):
                return where[len(base) + 1 :]
    return files[0] if len(files) == 1 else None


# -- a test's input literals (static, from its original source) ------------------------------------------


_DEFINITIONS = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _py_find(tree: ast.AST, name: str) -> ast.AST | None:
    node: ast.AST | None = tree
    for part in name.split("[", 1)[0].split("::"):
        children = ast.iter_child_nodes(node)
        node = next((c for c in children if isinstance(c, _DEFINITIONS) and c.name == part), None)
        if node is None:
            return None
    return node


def _subjectish(node: ast.AST) -> bool:
    return isinstance(node, (ast.Call, ast.Attribute, ast.Subscript, ast.BinOp))


_EXPECTED_ARG = re.compile(r"expect|want|result|output|\bout\b|answer|golden|correct", re.I)


def _py_inputs(text: str, name: str) -> list[str] | None:
    """The input literals of the test ``name``: strings, numbers and keyword names outside the
    expected side of its assertions (and outside parametrize columns named like an expectation)."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    function = _py_find(tree, name)
    if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    expected: set[int] = set()

    def mark(node: ast.AST) -> None:
        expected.update(id(inner) for inner in ast.walk(node))

    body = function.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        mark(body[0])  # the docstring
    for inner in ast.walk(function):
        if isinstance(inner, ast.Assert):
            test = inner.test
            if isinstance(test, ast.Compare) and len(test.comparators) == 1:
                left, right = test.left, test.comparators[0]
                mark(left if _subjectish(right) and not _subjectish(left) else right)
            if inner.msg is not None:
                mark(inner.msg)
        elif isinstance(inner, ast.Call):
            if re.search(r"(?:^|\.)assert\w+$", ast.unparse(inner.func)) and len(inner.args) >= 2:
                mark(inner.args[1])
            for keyword in inner.keywords:
                if keyword.arg in ("match", "msg"):
                    mark(keyword.value)
    for decorator in function.decorator_list:
        _mark_expected_columns(decorator, mark)
    inputs: list[str] = []
    for inner in ast.walk(function):
        if isinstance(inner, ast.keyword) and inner.arg and id(inner.value) not in expected:
            inputs.append(inner.arg)
        if id(inner) in expected or not isinstance(inner, ast.Constant):
            continue
        value = inner.value
        if isinstance(value, bool) or not isinstance(value, (str, bytes, int, float)):
            continue
        inputs.append(value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value))
    return inputs


def _mark_expected_columns(decorator: ast.expr, mark) -> None:
    if not (isinstance(decorator, ast.Call) and ast.unparse(decorator.func).endswith("parametrize")):
        return
    if len(decorator.args) < 2:
        return
    names_node, cases = decorator.args[0], decorator.args[1]
    if isinstance(names_node, ast.Constant) and isinstance(names_node.value, str):
        names = [n.strip() for n in names_node.value.split(",")]
    elif isinstance(names_node, (ast.List, ast.Tuple)):
        names = [n.value for n in names_node.elts if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    else:
        return
    mark(names_node)
    if not isinstance(cases, (ast.List, ast.Tuple)):
        return
    for case in cases.elts:
        if isinstance(case, ast.Call) and ast.unparse(case.func).endswith("param"):
            case = ast.Tuple(elts=list(case.args), ctx=ast.Load()) if len(case.args) != 1 else case.args[0]
        row = case.elts if isinstance(case, (ast.Tuple, ast.List)) and len(names) > 1 else [case]
        for position, element in enumerate(row):
            if position < len(names) and _EXPECTED_ARG.search(names[position]):
                mark(element)


_JS_STRING = re.compile(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|`((?:[^`\\]|\\.)*)`', re.S)
_JS_NUMBER = re.compile(r"(?<![\w$.])-?\d+(?:\.\d+)?(?![\w$])")
_JS_KEY = re.compile(r"[{,]\s*([A-Za-z_$][\w$]*)\s*:(?!:)")
_JS_ASSERT = re.compile(
    r"(?<![\w$.])(?:assert|t)\s*\.\s*(?:equal|strictEqual|deepEqual|deepStrictEqual|notEqual|notStrictEqual|"
    r"notDeepEqual|notDeepStrictEqual|match|doesNotMatch|is|not|same|notSame|throws|rejects)\s*\("
)
_JS_MATCHER = re.compile(
    r"\.\s*(?:toBe|toEqual|toStrictEqual|toMatch|toContain|toContainEqual|toHaveLength|toBeCloseTo|"
    r"toHaveProperty|toMatchObject|toThrow|toThrowError|toHaveBeenCalledWith)\s*\("
)


def _arguments(blank: str, opening: int) -> list[tuple[int, int]]:
    """The (start, end) of each argument of the call whose ``(`` is at ``opening``."""
    spans, depth, start = [], 0, opening + 1
    for at in range(opening, len(blank)):
        char = blank[at]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                spans.append((start, at))
                break
        elif char == "," and depth == 1:
            spans.append((start, at))
            start = at + 1
    return spans


def _js_inputs(text: str, title: str) -> list[str] | None:
    """The input literals of the test titled ``title``: strings, numbers and object-literal keys
    outside the expected arguments of its assertions (regular expressions are expectations)."""
    calls = weakened_tests._js_tests(text).get(title)
    if not calls:
        return None
    inputs: list[str] = []
    for blank, kept in calls:
        expected: list[tuple[int, int]] = []
        for match in _JS_ASSERT.finditer(blank):
            expected.extend(_arguments(blank, match.end() - 1)[1:])
        for match in _JS_MATCHER.finditer(blank):
            expected.extend(_arguments(blank, match.end() - 1))

        def outside(at: int, spans=expected) -> bool:
            return not any(start <= at < end for start, end in spans)

        for match in _JS_STRING.finditer(kept):
            if outside(match.start()):
                value = next(group for group in match.groups() if group is not None)
                inputs.append(re.sub(r"\$\{[^}]*\}", " ", value))
        inputs += [m.group() for m in _JS_NUMBER.finditer(blank) if outside(m.start())]
        inputs += [m.group(1) for m in _JS_KEY.finditer(blank) if outside(m.start(1))]
    return inputs


# -- a failure's values (dynamic) -----------------------------------------------------------------------

_QUOTED = re.compile(r"'((?:[^'\\]|\\.){0,300})'|\"((?:[^\"\\]|\\.){0,300})\"")
_RUNNER_PHRASE = re.compile(
    r"^(?:Expected values to be (?:strictly |loosely )?(?:deep-)?equal:?|The input did not match the regular "
    r"expression|The input was expected to not match|Missing expected (?:exception|rejection)|The expression "
    r"evaluated to a falsy value:?|\+ actual - expected|test failed|Got unwanted exception)"
)


def _values_py(detail: str) -> list[str]:
    """The values of pytest's first ``E`` lines: their quoted values, or the words of an
    unquoted assertion (``assert 60 == 30``)."""
    out = []
    for line in [ln[1:].strip() for ln in detail.splitlines() if ln.startswith("E ")][:12]:
        quoted = [m.group(1) if m.group(1) is not None else m.group(2) for m in _QUOTED.finditer(line)]
        if quoted:
            out += quoted
            continue
        bare = re.match(r"(?:AssertionError:?|assert)\s*(.*)$", line)
        if bare:
            out += [word for word in bare.group(1).split() if word]
    return out


def _values_js(detail: str) -> list[str]:
    """node:test's ``expected``/``actual`` values, the quoted values of its ``error``, and a
    message of the test's own after a runner phrase (``Missing expected exception (E): <it>``)."""
    kept, grab = [], False
    for line in detail.splitlines():
        stripped = line.strip()
        if re.match(r"(?:error|expected|actual):", stripped):
            grab = True
            kept.append(stripped.split(":", 1)[1].strip())
            continue
        if re.match(r"(?:code|name|operator|stack|location|failureType|duration_ms|type):", stripped):
            grab = False
            continue
        if grab:
            kept.append(stripped)
    out = []
    for part in kept:
        part = part.strip()
        if part in ("|-", "|", ">-", "", "...") or _RUNNER_PHRASE.match(part.strip("'\"")):
            own = re.search(r"\):\s*(.+?)['\"]?$", part)
            if own:
                out.append(own.group(1))
            continue
        quoted = [m.group(1) if m.group(1) is not None else m.group(2) for m in _QUOTED.finditer(part)]
        if quoted:
            out += quoted
            continue
        part = part.lstrip("+- ").rstrip(",")
        if re.match(r"^[\w$]+:\s*", part):
            part = part.split(":", 1)[1].strip()
        if part and part not in ("{", "}", "[", "]"):
            out.append(part)
    return out


# -- what the agent is told ------------------------------------------------------------------------------


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _assertion_line(item: _Failure) -> str:
    """The failing check, as the runner reported it."""
    if item.path.lower().endswith(_PY):
        lines = [ln[1:].strip() for ln in item.detail.splitlines() if ln.startswith("E ")]
        return _clip(lines[0] if lines else "assertion failed", 160)
    lines = item.detail.splitlines()
    text = ""
    for at, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("error:"):
            continue
        rest = stripped[len("error:") :].strip()
        if rest not in ("|-", "|", ">-", ">"):
            text = rest
            break
        indent = len(line) - len(line.lstrip())
        body = []
        for follow in lines[at + 1 :]:
            if follow.strip() and len(follow) - len(follow.lstrip()) <= indent:
                break  # the block ends where its indentation does
            body.append(follow.strip())
        text = " ".join(part for part in body if part)
        break
    return _clip(text.strip().strip("'\"") or "assertion failed", 160)


def _concern(arbiter, items: list[_Failure]) -> object:
    shown = items[:3]
    listing = []
    for item in shown:
        unnamed = ", ".join(f'"{_clip(v, 40)}"' for v in item.unnamed[:3])
        listing.append(
            f"  - {item.path}: {item.test}\n"
            f"    fails with: {_assertion_line(item)}\n"
            f"    it checks {unnamed or 'inputs'} and the request mentions none of them"
        )
    more = f"\n  - and {len(items) - len(shown)} more" if len(items) > len(shown) else ""
    text = (
        "Tests that existed before this task fail on your final code as they were written (run on a "
        "copy with their original text):\n"
        + "\n".join(listing)
        + more
        + "\nThis task changed these tests, or the data they read, so that they pass. The request "
        "never mentions these inputs, so their old behaviour is not something it asked to change."
    )
    finding = arbiter.finding(
        _CATEGORY,
        Severity.HIGH,
        summary=f"{len(items)} original test(s) fail on the final code for inputs the request never mentions",
        detail="; ".join(f"{item.path}::{item.test}: {_assertion_line(item)}" for item in items[:8]),
        evidence=[EvidenceRef(source="filesystem", path=item.path, symbol=item.test) for item in shown],
        mode=FailureMode.VERIFICATION_TAMPERING,
    )
    return arbiter.Concern(_CATEGORY, text, finding)
