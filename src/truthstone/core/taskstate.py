"""Per-task working state (SPEC §18, §19).

Scope checking and the Completion Gate both need the same thing: what has actually
happened during *this* task. Which files were touched, which test commands ran and what
they said, how many times the gate has already spoken.

Lives in memory, on the daemon, for the life of the task. Nothing here needs to survive a
restart — a lost task simply means the next action is evaluated without history, which
degrades to ALLOW.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from truthstone.intent.models import TaskSpec
from truthstone.verify.baseline import FileBaseline
from truthstone.verify.runners import VerificationState

# A task that has been running long enough to have touched this many files without any
# of them being in the expected scope is not the task that was asked for.
DEFAULT_UNRELATED_LIMIT = 5


@dataclass(slots=True)
class TaskState:
    task_id: str
    spec: TaskSpec
    started_at: float = field(default_factory=time.time)
    # The host session owns the task.  Keeping this alongside the in-memory state lets
    # the engine reject a stale or forged task id from another concurrent session.
    session_id: str = ""

    touched_files: set[str] = field(default_factory=set)
    deleted_files: set[str] = field(default_factory=set)
    # Files this task brought into existence: a TDD red phase may fail only in tests it
    # wrote itself (G4a).
    created_files: set[str] = field(default_factory=set)
    verification: VerificationState = field(default_factory=VerificationState)

    # How many times the Completion Gate has held this task open. Capped, so a
    # disagreement between Truthstone and the agent cannot become a loop (SPEC §19).
    stop_blocks: int = 0
    scope_challenged: bool = False
    # The completion arbiter's categories already raised with the agent in this task
    # (``ReasonCategory`` values): each reason is challenged at most once (v0.2 M1).
    raised_categories: set[str] = field(default_factory=set)

    # Verification is a timeline (G2a). Every change and every test run takes the next
    # number, so the gate can ask what a run actually saw: the latest run decides, and a
    # change made after the latest pass leaves that pass stale.
    seq: int = 0
    last_change_seq: dict[str, int] = field(default_factory=dict)
    # The position of the task's first change: a test that was already failing before it
    # is not the task's doing (v0.2 M1, "baseline red"). 0 until the first change.
    first_change_seq: int = 0
    # The tests that covered a file when it was deleted (G5). The index forgets a deleted
    # file, and with it which tests reached it; without this snapshot deleting covered
    # code looked like a change nothing tests.
    deleted_coverage: dict[str, set[str]] = field(default_factory=dict)
    # Whether each file parsed before this task first changed it (G15). The syntax gate
    # blames only files the task broke: a template that never parsed is not its doing.
    parse_baseline: dict[str, bool] = field(default_factory=dict)
    # Each file as the task found it, taken just before its first change (G2b): a file
    # whose bytes are back to this is no change, and a Python file first changed after a
    # passing run is compared with it for a comment-only edit.
    file_baselines: dict[str, FileBaseline] = field(default_factory=dict)
    # The code of each touched Python file at each passing run, by the run's sequence
    # number (G2b, bounded): a file edited after the pass whose code is unchanged — a
    # comment, formatting — keeps the pass.
    pass_fingerprints: dict[str, dict[int, str]] = field(default_factory=dict)

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def touch(self, path: str) -> None:
        self.touched_files.add(path)
        self.deleted_files.discard(path)  # written again after a deletion
        self.last_change_seq[path] = self.next_seq()
        self.first_change_seq = self.first_change_seq or self.seq

    def delete(self, path: str, covering: set[str] | None = None) -> None:
        """Record a deletion: a change to ``path`` that leaves nothing on disk.

        The path stays among the touched files (scope still sees it), and ``covering``
        keeps the tests that reached it before the index forgot them.
        """
        self.touched_files.add(path)
        self.deleted_files.add(path)
        self.created_files.discard(path)
        self.last_change_seq[path] = self.next_seq()
        self.first_change_seq = self.first_change_seq or self.seq
        if covering:
            self.deleted_coverage.setdefault(path, set()).update(covering)

    @property
    def changed_files(self) -> set[str]:
        return self.touched_files | self.deleted_files

    def unrelated_files(self, blast: set[str] | None = None) -> set[str]:
        """Touched files that the task does not plausibly reach.

        "Plausibly" is generous on purpose: the expected scope, anything importing or
        imported by it, and its tests all count as related. SPEC §18's example is an agent
        editing *17 unrelated files* while fixing login validation — the signal worth
        catching is wholesale drift, not an adjacent helper.
        """
        if not self.spec.expected_scope:
            return set()  # nothing was resolved, so nothing can be called unrelated
        related = set(self.spec.expected_scope) | (blast or set())
        return {path for path in self.touched_files if path not in related}
