"""Changes a shell command made reach the task (G5).

Edit and Write name the file they change; a shell command does not. `sed -i`, a codemod, a
generator, `git mv` and `rm` changed files that the index learned about at its next sweep,
but the *task* never did: `touched_files` stayed empty, so the Completion Gate never asked
for tests (D6 E12: the same change made with `sed -i` was silent, made with Edit it
blocked; D5: after `rm` of a covered file the gate passed).

What a sweep finds (`RepoIndex.refresh_delta`) is attributed here, to the shell commands
that could have made it, at the place on the task's timeline each command took:

* **A reservation per command.** A shell command that may write (anything but a
  read-only command, A4) reserves a sequence number on its task's timeline when its
  post-tool event arrives: *before* its own test run when that run is the command's last
  stage (`sed -i … && pytest -q | tail`), *after* it otherwise — conservatively, since a
  change after a pass leaves the pass stale. A sweep that lands later (rate-limited, or in
  the background) stamps the change with the reserved number, so it still sits where the
  command made it, on the task that ran the command.
* **Attribution by time.** A file the sweep saw added or modified goes to the reservation
  whose command window holds the file's change time — the later of mtime and ctime, so a
  move or a `cp -p` counts when it happened. A window runs from the command's PreToolUse
  (when one was seen) to its post-tool event. A change outside every window — the
  developer's own edit, saved before the command started or after it finished — is
  nobody's. A removed file has no time: it goes to the task's latest open reservation.
* **Only what the index tracks.** The delta is the index's own, so ignored files and build
  outputs (`IndexSettings.exclude_dirs`) never appear in it.
* **What a removed file was covered by** is read from the index as it was *before* the
  sweep (`Snapshot`), as the Delete tool's branch reads it before `refresh_path`: after
  the sweep nothing says which tests reached it.

Everything here mutates `TaskState` through its public fields; callers hold the
workspace's event lock while applying a sweep. Nothing here raises.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from truthstone.core.taskstate import TaskState
from truthstone.repo import symbols_ts
from truthstone.repo.index import IndexDelta, RepoIndex
from truthstone.validate import shell
from truthstone.verify import commands, spec_snapshot

log = logging.getLogger(__name__)

# Timestamp granularity and clock tolerance around a command's window. File times come
# from the filesystem, window edges from the daemon's clock; on one machine they agree to
# well under a millisecond (APFS and ext4 keep nanoseconds), but coarse filesystems round.
SLACK_S = 1.0
# Bounds: reservations nobody swept for this long are dropped (the sweep they waited for
# was never going to come — an index that never finished building, say).
MAX_RESERVATIONS = 256
RESERVATION_TTL_S = 900.0
MAX_STARTS = 512

# Stages that may follow a test run without making the run "not the last stage": they
# filter or report its output and change no file (redirections are checked separately).
_AFTER_RUN = frozenset(
    {
        "tail", "head", "grep", "egrep", "fgrep", "rg", "cat", "sort", "uniq", "cut", "nl",
        "column", "wc", "less", "more", "ts", "tr", "true", "false", ":", "echo", "printf",
        "exit",
    }
)
# Redirection targets that are not files (the A4 classifier's rule).
_SINK = re.compile(r"/dev/(?:null|stdout|stderr|tty)|&?-|&?\d{1,2}")


def changes_precede_run(command: str) -> bool:
    """Whether everything ``command`` changed happened before its test run (G5, G1).

    True when the run whose result the command reports is its last stage — followed at
    most by stages that only filter or report its output (`| tail`, `|| true`). Then
    `sed -i … && pytest` changed the files the run checked. Anything else after the run,
    or a line that cannot be fully read, is False: the change may have come after it.
    """
    try:
        parsed = shell.parse(command)
        if parsed.truncated or parsed.reasons:
            return False
        parts = parsed.parts
        last = None
        for index, part in enumerate(parts):
            if commands.test_invocations(part.text):
                last = index  # nested `sh -c` parts follow their parent: the innermost wins
        if last is None:
            return False
        for part in parts[last + 1 :]:
            if part.opaque or not part.argv or part.name not in _AFTER_RUN:
                return False
            if any(">" in operator and not _SINK.fullmatch(target) for operator, target in part.redirects):
                return False
        return True
    except Exception:  # unsure is "after the run", never an exception
        log.debug("truthstone: could not read a shell command's stages", exc_info=True)
        return False


@dataclass(slots=True)
class Reservation:
    """A place on a task's timeline, held for the changes one shell command made."""

    task_id: str
    session_id: str
    seq: int
    at: float  # wall clock: the command had finished (its post-tool event was handled)
    started: float | None = None  # wall clock of its PreToolUse, when one was seen
    made: float = field(default_factory=time.monotonic)
    # The command was made entirely of git invocations that bring in another ref's content
    # (``spec_snapshot.brings_in_ref``): the docs credited to it are re-snapshotted (C2).
    rewrites_tree: bool = False


