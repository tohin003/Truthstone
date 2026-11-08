"""The task-start documentation snapshot (C2 v3c): a before-text for docs no edit tool baselined.

Ported from the frozen prototype ``snapshot_proto_v3c.py`` (FIX-DESIGN v4, C2 and D-C2; appendix
``RULES-C2-v3c.md``); the prototype is the specification. A doc rewritten through the shell
(``cat > docs/FORMAT.md <<'EOF'``) had no "before" text: only edit tools record a baseline
(``core/engine.py:Guard._record_parse_baseline``), so Stop never compared it.

* **Scope.** Docs only: ``spec_integrity.is_doc_path``, minus history files
  (``spec_integrity._LOG``). Tests are out.
* **Taking it.** At the prompt of a task created for a session, the task's in-scope docs are read,
  sorted, within the caps: ``FILE_BYTES`` per file (larger files skipped, never truncated),
  ``FILES`` files and ``RAW_BYTES`` raw in all, binaries skipped, zlib-stored. Live
  (``Guard.defer_bookkeeping``) it is taken on its own thread, off the event lock, within
  ``DEADLINE_S``; only the task's first write-capable pre-tool event waits for it (``wait``). In
  process (replay, tests) it is taken synchronously, so replay stays deterministic. One snapshot per
  session's current task: a session's next prompt frees the previous task's. The snapshot lives on
  ``TaskState.spec_snapshot`` and is never stored: a task rebuilt from the store has none.
* **When it is used.** Only for a changed doc with no usable edit baseline (no ``file_baselines``
  entry, or one with ``changed_before``): ``snapshot_texts``, a second pass at Stop after
  ``arbiter.changed_texts`` (at most ``MAX_SNAPSHOT_COMPARED`` files within ``COMPARE_BUDGET_S``).
  Such a doc is read for marker sentences only (``_excepted`` still runs), and its erosion speaks
  only with request pressure or a pressing test. Spec erosion and ``spec_conflict``
  (``verify/spec_conflict.py``) are its only readers.
* **Re-snapshot.** Only after a shell line made ENTIRELY of git invocations that bring in another
  ref's content (merge, pull, rebase, cherry-pick, checkout/switch of a ref, reset to a ref,
  ``restore --source``, revert) or ``gh pr checkout`` (``brings_in_ref``): no redirect to a file,
  nothing opaque, nothing else on the line. Never after stash, apply, am or patch: those carry the
  agent's own content. The command's reservation carries ``rewrites_tree``; under the event lock the
  sweep that credits a path to it only queues (task, path) (``queue_resnapshot``); the reads happen
  off the lock (``drain``: in process when ``Guard.handle`` returns, live on a
  ``truthstone-spec-resnapshot`` thread), one read per path, the raw cap from a maintained total,
  published copy-on-write by one assignment. A re-snapshot is a no-op until the snapshot is done;
  at Stop, jobs still queued for the task are applied first (``settle``).
* **Deleted docs** are compared: a rule that left with its file counts as removed, unless a doc
  change was requested. Not when the doc's whole directory was removed (``dir_removed``: package
  removal), nor when it was moved (``moved_to``: a file the task changed or created, existing now,
  with the same base name or ``difflib`` text >= ``MOVED_SIMILARITY`` similar). Docs created through
  the shell join the pool of new texts (``created_docs``).

Nothing here raises into the hook: a snapshot not taken, a lost re-snapshot or a failed read is
silence.
"""

from __future__ import annotations

import difflib
import logging
import os
import threading
import time
import zlib
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from truthstone.core.taskstate import TaskState
    from truthstone.repo.index import RepoIndex

log = logging.getLogger(__name__)

FILE_BYTES = 512_000
RAW_BYTES = 8_000_000
FILES = 2_000
DEADLINE_S = 1.5
MAX_SNAPSHOT_COMPARED = 100
COMPARE_BUDGET_S = 2.0
MOVED_SIMILARITY = 0.8
SETTLE_WAIT_S = 0.5


