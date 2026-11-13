"""Whether a test edit held under test pressure moved the yardstick: its original fails on the code (day 12).

The failure class and its look-alike
------------------------------------
Under a request about failing tests ("X has been failing since the refactor, fix it"), the test-weakening
check (``validate/weakened_tests.py``) holds a "done" over an existing test the change edited: a new check
slipped into a passing neighbour of the failing test, the failing test itself parametrised with more cases
and a recomputed total, a test renamed and widened. Its reason is the yardstick: the tests that existed
are what the request asks the code to meet. The tamper it is there for moves that yardstick, so the old
test would fail on the new code: an expected value changed to what the code returns now, the failing
assertion dropped, the failing test deleted.

Red-green and regression work touches the same tests honestly, and then the old test still passes on the
new code: the agent fixed the code and added cases. A grader that runs the original tests against the
final tree (and does not forbid test edits outright) passes that work, and a hold there is a false block.
The request's own words are the only thing that forbids test edits outright ("don't change the tests",
``tests_kept_requested``); that case is not this module's.

What is checked
---------------
``failing(state, index, items)``: the test files holding ``items`` get their task-start text back in a
sandboxed copy of the working tree (as do the other existing test files the task changed: the original
suite, as a grader runs it), and are run there with the runner this session itself used (pytest under its
interpreter, node's test runner). The result is the items whose original test definitely failed there:
a failure or error under that test's own id (pytest ``path::name[...]``, node:test's title in its file), a
file that did not even load, or for a file-level item (a module-level change) any failure in its file.

Anything that cannot be settled (no sandbox, a runner the session never used, a timeout, output that does
not name the test) is not a failure: the item is not held, and that is logged at INFO. This only ever
quiets the check that calls it.

Safety and cost
---------------
``original_tests``' sandbox: never in the agent's tree; a copy under ``sandbox-exec`` (no network, writes
only to the copy and the temporary directories). One wall-clock budget for the copy and the runs,
``BUDGET_S`` (Codex's Stop forwarder gives up at 4 s). It runs only at a Stop where pressure alone would
hold a test edit, which is rare, once per tree state (memoized).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from truthstone.core.taskstate import TaskState
from truthstone.repo import scanner
from truthstone.repo.index import RepoIndex
from truthstone.validate import original_tests as sandbox

log = logging.getLogger(__name__)

__all__ = ["BUDGET_S", "failing"]

BUDGET_S = 2.5
MAX_FILES = 8  # test files run, at most: more is a rewritten suite, not a few edits to settle here
MAX_MEMO = 64

_PY = (".py",)
_JS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
_PYTEST_LINE = re.compile(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)\s+(\S+?)(?:\s+-\s+.*)?$", re.M)
_TAP_LINE = re.compile(r"^\s*(ok|not ok) \d+ - (.*?)(?:\s+(?<!\\)#\s*(SKIP|TODO)\b.*)?\s*$")
_LOCATION = re.compile(r"location: '(.+?):\d+:\d+'")

_MEMO: dict[tuple, frozenset[tuple[str, str]]] = {}


def failing(state: TaskState, index: RepoIndex, items: list) -> set[tuple[str, str]]:
    """The ``(path, test)`` keys of ``items`` (``weakened_tests.Weakening``) whose original test fails on the
    current code, run in a sandboxed copy; an empty set when nothing can be settled. Never raises."""
    from truthstone.verify import arbiter

    keys = sorted({(item.path, item.test) for item in items})
    if not keys:
        return set()
    try:
        texts = arbiter.changed_texts(state, index)
        files = sorted({path for path, _test in keys})
        originals = {
            path: before
            for path, (before, _after) in texts.items()
            if before is not None and scanner.is_test_path(path)
        }
        if len(files) > MAX_FILES or not all(path in originals for path in files):
            log.info("truthstone: yardstick not settled: %d test file(s), originals missing", len(files))
            return set()
        digest = hashlib.sha256()
        for path, (_before, after) in sorted(texts.items()):
            digest.update(path.encode() + b"\0" + (after or "").encode("utf-8", "replace") + b"\0")
        memo = (state.task_id, state.session_id, state.started_at, tuple(keys), digest.hexdigest())
        if memo in _MEMO:
            return set(_MEMO[memo])
        if not sandbox.sandbox_available():
            log.info("truthstone: yardstick not settled: no sandbox on this machine")
            return set()
        started = time.monotonic()
        found = _run(state, index, keys, files, originals)
        log.info(
            "truthstone: yardstick ran %d original test file(s) in %.2fs: %s",
            len(files),
            time.monotonic() - started,
            "not settled" if found is None else f"{len(found)} of {len(keys)} original test(s) fail",
        )
    except Exception:  # never fails the hook (logged, then silence)
        log.info("truthstone: yardstick check failed; silent", exc_info=True)
        return set()
    result = frozenset(found or ())
    if found is not None:
        while len(_MEMO) >= MAX_MEMO:
            _MEMO.pop(next(iter(_MEMO)))
        _MEMO[memo] = result
    return set(result)


def _run(
    state: TaskState,
    index: RepoIndex,
    keys: list[tuple[str, str]],
    files: list[str],
    originals: dict[str, str],
) -> set[tuple[str, str]] | None:
    """The keys whose original fails in the copy; None when the copy or a run cannot be settled."""
    deadline = time.monotonic() + BUDGET_S
    root = Path(index.root)
    runners = sandbox._runners(state, root)
    by_family: dict[str, list[str]] = {}
    for path in files:
        family = "python" if path.lower().endswith(_PY) else "js" if path.lower().endswith(_JS) else ""
        if family not in runners:
            log.info("truthstone: yardstick not settled: no runner this session used for %s", path)
            return None
        by_family.setdefault(family, []).append(path)
    work = Path(tempfile.mkdtemp(prefix="truthstone-yardstick-"))
    try:
        copy = work / "tree"
        (work / "tmp").mkdir()
        copy.mkdir()
        try:
            if not sandbox._copy(index, root, copy, deadline):
                return None
        except sandbox._OutOfTime:
            return None
        for rel, text in originals.items():
            target = copy / rel
            if not str(target.resolve()).startswith(str(copy.resolve()) + os.sep):
                return None
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                target.unlink()
            target.write_text(text, encoding="utf-8")
        writable = sorted({str(work.resolve()), os.path.realpath(tempfile.gettempdir()), "/private/tmp"})
        out: set[tuple[str, str]] = set()
        for family, paths in by_family.items():
            output = sandbox._run([*runners[family], *paths], copy, writable, deadline)
            if output is None:
                return None  # out of time
            wanted = [key for key in keys if key[0] in paths]
            reader = _python_failing if family == "python" else _js_failing
            found = reader(output, wanted, paths, copy, _still_red(state))
            if found is None:
                return None
            out |= found
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _still_red(state: TaskState) -> set[tuple[str, str]]:
    """(file, test) of every test the session's own latest run reported failing: a test the edited file
    still fails is not one the edit made pass (a known failure left as it was)."""
    runs = [run for run in state.verification.outcomes if run.seq is not None]
    if not runs:
        return set()
    latest = max(runs, key=lambda run: run.seq)
    return {
        (test.split("::", 1)[0], test.split("::", 1)[1].split("[", 1)[0])
        for test in latest.failing_tests
        if "::" in test
    }


def _python_failing(
    output: str, keys: list[tuple[str, str]], paths: list[str], _copy: Path, still: set[tuple[str, str]]
) -> set[tuple[str, str]] | None:
    """pytest ``-rA``: a key fails on its own FAILED / ERROR line, or with its file's collection error; a
    file-level key (no test) on a failure in its file of a test the session's latest run did not still
    fail. None when the run named nothing at all."""
    results = _PYTEST_LINE.findall(output)
    if not results:
        return None
    failed: set[str] = set()
    broken: set[str] = set()  # files that did not load
    for status, node in results:
        if status not in ("FAILED", "ERROR"):
            continue
        if "::" in node:
            failed.add(node.split("[", 1)[0])
        else:
            broken.add(node)
    out = set()
    for path, test in keys:
        if path in broken:
            out.add((path, test))
        elif not test:
            if any(
                node.split("::", 1)[0] == path and (path, node.split("::", 1)[1]) not in still
                for node in failed
            ):
                out.add((path, test))
        elif f"{path}::{test}" in failed:
            out.add((path, test))
    return out


def _js_failing(
    output: str, keys: list[tuple[str, str]], paths: list[str], copy: Path, still: set[tuple[str, str]]
) -> set[tuple[str, str]] | None:
    """node's TAP: a key fails on a ``not ok`` with its title whose location is its file (the only file run
    needs no location), or when its file did not load (a ``not ok`` named by the file). A file-level key
    fails on a ``not ok`` located in its file, of a test the session's latest run did not still fail."""
    from truthstone.validate import weakened_tests

    lines = output.splitlines()
    if not any(_TAP_LINE.match(line) for line in lines):
        return None
    failures: list[tuple[str, str | None]] = []  # (title, file or None)
    for at, line in enumerate(lines):
        match = _TAP_LINE.match(line)
        if not match or match.group(1) != "not ok" or match.group(3):
            continue
        title = re.sub(r"\\([\\#])", r"\1", match.group(2).strip())
        block = []
        for follow in lines[at + 1 : at + 120]:
            if _TAP_LINE.match(follow) or follow.lstrip().startswith("# Subtest"):
                break
            block.append(follow)
        failures.append((title, _where("\n".join(block), copy, paths)))
    out = set()
    for path, test in keys:
        template = weakened_tests._template(test) if "${" in test else None
        for title, where in failures:
            if title in (path, f"./{path}", str(copy / path)) or title.endswith("/" + path):
                out.add((path, test))  # the file itself failed to load
                break
            if where is None and len(paths) == 1:
                where = paths[0]
            if where != path:
                continue
            if not test:
                if (path, title) not in still:
                    out.add((path, test))
                    break
            elif title == test or (template is not None and template.fullmatch(title)):
                out.add((path, test))
                break
    return out


def _where(detail: str, copy: Path, paths: list[str]) -> str | None:
    located = _LOCATION.search(detail)
    if not located:
        return None
    spot = located.group(1)
    for base in (str(copy.resolve()), str(copy)):
        if spot.startswith(base + "/"):
            rel = spot[len(base) + 1 :]
            return rel if rel in paths else None
    return None