@dataclass(slots=True)
class Snapshot:
    """The index's coverage and parse results as they were just before a sweep.

    Copies of the top-level maps only (C-level copies, atomic under the GIL); the sweep
    replaces derived maps and per-file results rather than editing the objects held here.
    """

    started: float  # wall clock when the sweep began
    tests_by_source: dict[str, set[str]]
    dependents: dict[str, set[str]]
    parsed: dict[str, Any]

    @classmethod
    def take(cls, index: RepoIndex) -> Snapshot:
        return cls(
            started=time.time(),
            tests_by_source=index.tests_by_source.copy(),
            dependents=index.dependents.copy(),
            parsed=index.parsed.copy(),
        )

    def covering(self, path: str) -> set[str]:
        """The tests that reached ``path`` before the sweep: as `runners.affected_tests`
        reads them — its own tests and its direct dependents' tests."""
        tests = set(self.tests_by_source.get(path, ()))
        for dependent in self.dependents.get(path, ()):
            tests.update(self.tests_by_source.get(dependent, ()))
        return tests

    def parsed_before(self, path: str, lang: str) -> bool | None:
        """Whether ``path`` parsed before the sweep (G15), or None when unknown."""
        if lang != "python" and not symbols_ts.available(lang):
            return None
        before = self.parsed.get(path)
        return True if before is None else bool(before.parsed)


def changed_at(index: RepoIndex, path: str) -> float | None:
    """When ``path`` last changed: the later of its mtime and ctime, in seconds."""
    try:
        st = os.stat(index.root / path)
    except (OSError, ValueError):
        return None
    return max(st.st_mtime_ns, st.st_ctime_ns) / 1e9


def _owner(reservations: list[Reservation], when: float) -> Reservation | None:
    """The reservation whose command window holds a change made at ``when``: the earliest
    that finished after it (and had started before it), else — within the slack — the
    latest."""
    for reservation in reservations:
        if reservation.started is not None and when < reservation.started - SLACK_S:
            continue
        if when <= reservation.at:
            return reservation
    last = reservations[-1]
    if when <= last.at + SLACK_S and (last.started is None or when >= last.started - SLACK_S):
        return last
    return None


def mark_changed(state: TaskState, path: str, seq: int, created: bool = False) -> None:
    """`TaskState.touch` at a reserved place on the timeline."""
    state.touched_files.add(path)
    state.deleted_files.discard(path)
    if created:
        state.created_files.add(path)
    state.last_change_seq[path] = max(state.last_change_seq.get(path, 0), seq)


def mark_removed(state: TaskState, path: str, seq: int, covering: Iterable[str] = ()) -> None:
    """`TaskState.delete` at a reserved place on the timeline."""
    state.touched_files.add(path)
    state.deleted_files.add(path)
    state.created_files.discard(path)
    state.last_change_seq[path] = max(state.last_change_seq.get(path, 0), seq)
    covering = set(covering)
    if covering:
        state.deleted_coverage.setdefault(path, set()).update(covering)