class SpecSnapshot:
    __slots__ = (  # noqa: RUF023 - the prototype's order
        "files",
        "raw",
        "raw_bytes",
        "done",
        "started",
        "complete",
        "stats",
        "waited",
        "synchronous",
        "lock",
    )

    def __init__(self, synchronous: bool = True) -> None:
        self.files: dict[str, bytes] = {}
        self.raw: dict[str, int] = {}  # raw size per stored entry (rd2-3-5)
        self.raw_bytes = 0
        self.done = threading.Event()
        self.started = time.monotonic()
        self.complete = False
        self.stats: dict = {}
        self.waited = False  # the first write-capable pre-tool event already waited
        self.synchronous = synchronous
        self.lock = threading.Lock()  # held while a re-snapshot batch of this task is applied


# (task state, root, path), queued under the event lock; read off it (``drain``).
_PENDING: list[tuple[Any, str, str]] = []
_PENDING_LOCK = threading.Lock()


def _snapshot(state: Any) -> SpecSnapshot | None:
    """The task's snapshot, or None (none taken, freed, or a rebuilt task)."""
    return getattr(state, "spec_snapshot", None)


def _ready(snap: SpecSnapshot) -> bool:
    """Taken and published. ``done`` is also set when taking it failed (``start``: its waiter must
    not stall), and such a snapshot is no snapshot."""
    return snap.done.is_set() and snap.complete


def in_spec_scope(path: str) -> bool:
    from truthstone.validate import spec_integrity as si

    return si.is_doc_path(path) and not si._LOG.match(PurePosixPath(path).name)


# -- taking the snapshot -------------------------------------------------------------------------------------


