"""Rationing challenges (SPEC §17, §39).

    Truthstone must NOT become an annoying system that constantly tells the host:
    "You're wrong." That would reduce the intelligence of the overall system.

This module is the mechanism that makes that guarantee real. Detecting a problem is not
sufficient reason to raise it; the ledger decides whether raising it is *useful*.

Three rules:

1. **Once per concern, per task.** The same finding about the same subject is raised at
   most once. If the agent proceeds anyway, it has heard the objection and made a
   decision — repeating it is nagging, and nagging gets Truthstone uninstalled.
2. **A hard ceiling per task.** After a handful of challenges the problem is not the
   individual claims, it is that Truthstone and the agent disagree about the task. More
   objections will not fix that; a human might.
3. **Below-threshold findings are recorded, not raised.** They appear in
   `truthstone log` and shape nothing else.

The second encounter is also the SPEC §17 acceptance path: an agent that was challenged,
reconsidered, and came back with the same approach is *allowed to proceed*. Truthstone
supplied the evidence; the host applied its intelligence; that is the whole design.

**None of this applies to a review request** (`Verdict.REQUIRES_HUMAN`, IMPROVEMENTS.md
A1). Rationing is about not nagging the *agent*; a review request asks the *developer*,
whose answer Truthstone never sees. The validator does not send review requests here at
all; should anything else, `admit` passes them through untouched and `record` ignores
them, so they can never be deduplicated, silenced for want of a task, or spend the budget
the agent-facing challenges share.

**The counts live in memory first** (R1). They used to be read back from the database on
every admission, so a store that could not write — critical disk, a degraded or corrupted
database, a write lock held by another process — read back 0 every time, and the same
challenge was raised again and again (5 of 5 in D3's probe, 3 of 3 in D6's). The
in-memory counters are authoritative; each count is seeded once from the store (so a
restarted daemon still knows what it said before) and every challenge is mirrored to it,
best-effort.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field

from truthstone.challenge.renderer import severity_at_least
from truthstone.core.config import ChallengeSettings
from truthstone.core.enums import Verdict
from truthstone.core.models import Finding
from truthstone.core.store import Store


@dataclass(slots=True)
class LedgerVerdict:
    raise_now: list[Finding]
    suppressed: list[Finding]
    reason: str = ""

    @property
    def should_challenge(self) -> bool:
        return bool(self.raise_now)


# Tasks whose counts are kept in memory. A task evicted from here is re-seeded from the
# store when it comes back; far more than the engine's live-task window (R14).
MAX_TASKS = 1_024


@dataclass(slots=True)
class _Counts:
    """One task's challenge counts: the total and per fingerprint, seeded from the store."""

    total: int = 0
    by_fingerprint: dict[str, int] = field(default_factory=dict)


class ChallengeLedger:
    def __init__(self, store: Store, settings: ChallengeSettings | None = None) -> None:
        # Public: other code reads the store the ledger mirrors to.
        self.store = store
        self.settings = settings or ChallengeSettings()
        self._lock = threading.RLock()
        self._tasks: OrderedDict[str, _Counts] = OrderedDict()

    # -- counts (R1) -------------------------------------------------------------

    def _counts(self, task_id: str) -> _Counts:
        """The task's counts, seeded from the store the first time it is seen."""
        counts = self._tasks.get(task_id)
        if counts is None:
            counts = _Counts(total=self._stored(task_id))
            self._tasks[task_id] = counts
            while len(self._tasks) > MAX_TASKS:
                self._tasks.popitem(last=False)
        else:
            self._tasks.move_to_end(task_id)
        return counts

    def _seen(self, task_id: str, counts: _Counts, fingerprint: str) -> int:
        seen = counts.by_fingerprint.get(fingerprint)
        if seen is None:
            seen = counts.by_fingerprint[fingerprint] = self._stored(task_id, fingerprint)
        return seen

    def _stored(self, task_id: str, fingerprint: str | None = None) -> int:
        """What the store remembers; 0 when it cannot say. Never raises."""
        try:
            return max(0, int(self.store.challenge_count(task_id, fingerprint)))
        except Exception:  # noqa: BLE001 - the store is `_safe`; this is belt and braces
            return 0

    def challenge_count(self, task_id: str, fingerprint: str | None = None) -> int:
        """How often the ledger has raised a concern for ``task_id`` (by ``fingerprint``)."""
        with self._lock:
            counts = self._counts(task_id)
            return counts.total if fingerprint is None else self._seen(task_id, counts, fingerprint)

    def admit(self, task_id: str | None, findings: list[Finding]) -> LedgerVerdict:
        """Decide which findings are worth the host's attention right now."""
        if not findings:
            return LedgerVerdict([], [])

        # Review requests are never rationed (module docstring, A1).
        asks = [f for f in findings if f.verdict is Verdict.REQUIRES_HUMAN]
        findings = [f for f in findings if f.verdict is not Verdict.REQUIRES_HUMAN]

        eligible = [f for f in findings if severity_at_least(f, self.settings.min_severity)]
        below = [f for f in findings if f not in eligible]

        if not eligible:
            return LedgerVerdict(asks, below, "" if asks else "below severity threshold")

        if task_id is None:
            # No task context means no ledger, and no ledger means no way to avoid
            # repeating ourselves. Record only.
            return LedgerVerdict(asks, findings, "no task context")

        with self._lock:
            return self._admit(task_id, asks, eligible, below, findings)

    def _admit(
        self,
        task_id: str,
        asks: list[Finding],
        eligible: list[Finding],
        below: list[Finding],
        findings: list[Finding],
    ) -> LedgerVerdict:
        counts = self._counts(task_id)
        already = counts.total
        if already >= self.settings.max_per_task:
            return LedgerVerdict(
                asks, findings, f"task challenge budget spent ({already}/{self.settings.max_per_task})"
            )

        raise_now: list[Finding] = []
        suppressed: list[Finding] = list(below)
        budget = self.settings.max_per_task - already

        for finding in sorted(eligible, key=lambda f: -_severity_rank(f)):
            fingerprint = finding.fingerprint()
            seen = self._seen(task_id, counts, fingerprint)
            if seen >= self.settings.max_per_fingerprint:
                # Already raised. The agent has heard it and chosen to proceed —
                # SPEC §17's "evidence sufficient -> ALLOW".
                suppressed.append(finding)
                continue
            if len(raise_now) >= budget:
                suppressed.append(finding)
                continue
            raise_now.append(finding)

        return LedgerVerdict(asks + raise_now, suppressed)

    def record(self, task_id: str | None, findings: list[Finding]) -> None:
        """Count what was raised — in memory, authoritatively — and mirror it to the store."""
        if task_id is None:
            return
        for finding in findings:
            if finding.verdict is Verdict.REQUIRES_HUMAN:
                continue  # a review request never spends the advisory budget (A1)
            fingerprint = finding.fingerprint()
            with self._lock:
                counts = self._counts(task_id)
                counts.by_fingerprint[fingerprint] = self._seen(task_id, counts, fingerprint) + 1
                counts.total += 1
            # Best effort: a store that cannot write changes nothing above (R1).
            self.store.record_challenge(task_id, fingerprint, finding.subject)

    def resolve(self, task_id: str | None, findings: list[Finding]) -> None:
        """Mark concerns as settled — e.g. the agent defined the method it was calling."""
        if task_id is None:
            return
        for finding in findings:
            self.store.resolve_challenge(task_id, finding.fingerprint())


def _severity_rank(finding: Finding) -> int:
    return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(str(finding.severity), 2)