class ShellChanges:
    """One workspace's open reservations, and the attribution of what sweeps find."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reservations: list[Reservation] = []
        self._starts: OrderedDict[tuple[str, str], float] = OrderedDict()

    # -- the commands ---------------------------------------------------------------

    def note_start(self, session_id: str, tool_use_id: str | None) -> None:
        """A shell command is about to run: its window opens now."""
        if not tool_use_id:
            return
        with self._lock:
            self._starts[(session_id, tool_use_id)] = time.time()
            while len(self._starts) > MAX_STARTS:
                self._starts.popitem(last=False)

    def reserve(
        self, state: TaskState, tool_use_id: str | None = None, rewrites_tree: bool = False
    ) -> Reservation:
        """Hold the next place on ``state``'s timeline for what this command changed.
        ``rewrites_tree``: the command brings in another ref's content (C2's re-snapshot)."""
        with self._lock:
            started = self._starts.pop((state.session_id, tool_use_id), None) if tool_use_id else None
            reservation = Reservation(
                task_id=state.task_id,
                session_id=state.session_id,
                seq=state.next_seq(),
                at=time.time(),
                started=started,
                rewrites_tree=rewrites_tree,
            )
            self._reservations.append(reservation)
            self._expire()
        return reservation

    def pending(self, task_id: str | None = None) -> bool:
        """Whether a reservation (for ``task_id``, or any) still waits for a sweep."""
        with self._lock:
            return any(task_id is None or r.task_id == task_id for r in self._reservations)

    def pending_tasks(self) -> set[str]:
        with self._lock:
            return {r.task_id for r in self._reservations}

    def forget_session(self, session_id: str) -> None:
        with self._lock:
            self._reservations = [r for r in self._reservations if r.session_id != session_id]
            for key in [key for key in self._starts if key[0] == session_id]:
                del self._starts[key]

    def _expire(self) -> None:
        cutoff = time.monotonic() - RESERVATION_TTL_S
        self._reservations = [r for r in self._reservations if r.made >= cutoff][-MAX_RESERVATIONS:]

    # -- the sweeps -----------------------------------------------------------------

    def apply(
        self,
        delta: IndexDelta,
        snapshot: Snapshot,
        index: RepoIndex,
        lookup: Callable[[str], TaskState | None],
    ) -> int:
        """Attribute what one sweep found; returns how many (path, task) changes landed.

        Reservations whose command finished before the sweep began are settled by it:
        whatever they changed, the sweep saw. Later ones stay open for the next sweep.

        A path credited to a command that brought in another ref's content (``rewrites_tree``)
        is queued for its task's documentation snapshot (C2, ``verify/spec_snapshot.py``); the
        queue is read off the event lock, never here.
        """
        try:
            return self._attribute(delta, snapshot, index, lookup)
        finally:
            spec_snapshot.drain_live()

    def _attribute(
        self,
        delta: IndexDelta,
        snapshot: Snapshot,
        index: RepoIndex,
        lookup: Callable[[str], TaskState | None],
    ) -> int:
        if not delta.swept:
            return 0
        with self._lock:
            candidates = list(self._reservations)
        landed = 0
        try:
            by_task: dict[str, list[Reservation]] = {}
            for reservation in sorted(candidates, key=lambda r: r.at):
                by_task.setdefault(reservation.task_id, []).append(reservation)
            states = {task_id: lookup(task_id) for task_id in by_task}
            for path in sorted(delta.added | delta.modified):
                when = changed_at(index, path)
                if when is None:
                    continue  # gone again since the sweep: the next sweep sees the removal
                record = index.files.get(path)
                for task_id, reservations in by_task.items():
                    state = states.get(task_id)
                    owner = _owner(reservations, when) if state is not None else None
                    if owner is None:
                        continue
                    if path not in state.parse_baseline and record is not None:
                        parsed = True if path in delta.added else snapshot.parsed_before(path, record.lang)
                        if parsed is not None:
                            state.parse_baseline[path] = parsed
                    mark_changed(state, path, owner.seq, created=path in delta.added)
                    if owner.rewrites_tree:
                        spec_snapshot.queue_resnapshot(state, index.root, path)
                    landed += 1
            for path in sorted(delta.removed):
                covering = snapshot.covering(path)
                for task_id, reservations in by_task.items():
                    state = states.get(task_id)
                    if state is None:
                        continue
                    mark_removed(state, path, reservations[-1].seq, covering)
                    if reservations[-1].rewrites_tree:
                        spec_snapshot.queue_resnapshot(state, index.root, path)
                    landed += 1
        except Exception:  # a lost attribution is "judged as before", never a crash
            log.exception("truthstone: could not attribute a sweep's changes; continuing")
        finally:
            settled = {id(r) for r in candidates if r.at <= snapshot.started}
            with self._lock:
                self._reservations = [r for r in self._reservations if id(r) not in settled]
        return landed