def build(
    root: Path, paths: Iterable[str] | None, deadline: float | None = None
) -> tuple[dict[str, bytes], dict[str, int], dict]:
    """Read the in-scope docs of ``paths`` under ``root`` within the caps. Never raises."""
    from truthstone.verify import baseline

    t0 = time.perf_counter()
    files: dict[str, bytes] = {}
    sizes: dict[str, int] = {}
    stats: dict[str, Any] = {
        "listed": 0,
        "in_scope": 0,
        "stored": 0,
        "raw_bytes": 0,
        "zlib_bytes": 0,
        "skipped_large": 0,
        "skipped_binary": 0,
        "unreadable": 0,
        "cut": "",
    }
    try:
        paths = list(paths or ())
        stats["listed"] = len(paths)
        scoped = sorted(p for p in paths if in_spec_scope(p))
        stats["in_scope"] = len(scoped)
        raw = 0
        for rel in scoped:
            if deadline is not None and time.monotonic() > deadline:
                stats["cut"] = "deadline"
                break
            full = baseline._resolve(root, rel)
            if full is None:
                stats["unreadable"] += 1
                continue
            try:
                if not full.is_file():
                    continue
                size = full.stat().st_size
            except OSError:
                stats["unreadable"] += 1
                continue
            if size > FILE_BYTES:
                stats["skipped_large"] += 1
                continue
            if len(files) >= FILES:
                stats["cut"] = "files"
                break
            if raw + size > RAW_BYTES:
                stats["cut"] = "bytes"
                break
            try:
                data = full.read_bytes()
            except OSError:
                stats["unreadable"] += 1
                continue
            comp = baseline._compress(data)
            if comp is None:
                stats["skipped_binary"] += 1
                continue
            files[rel] = comp
            sizes[rel] = len(data)
            raw += len(data)
            stats["zlib_bytes"] += len(comp)
        stats["stored"] = len(files)
        stats["raw_bytes"] = raw
    except Exception as exc:  # noqa: BLE001 - a snapshot only sharpens a check; never a failure
        stats["error"] = repr(exc)[:200]
    stats["ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return files, sizes, stats


def start(
    state: TaskState, root: Path, list_files: Callable[[], Iterable[str] | None], synchronous: bool
) -> SpecSnapshot:
    """Take the task's snapshot: synchronously in process, else on its own thread. The thread
    publishes in a ``finally`` (struct-3-13): a failure never leaves the task's first write waiting."""
    snap = SpecSnapshot(synchronous)
    state.spec_snapshot = snap

    def run() -> None:
        t0 = time.perf_counter()
        try:
            try:
                paths = list_files()
            except Exception:  # noqa: BLE001
                paths = None
            if paths is None:
                from truthstone.repo import scanner

                paths = scanner._git_listed_files(root) or []
            files, sizes, stats = build(root, paths, None if synchronous else snap.started + DEADLINE_S)
            stats["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            snap.stats = stats
            snap.raw = sizes
            snap.raw_bytes = sum(sizes.values())
            snap.files = files  # published by one assignment
            snap.complete = True
        except Exception:  # a snapshot not taken is silence
            log.debug("truthstone: the documentation snapshot failed", exc_info=True)
        finally:
            snap.done.set()

    if synchronous:
        run()
    else:
        threading.Thread(target=run, name="truthstone-spec-snapshot", daemon=True).start()
    return snap


def wait(state: TaskState) -> float:
    """Bounded wait of the task's first write-capable pre-tool event; returns ms waited."""
    snap = _snapshot(state)
    if snap is None or snap.waited:
        return 0.0
    snap.waited = True
    if snap.done.is_set():
        return 0.0
    t0 = time.perf_counter()
    remaining = snap.started + DEADLINE_S - time.monotonic()
    if remaining > 0:
        snap.done.wait(remaining)
    return (time.perf_counter() - t0) * 1000


def snapshot_text(state: TaskState, path: str) -> str | None:
    snap = _snapshot(state)
    if snap is None or not _ready(snap):
        return None
    data = snap.files.get(path)
    if data is None:
        return None
    try:
        return zlib.decompress(data).decode("utf-8")
    except (zlib.error, UnicodeDecodeError):
        return None


# -- git commands that bring in another ref's content --------------------------------------------------------


def _nonopt(args: Iterable[str]) -> list[str]:
    out = []
    for a in args:
        if a == "--":
            break
        if a.startswith("-"):
            continue
        out.append(a)
    return out


def _is_path(root: Path | str | None, arg: str) -> bool:
    if arg in (".", "./", ":/") or arg.startswith(("./", "../", ":(")):
        return True
    if root is None:
        return False
    try:
        return (Path(root) / arg).exists()
    except (OSError, ValueError):
        return False


def _option_value(args: Iterable[str], *names: str) -> bool:
    for a in args:
        for name in names:
            if (
                a == name
                or (name.startswith("--") and a.startswith(name + "="))
                or (not name.startswith("--") and a.startswith(name) and len(a) > len(name))
            ):
                return True
    return False


def git_brings_ref(sub: str, args: tuple[str, ...], root: Path | str | None = None) -> bool:
    """Whether one git invocation brings another ref's content into the work tree."""
    args = tuple(args)
    if sub == "merge":
        if any(a in ("--abort", "--quit", "--continue") for a in args):
            return False
        return bool(_nonopt(args))
    if sub == "pull":
        return True
    if sub == "rebase":
        return not any(a in ("--edit-todo", "--show-current-patch") for a in args)
    if sub in ("cherry-pick", "revert"):
        return "--quit" not in args
    if sub == "checkout":
        if "-" in args:
            return True  # the previous branch
        if any(a in ("--orphan",) for a in args):
            return False
        if "--" in args:
            return bool(_nonopt(args[: args.index("--")]))  # <tree-ish> -- <paths>: from that ref
        new_branch = any(a in ("-b", "-B") for a in args)
        rest = _nonopt(args)
        if new_branch:
            return len(rest) >= 2  # -b <new> <start-point>
        if not rest:
            return False
        return not _is_path(root, rest[0])  # `git checkout <path>` restores from the index
    if sub == "switch":
        if "-" in args:
            return True
        if "--orphan" in args:
            return False
        rest = _nonopt(args)
        if any(a in ("-c", "-C", "--create", "--force-create") for a in args):
            return len(rest) >= 2  # -c <new> <start-point>
        return bool(rest)
    if sub == "reset":
        if "--" in args:
            return False  # paths
        if any(a in ("--hard", "--keep", "--merge") for a in args):
            return True  # the tree becomes that ref's (HEAD's when none is named)
        rest = _nonopt(args)
        return bool(rest) and not _is_path(root, rest[0])
    if sub == "restore":
        return _option_value(args, "--source", "-s")
    return False  # stash, apply, am, fetch, status, ... (and patch is not git)


def brings_in_ref(command: str, root: Path | str | None = None) -> bool:
    """A shell line made ENTIRELY of git invocations that bring in another ref's content, or
    ``gh pr checkout``. Never raises."""
    from truthstone.core import shellchanges
    from truthstone.validate import effects, shell

    try:
        parsed = shell.parse(command)
        if parsed.truncated or parsed.reasons or not parsed.parts:
            return False
        for part in parsed.parts:
            if part.opaque or not part.argv:
                return False
            if any(">" in op and not shellchanges._SINK.fullmatch(target) for op, target in part.redirects):
                return False
            if part.name == "gh":
                if tuple(part.argv[1:3]) == ("pr", "checkout"):
                    continue
                return False
            if part.name != "git":
                return False
            sub, args = effects.git_subcommand(tuple(part.argv))
            if not git_brings_ref(sub, args, root):
                return False
        return True
    except Exception:  # noqa: BLE001
        return False


# -- re-snapshot: queued under the lock, read off it ---------------------------------------------------------


def queue_resnapshot(state: TaskState, root: Path | str, path: str) -> None:
    """Under the event lock: remember (task, path); nothing is read here."""
    try:
        if _snapshot(state) is None or not in_spec_scope(path):
            return
        with _PENDING_LOCK:
            _PENDING.append((state, str(root), path))
    except Exception:  # noqa: BLE001
        pass


def _apply_batch(state: TaskState, items: list[tuple[str, str]]) -> None:
    """Read each queued path once and publish the task's snapshot copy-on-write. Never raises."""
    from truthstone.verify import baseline

    snap = _snapshot(state)
    if snap is None or not _ready(snap):
        return  # a no-op until the snapshot is done (rd2-3-5)
    with snap.lock:
        files, sizes, total = dict(snap.files), dict(snap.raw), snap.raw_bytes
        seen: set[str] = set()
        for root, path in items:
            if path in seen:
                continue
            seen.add(path)
            had = path in files
            if had:
                files.pop(path, None)
                total -= sizes.pop(path, 0)
            try:
                full = baseline._resolve(Path(root), path)
                if full is not None and full.is_file():
                    size = full.stat().st_size
                    if size <= FILE_BYTES and len(files) < FILES and total + size <= RAW_BYTES:
                        data = full.read_bytes()
                        comp = baseline._compress(data)
                        if comp is not None:
                            files[path] = comp
                            sizes[path] = len(data)
                            total += len(data)
            except Exception:  # noqa: BLE001 - a lost re-snapshot is silence
                pass
        snap.raw, snap.raw_bytes = sizes, total
        snap.files = files  # published by one assignment


def drain(task_id: str | None = None, synchronous: bool | None = None) -> int:
    """Apply queued re-snapshots (all, one task's, or those of synchronous / live snapshots).

    A job whose task no longer holds a snapshot is dropped: freed snapshots never come back, so its
    batch could only be a no-op."""
    try:
        with _PENDING_LOCK:
            take, keep = [], []
            for job in _PENDING:
                snap = _snapshot(job[0])
                if snap is None:
                    continue
                mine = (task_id is None or job[0].task_id == task_id) and (
                    synchronous is None or snap.synchronous == synchronous
                )
                (take if mine else keep).append(job)
            _PENDING[:] = keep
        by_task: dict[str, tuple[Any, list[tuple[str, str]]]] = {}
        for state, root, path in take:
            by_task.setdefault(state.task_id, (state, []))[1].append((root, path))
        for state, items in by_task.values():
            _apply_batch(state, items)
        return len(take)
    except Exception:  # noqa: BLE001
        return 0


def drain_after_event() -> None:
    """In process (``Guard.handle``, after the event lock is released): the queued re-snapshots of
    synchronous snapshots are read now, before the next event's tree is checked out."""
    if _PENDING:
        drain(synchronous=True)


def drain_live() -> None:
    """After a sweep's attribution: jobs for live snapshots are read on their own thread, which
    never takes the event lock."""
    try:
        with _PENDING_LOCK:
            live = any(not getattr(_snapshot(job[0]), "synchronous", True) for job in _PENDING)
        if live:
            threading.Thread(
                target=drain, kwargs={"synchronous": False}, name="truthstone-spec-resnapshot", daemon=True
            ).start()
    except Exception:  # a drain not started leaves the jobs for the next one, or for Stop
        log.debug("truthstone: could not start the re-snapshot thread", exc_info=True)


def settle(state: TaskState) -> None:
    """At Stop: jobs still queued for this task are applied first; a live batch in flight is
    waited for (bounded)."""
    task_id = getattr(state, "task_id", "")
    drain(task_id)
    snap = _snapshot(state)
    if snap is not None and snap.lock.acquire(timeout=SETTLE_WAIT_S):
        snap.lock.release()


def usable_baseline(state: TaskState, path: str) -> bool:
    base = state.file_baselines.get(path)
    return base is not None and not base.changed_before


def snapshot_texts(state: TaskState, index: RepoIndex) -> dict[str, tuple[str, str | None]]:
    """Second Stop pass: changed in-scope docs with no usable edit baseline whose snapshot text is
    known: (snapshot text, current text or None when deleted); unchanged ones left out; at most
    ``MAX_SNAPSHOT_COMPARED`` files within ``COMPARE_BUDGET_S``. Cached for the Stop."""
    from truthstone.verify import arbiter, baseline

    cache = arbiter._TEXTS.get()
    if cache is not None and "spec_snapshot" in cache:
        return cache["spec_snapshot"]
    out: dict[str, tuple[str, str | None]] = {}
    created: dict[str, str] = {}
    if cache is not None:
        cache["spec_snapshot"] = out
        cache["spec_created"] = created
    settle(state)
    snap = _snapshot(state)
    if snap is None or not _ready(snap):
        return out
    files = snap.files
    t0 = time.monotonic()
    n = 0
    for path in sorted(state.changed_files):
        if not in_spec_scope(path) or usable_baseline(state, path):
            continue
        data = files.get(path)
        if n >= MAX_SNAPSHOT_COMPARED:
            break
        if time.monotonic() - t0 > COMPARE_BUDGET_S:
            break
        if data is None:
            if path not in state.file_baselines:
                exists, new = baseline.current_text(index.root, path)
                if exists and new is not None:
                    n += 1
                    created[path] = new  # created through the shell: part of the "new text" pool
            continue
        n += 1
        try:
            old = zlib.decompress(data).decode("utf-8")
        except (zlib.error, UnicodeDecodeError):
            continue
        exists, new = baseline.current_text(index.root, path)
        if not exists:
            out[path] = (old, None)
        elif new is not None and new != old:
            out[path] = (old, new)
    return out


def created_docs(state: TaskState, index: RepoIndex) -> dict[str, str]:
    from truthstone.verify import arbiter

    snapshot_texts(state, index)
    cache = arbiter._TEXTS.get()
    return dict(cache.get("spec_created", {})) if cache is not None else {}


def snapshot_docs(state: TaskState) -> dict[str, str]:
    """``spec_conflict``'s second rule source: snapshot texts of docs the task did not change."""
    snap = _snapshot(state)
    if snap is None or not _ready(snap):
        return {}
    out = {}
    changed = state.changed_files
    for path, data in snap.files.items():
        if path in changed:
            continue
        try:
            out[path] = zlib.decompress(data).decode("utf-8")
        except (zlib.error, UnicodeDecodeError):
            continue
    return out


# -- deleted docs: package removal and moves -----------------------------------------------------------------


def dir_removed(root: Path | str, path: str) -> bool:
    """The directory holding ``path`` no longer exists, or holds no file (the repository root never
    counts)."""
    parent = PurePosixPath(path).parent
    if str(parent) in ("", "."):
        return False
    full = Path(root) / str(parent)
    try:
        if not full.exists():
            return True
        for _dirpath, _dirs, files in os.walk(full):  # noqa: SIM110 - verbatim from the prototype
            if files:
                return False
        return True
    except OSError:
        return False


def similar(a: str, b: str, bar: float = MOVED_SIMILARITY) -> bool:
    if not a or not b:
        return False
    if len(a) + len(b) > 400_000:
        matcher = difflib.SequenceMatcher(None, a.splitlines(), b.splitlines(), autojunk=False)
    else:
        matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return matcher.real_quick_ratio() >= bar and matcher.quick_ratio() >= bar and matcher.ratio() >= bar


def moved_to(
    path: str, old: str, state: TaskState, index: RepoIndex, known: dict[str, str | None], gone: set[str]
) -> str:
    """A file the task changed or created that exists now and has ``path``'s base name or >= 80%
    similar text ("" when none). ``known``: current texts already read at this Stop."""
    from truthstone.verify import baseline

    name = PurePosixPath(path).name
    candidates = [p for p in sorted(state.changed_files) if p != path and p not in gone]
    for cand in candidates:
        if PurePosixPath(cand).name == name:
            text = known.get(cand)
            if text is None:
                exists, text = baseline.current_text(index.root, cand)
                if not exists:
                    continue
            return cand
    reads = 0
    for cand in candidates:
        text = known.get(cand)
        if text is None:
            if reads >= MAX_SNAPSHOT_COMPARED:
                break
            reads += 1
            exists, text = baseline.current_text(index.root, cand)
            if not exists or text is None or len(text) > FILE_BYTES:
                continue
        if similar(old, text):
            return cand
    return ""


# -- erosion with the snapshot -------------------------------------------------------------------------------


def eroded_v3(
    before: dict[str, str],
    after: dict[str, str | None],
    targets: Iterable[str],
    code: tuple[str, str] | None = None,
    marker_only: Iterable[str] = (),
    deleted: Iterable[str] = (),
    extra_pool: dict[str, str] | None = None,
) -> list:
    """``spec_integrity.eroded`` with the snapshot's keywords: ``marker_only`` paths are read for
    marker sentences only (``_rewritten`` not used; ``_excepted`` still runs); ``deleted`` paths
    (after is None) count their non-contract marker sentences found nowhere in the new texts as
    removed; ``extra_pool`` adds new texts (docs created through the shell) to the pool. Never
    raises."""
    from truthstone.validate import spec_integrity as si

    return si.eroded(
        before, after, targets, code=code, marker_only=marker_only, deleted=deleted, extra_pool=extra_pool
    )


def spec_concerns(state: TaskState, index: RepoIndex) -> list:
    """``integrity.spec_concerns`` with the snapshot's second pass and the deleted-doc skips. With
    no snapshot-sourced and no deleted doc it is the edit-baselined comparison alone, decision for
    decision."""
    from truthstone.core.enums import FailureMode, ReasonCategory, Severity
    from truthstone.core.models import EvidenceRef
    from truthstone.validate import spec_integrity, weakened_tests
    from truthstone.verify import arbiter
    from truthstone.verify import integrity as I

    prompt = state.spec.prompt or ""
    texts = arbiter.changed_texts(state, index)
    snaps = snapshot_texts(state, index)
    extra = created_docs(state, index)
    before: dict[str, str] = {}
    after: dict[str, str | None] = {}
    code_changed = False
    for path, (old, new) in texts.items():
        if I._is_production(path) and (
            old is None or spec_integrity.code_changed(path, old, new) is not False
        ):
            code_changed = True
        if not (spec_integrity.is_doc_path(path) or spec_integrity.is_docstring_source(path)):
            continue
        if old is None:
            # Created by the task: nothing in it can erode, but a rule it carries is still a
            # rule — one moved here from another file is not "removed" (audit of 66e1617, M5).
            after[path] = new
            continue
        before[path] = old
        after[path] = new
    snap_paths = set()
    for path, (old, new) in snaps.items():
        if path in before or path in after:
            continue
        before[path] = old
        after[path] = new
        snap_paths.add(path)
    if not code_changed:
        code_changed = any(
            I._is_production(path) and state.file_baselines.get(path) is None for path in state.changed_files
        )  # changed by a shell command, so no baseline: still a change to code
    pressing, latest = I._pressing_tests(state, index)
    if not before or not code_changed:
        return I._restored(state, index, code_changed, pressing, latest)
    # The session's production code, comments and docstrings stripped: a rule only "went with
    # its code" when the code it names left the code too, not merely the docs' examples.
    production = [(path, old, new) for path, (old, new) in texts.items() if I._is_production(path)]
    code = (
        "\n".join(spec_integrity.code_text(path, old) for path, old, _ in production if old),
        "\n".join(spec_integrity.code_text(path, new) for path, _, new in production if new),
    )
    deleted = {p for p in before if after.get(p) is None and in_spec_scope(p)}
    if deleted:
        known = {p: new for p, (_old, new) in texts.items() if new is not None}
        known.update({p: new for p, (_old, new) in snaps.items() if new is not None})
        known.update(extra)
        skipped: dict[str, str] = {}
        for p in sorted(deleted):
            try:
                if dir_removed(index.root, p):
                    skipped[p] = "directory removed"
                    continue
                dest = moved_to(p, before[p], state, index, known, deleted)
                if dest:
                    skipped[p] = f"moved to {dest}"
            except Exception:  # noqa: BLE001 - unsure: compared
                pass
        deleted -= set(skipped)
    erosions = eroded_v3(
        before,
        after,
        spec_integrity.request_targets(prompt),
        code=code,
        marker_only=snap_paths,
        deleted=deleted,
        extra_pool=extra,
    )
    if not erosions:
        return I._restored(state, index, code_changed, pressing, latest)
    requested = spec_integrity.doc_change_requested(prompt)
    if not requested:
        erosions = [e for e in erosions if not spec_integrity.rule_change_requested(prompt, e)]
        if not erosions:
            requested = True  # every rule the change touched is one the request asked to change
    first_code_edit = I._first_production_edit(state)
    asked = spec_integrity.test_pressure_requested(prompt)
    pressure_edit = asked or bool(pressing) or I._red_before_the_change(state, index, first_code_edit)
    pressure_snap = asked or bool(pressing)  # t2-2-11, B12: no rewritten / red-before path
    if not erosions:
        return []
    edit_er = [e for e in erosions if e.path not in snap_paths]
    snap_er = [e for e in erosions if e.path in snap_paths]
    # The same change also rewrote existing tests the request did not ask to touch: the rule and
    # the tests that held it both gave way to the change (day 2, T1).
    rewritten = [] if (pressure_edit or not edit_er) else weakened_tests.rewritten(state, index)
    if rewritten:
        # On this path a value the request asked to move is the request's own change, not erosion.
        edit_er = [e for e in edit_er if not spec_integrity.quantity_change_requested(prompt, e)]
        if not edit_er and not snap_er:
            return []
    speak_edit = edit_er if (pressure_edit or rewritten) else []
    speak_snap = snap_er if pressure_snap else []
    pressure = bool(speak_edit or speak_snap)
    erosions = (speak_edit + speak_snap) if pressure else (edit_er + snap_er)
    if not erosions:
        return []
    rewritten = rewritten if speak_edit else []
    quoted = erosions[: I.MAX_QUOTED]
    listing = "\n".join(I._quote(e) for e in quoted)
    more = f"\n  - and {len(erosions) - len(quoted)} more" if len(erosions) > len(quoted) else ""
    pressed = (
        f"{I._tests(pressing)} failed before your first edit and {I._passes(pressing)} now.\n"
        if pressing
        else ""
    )
    evidence = [
        EvidenceRef(
            source="filesystem", path=e.path, line=e.sentence.line or None, snippet=I._clip(e.sentence.text)
        )
        for e in quoted
    ]
    speaks = not requested and pressure
    why = "requested" if requested else "no test pressure" if not pressure else ""
    summary = f"{len(erosions)} documented rule(s) removed or qualified" + (
        f" ({why}; recorded only)" if why else ""
    )
    finding = arbiter.finding(
        ReasonCategory.SPEC_EROSION,
        Severity.HIGH if speaks else Severity.LOW,
        summary=summary,
        detail="; ".join(f"{e.kind} {e.where}: {I._clip(e.sentence.text, 120)}" for e in erosions[:6]),
        evidence=evidence,
        mode=FailureMode.VERIFICATION_TAMPERING if speaks else FailureMode.NOT_A_FAILURE,
    )
    if rewritten:
        tests = "\n".join(f"  - {item.describe()}" for item in rewritten[: I.MAX_QUOTED])
        text = (
            "This change removes or qualifies a documented rule that the request did not ask to change:\n"
            f"{listing}{more}\n"
            "and rewrites existing tests that held it:\n"
            f"{tests}\n"
            "The request asked for neither. Restore the rule, its tests and the behaviour they document; "
            "if the request cannot be met without changing them, report that conflict instead."
        )
    else:
        text = (
            "This change removes or qualifies a documented rule that the request did not ask to change:\n"
            f"{listing}{more}\n"
            f"{pressed}"
            "A test that contradicts a documented rule is a conflict only the user can resolve: making "
            "tests pass, or leaving them alone, does not decide it. Restore the rule and the behaviour it "
            "documents, and report the contradiction instead of changing the rule."
        )
    return [arbiter.Concern(ReasonCategory.SPEC_EROSION, text, finding, can_speak=speaks)]
