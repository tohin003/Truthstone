"""The failure-mode census (Phase 7, SPEC §3 · §37).

Reads what AgentGuard has already recorded and ranks SPEC §3's seventeen failure modes by
how often they were actually observed. No new machinery: every finding needed for this has
been written to SQLite since Phase 0. What was missing was the taxonomy on each finding
and the discipline about what may be reported.

Four properties the renderer is responsible for, all of them about not overstating.

**Modes with no detector are a separate section, never a zero row.** Sorting seventeen
modes by count would put six uninstrumented ones at the bottom next to genuinely rare
ones, and the reader would have no way to tell "never happened" from "never looked".

**A detector counts only where its host feeds it (H7).** The completion gate runs on a
stop event; scope and the gate judge a task, which a prompt event opens. On a host that
sends neither, those modes were never looked at, and "instrumented, never observed" would
be exactly the unmeasured zero the rule above forbids. So activity is grouped by host
(``sessions.agent``), each host's events are what its capability profile declares plus
what it was actually recorded sending, and a mode its host cannot feed is reported as
"not instrumented on <host>" — never as a zero, and never in a rate's denominator.

**Rates carry their denominator.** "Observed in 9 of 41 tasks" survives being quoted;
"22%" does not. The denominator is the tasks on hosts that could have shown the mode, and
an observation outside any task (a host without a prompt event) counts as an occurrence,
never as a task of its own.

**Guarded and unguarded observations are counted separately.** A session in which
AgentGuard was challenging and injecting planning budgets describes a steered agent. Its
failure rate is a different quantity from the unguarded baseline the census exists to
establish, and averaging the two produces a number that is neither.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from agentguard.census.taxonomy import (
    ALL_MODES,
    EXTENDED_TAXONOMY,
    NOT_INSTRUMENTED_BECAUSE,
    TAXONOMY,
    ModeSpec,
)
from agentguard.core.enums import EventType, FailureMode
from agentguard.core.hosts import CONSERVATIVE, HostCapabilities, capabilities_for
from agentguard.core.store import ProjectStore

# -- what each detector needs from a host (H7) -----------------------------------------------

TASK = "task"  # a prompt event: tasks are opened there, and scope and the gate judge one
PRE_TOOL = str(EventType.PRE_TOOL_USE)
POST_TOOL = str(EventType.POST_TOOL_USE)
STOP = str(EventType.STOP)

NEED_TEXT = {
    TASK: "no prompt event, so no task",
    PRE_TOOL: "no pre-tool event",
    POST_TOOL: "no post-tool event",
    STOP: "no stop event",
}

DETECTOR_NEEDS: dict[FailureMode, tuple[str, ...]] = {
    # The evidence engine and the action validator judge one proposed action.
    FailureMode.HALLUCINATED_FILE: (PRE_TOOL,),
    FailureMode.HALLUCINATED_API: (PRE_TOOL,),
    FailureMode.INVENTED_FUNCTION: (PRE_TOOL,),
    FailureMode.INVENTED_LIBRARY: (PRE_TOOL,),
    FailureMode.UNNECESSARY_DEPENDENCY: (PRE_TOOL,),
    FailureMode.IGNORED_REPO_PATTERN: (PRE_TOOL,),
    FailureMode.DESTRUCTIVE_ACTION: (PRE_TOOL,),
    # Bypass flags and self-protection (A8, A9) judge a command or write before it runs;
    # the secrets check (A11) judges the content a write proposes.
    FailureMode.VERIFICATION_TAMPERING: (PRE_TOOL,),
    FailureMode.SECRET_EXPOSURE: (PRE_TOOL,),
    # Scope judges a task's changed files against what the task asked for.
    FailureMode.OVERPLANNED_TRIVIAL: (TASK, PRE_TOOL, POST_TOOL),
    FailureMode.UNRELATED_FILES_MODIFIED: (TASK, PRE_TOOL, POST_TOOL),
    # The completion gate judges a task's changes and test runs when the agent stops.
    FailureMode.FALSE_COMPLETION: (TASK, POST_TOOL, STOP),
    FailureMode.INSUFFICIENT_TESTS: (TASK, POST_TOOL, STOP),
    FailureMode.UNVERIFIED_CHANGE: (TASK, POST_TOOL, STOP),
}
# A detector added without an entry above is taken to need everything, so its silence is
# never read as a measurement on a host that may not feed it (`test_census_hosts` checks
# that every instrumented mode has an entry).
ALL_NEEDS: tuple[str, ...] = (TASK, PRE_TOOL, POST_TOOL, STOP)


def needs(mode: FailureMode) -> tuple[str, ...]:
    return DETECTOR_NEEDS.get(mode, ALL_NEEDS)


def declared_events(caps: HostCapabilities) -> set[str]:
    """What a known host's capability profile says it delivers.

    A profile records what a host can be *told*, which implies what it sends: a context
    channel exists only on an event the host fires, a pre-tool deny needs a pre-tool event,
    a Stop continuation a stop event. An unknown host's profile (CONSERVATIVE) is a list of
    assumptions, not observations, so it declares nothing: only what that host was
    recorded sending counts.
    """
    if caps is CONSERVATIVE:
        return set()
    events = {str(channel) for channel in caps.context_channels}
    if caps.can_block_pre:
        events.add(PRE_TOOL)
    if caps.stop_continue != "none":
        events.add(STOP)
    if caps.failure_event:
        events.add(str(EventType.POST_TOOL_FAILURE))
    return events


@dataclass(slots=True)
class HostActivity:
    """One host's share of the window, and what it could not show."""

    name: str
    profile: str  # the capability profile it was judged by ("conservative" when unknown)
    sessions: int = 0
    tasks: int = 0
    decisions: int = 0
    events: dict[str, int] = field(default_factory=dict)  # recorded, by event type
    delivers: frozenset[str] = frozenset()  # declared by its profile, or recorded
    # Instrumented modes this host cannot feed -> what is missing.
    blind: dict[FailureMode, tuple[str, ...]] = field(default_factory=dict)

    @property
    def opens_tasks(self) -> bool:
        return TASK in self.delivers

    def can_observe(self, mode: FailureMode) -> bool:
        return mode not in self.blind

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.name,
            "profile": self.profile,
            "sessions": self.sessions,
            # None, not 0: a host that sends no prompt event has no tasks to count.
            "tasks": self.tasks if self.opens_tasks else None,
            "decisions": self.decisions,
            "events": dict(sorted(self.events.items())),
            "not_instrumented": [
                {"mode": str(mode), "missing": [NEED_TEXT[need] for need in missing]}
                for mode, missing in self.blind.items()
            ],
        }


@dataclass(slots=True)
class ModeObservation:
    spec: ModeSpec
    occurrences: int = 0
    tasks: int = 0
    distinct_subjects: int = 0
    last_seen: float = 0.0
    examples: list[dict] = field(default_factory=list)
    # Occurrences outside any task: counted, never as tasks (H7).
    untasked: int = 0
    # The tasks on hosts that could have shown this mode: the rate's denominator.
    denominator: int = 0
    by_host: dict[str, int] = field(default_factory=dict)  # occurrences per host

    @property
    def rate(self) -> float | None:
        return self.tasks / self.denominator if self.tasks and self.denominator else None


@dataclass(slots=True)
class Census:
    root: str
    days: int
    activity: dict[str, Any]
    observed: list[ModeObservation]  # instrumented and seen, most frequent first
    silent: list[ModeSpec]  # instrumented and never seen
    uninstrumented: list[ModeSpec]  # no detector — reported as such, never as zero
    unknown: list[str] = field(default_factory=list)  # recorded but not in the taxonomy
    # Beyond SPEC §3: AgentGuard's own extension, reported in its own section so it can
    # never be read as a SPEC bullet (census/taxonomy.py EXTENDED_TAXONOMY).
    extended_observed: list[ModeObservation] = field(default_factory=list)
    extended_silent: list[ModeSpec] = field(default_factory=list)
    extended_uninstrumented: list[ModeSpec] = field(default_factory=list)
    # H7: who was active, and the detectors none of them could feed.
    hosts: list[HostActivity] = field(default_factory=list)
    unobservable: list[ModeSpec] = field(default_factory=list)
    extended_unobservable: list[ModeSpec] = field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return bool(self.activity.get("tasks") or self.activity.get("decisions"))

    def blind_hosts(self, mode: FailureMode) -> list[HostActivity]:
        return [host for host in self.hosts if not host.can_observe(mode)]

    def seeing_hosts(self, mode: FailureMode) -> list[HostActivity]:
        return [host for host in self.hosts if host.can_observe(mode)]

    def _blind_dict(self, spec: ModeSpec) -> dict[str, list[str]]:
        return {
            host.name: [NEED_TEXT[need] for need in host.blind[spec.mode]]
            for host in self.blind_hosts(spec.mode)
        }

    def _observed_dict(self, o: ModeObservation, text_key: str) -> dict[str, Any]:
        return {
            "mode": str(o.spec.mode),
            text_key: o.spec.spec_text,
            "detector": o.spec.detector,
            "proves": o.spec.proves,
            "occurrences": o.occurrences,
            "tasks": o.tasks,
            "untasked_occurrences": o.untasked,
            "rate_denominator_tasks": o.denominator,
            "by_host": o.by_host,
            "distinct_subjects": o.distinct_subjects,
            "last_seen": o.last_seen,
            "examples": o.examples,
        }

    def _silent_dict(self, spec: ModeSpec, text_key: str) -> dict[str, Any]:
        entry: dict[str, Any] = {"mode": str(spec.mode), text_key: spec.spec_text, "detector": spec.detector}
        if self.hosts:
            entry["observable_on"] = [host.name for host in self.seeing_hosts(spec.mode)]
            entry["not_instrumented_on"] = self._blind_dict(spec)
        return entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "window_days": self.days,
            "generated_at": time.time(),
            "activity": self.activity,
            "hosts": [host.to_dict() for host in self.hosts],
            "observed": [self._observed_dict(o, "spec_text") for o in self.observed],
            "instrumented_never_observed": [self._silent_dict(s, "spec_text") for s in self.silent],
            "not_instrumented_on_active_hosts": [
                {"mode": str(s.mode), "spec_text": s.spec_text, "hosts": self._blind_dict(s)}
                for s in self.unobservable
            ],
            "not_instrumented": [
                {
                    "mode": str(s.mode),
                    "spec_text": s.spec_text,
                    "because": NOT_INSTRUMENTED_BECAUSE.get(s.mode, ""),
                }
                for s in self.uninstrumented
            ],
            "unrecognised_modes": self.unknown,
            "beyond_spec_3": {
                "note": "AgentGuard's own extension; not part of SPEC §3",
                "observed": [self._observed_dict(o, "text") for o in self.extended_observed],
                "instrumented_never_observed": [self._silent_dict(s, "text") for s in self.extended_silent],
                "not_instrumented_on_active_hosts": [
                    {"mode": str(s.mode), "text": s.spec_text, "hosts": self._blind_dict(s)}
                    for s in self.extended_unobservable
                ],
                "not_instrumented": [
                    {
                        "mode": str(s.mode),
                        "text": s.spec_text,
                        "because": NOT_INSTRUMENTED_BECAUSE.get(s.mode, ""),
                    }
                    for s in self.extended_uninstrumented
                ],
            },
        }


def collect(store: ProjectStore, days: int = 14, examples: int = 2) -> Census:
    """Build the census from one project's recorded findings."""
    since = time.time() - days * 86400
    counts = {row["failure_mode"]: row for row in store.failure_mode_counts(since)}
    by_host: dict[str, dict[str, int]] = {}
    for row in store.failure_mode_counts_by_host(since):
        name = _host_name(row["agent"])
        per_mode = by_host.setdefault(row["failure_mode"], {})
        per_mode[name] = per_mode.get(name, 0) + int(row["occurrences"])
    activity = store.activity(since)
    hosts = _hosts(store.activity_by_host(since))
    has_data = bool(activity.get("tasks") or activity.get("decisions"))

    def observe(specs: tuple[ModeSpec, ...]):
        return _observe(specs, counts, by_host, store, since, examples, hosts, has_data, activity)

    observed, silent, unobservable, uninstrumented = observe(TAXONOMY)
    ext_observed, ext_silent, ext_unobservable, ext_uninstrumented = observe(EXTENDED_TAXONOMY)

    # Recorded modes with no taxonomy entry — a row written by a newer version, or a
    # detector added without one. Reported rather than dropped: quietly discarding data
    # you do not recognise is how a census starts lying.
    known = {str(spec.mode) for spec in ALL_MODES}
    unknown = sorted(name for name in counts if name not in known)

    return Census(
        root=store.identity.root,
        days=days,
        activity=activity,
        observed=observed,
        silent=silent,
        uninstrumented=uninstrumented,
        unknown=unknown,
        extended_observed=ext_observed,
        extended_silent=ext_silent,
        extended_uninstrumented=ext_uninstrumented,
        hosts=hosts,
        unobservable=unobservable,
        extended_unobservable=ext_unobservable,
    )


def _host_name(agent: str | None) -> str:
    return (agent or "").strip() or "unknown"


def _hosts(raw: dict[str, dict[str, Any]]) -> list[HostActivity]:
    """Every host active in the window, with the instrumented modes it cannot feed."""
    merged: dict[str, dict[str, Any]] = {}
    for agent, data in raw.items():
        into = merged.setdefault(_host_name(agent), {"sessions": 0, "tasks": 0, "decisions": 0, "events": {}})
        for key in ("sessions", "tasks", "decisions"):
            into[key] += int(data.get(key) or 0)
        for event, count in (data.get("events") or {}).items():
            into["events"][event] = into["events"].get(event, 0) + int(count)

    hosts: list[HostActivity] = []
    for name, data in sorted(merged.items()):
        if not (data["sessions"] or data["tasks"] or data["decisions"] or data["events"]):
            continue
        caps = capabilities_for(None if name == "unknown" else name)
        delivers = set(data["events"]) | declared_events(caps)
        if str(EventType.POST_TOOL_FAILURE) in delivers:
            delivers.add(POST_TOOL)  # the engine observes a failed tool through the same path
        if str(EventType.USER_PROMPT) in delivers or data["tasks"]:
            delivers.add(TASK)
        host = HostActivity(
            name=name,
            profile=caps.name,
            sessions=data["sessions"],
            tasks=data["tasks"],
            decisions=data["decisions"],
            events=data["events"],
            delivers=frozenset(delivers),
        )
        for spec in ALL_MODES:
            if spec.instrumented:
                missing = tuple(need for need in needs(spec.mode) if need not in delivers)
                if missing:
                    host.blind[spec.mode] = missing
        hosts.append(host)
    return hosts


def _observe(
    specs: tuple[ModeSpec, ...],
    counts: dict[str, Any],
    by_host: dict[str, dict[str, int]],
    store: ProjectStore,
    since: float,
    examples: int,
    hosts: list[HostActivity],
    has_data: bool,
    activity: dict[str, Any],
) -> tuple[list[ModeObservation], list[ModeSpec], list[ModeSpec], list[ModeSpec]]:
    """Split one taxonomy into observed / instrumented-but-silent / not observable on any
    active host / uninstrumented."""
    observed: list[ModeObservation] = []
    silent: list[ModeSpec] = []
    unobservable: list[ModeSpec] = []
    uninstrumented: list[ModeSpec] = []

    for spec in specs:
        if not spec.instrumented:
            uninstrumented.append(spec)
            continue
        seeing = [host for host in hosts if host.can_observe(spec.mode)]
        row = counts.get(str(spec.mode))
        if row is None:
            # Silence is a measurement only where some active host could have spoken.
            if has_data and hosts and not seeing:
                unobservable.append(spec)
            else:
                silent.append(spec)
            continue
        # An observation is evidence whoever sent it; its rate's denominator is the
        # tasks on hosts that could have shown it.
        denominator = sum(host.tasks for host in seeing) if hosts else int(activity.get("tasks") or 0)
        observed.append(
            ModeObservation(
                spec=spec,
                occurrences=int(row["occurrences"]),
                tasks=int(row["tasks"]),
                distinct_subjects=int(row["distinct_subjects"]),
                last_seen=float(row["last_seen"] or 0.0),
                examples=(
                    store.failure_mode_examples(str(spec.mode), since, examples)
                    if examples
                    else []
                ),
                untasked=int(row.get("untasked") or 0),
                denominator=denominator,
                by_host=dict(sorted(by_host.get(str(spec.mode), {}).items())),
            )
        )

    # Ranked by breadth first: a mode that touched nine separate tasks matters more than
    # one that fired thirty times inside a single stubborn afternoon.
    observed.sort(key=lambda o: (-o.tasks, -o.occurrences, str(o.spec.mode)))
    return observed, silent, unobservable, uninstrumented


def _tasks_cell(o: ModeObservation) -> str:
    """A task count, or "—" when every occurrence came from outside any task."""
    return "—" if not o.tasks and o.untasked else str(o.tasks)


def _rate_cell(o: ModeObservation) -> str:
    rate = o.rate
    return f"{rate * 100:.1f}%" if rate is not None else "—"


def _render_hosts(census: Census, add: Any) -> None:
    """Per-host sessions and tasks, and what each host could not show (H7)."""
    if not census.hosts:
        return
    add("hosts")
    if sum(host.sessions for host in census.hosts) != int(census.activity.get("sessions") or 0):
        add("  (a session with no session-start or prompt event is counted here from its tool events)")
    width = max(len(host.name) for host in census.hosts) + 2
    for host in census.hosts:
        tasks = (
            f"{host.tasks} task(s)"
            if host.opens_tasks
            else "tasks: — (it sends no prompt event, so it opens none)"
        )
        profile = "" if host.profile == host.name else f"  [judged as {host.profile}]"
        counts = f"{host.sessions} session(s) · {tasks} · {host.decisions} decision(s)"
        add(f"  {host.name:<{width}}{counts}{profile}")
        groups: dict[tuple[str, ...], list[ModeSpec]] = {}
        for spec in ALL_MODES:
            if spec.mode in host.blind:
                groups.setdefault(host.blind[spec.mode], []).append(spec)
        for missing, specs in groups.items():
            why = "; ".join(NEED_TEXT[need] for need in missing)
            add(f"      not instrumented on {host.name} ({why}):")
            for spec in specs:
                add(f"        · {spec.spec_text}")
    add("")


def _observable_note(census: Census, spec: ModeSpec) -> str:
    """" (on claude-code only)" when some active host could not have shown the mode."""
    if not census.hosts or not census.blind_hosts(spec.mode):
        return ""
    return f" (on {', '.join(host.name for host in census.seeing_hosts(spec.mode))} only)"


def render(census: Census) -> str:
    """The published table (Phase 7's exit criterion)."""
    activity = census.activity
    lines: list[str] = []
    add = lines.append

    add("AgentGuard — failure-mode census (SPEC §3)")
    add(census.root)
    add(f"last {census.days} days")
    add("")

    sessions = int(activity.get("sessions") or 0)
    observe_sessions = int(activity.get("observe_only_sessions") or 0)
    tasks = int(activity.get("tasks") or 0)
    add(
        f"  {sessions} session(s) · {tasks} task(s) · "
        f"{int(activity.get('decisions') or 0)} decision(s)"
    )
    add(f"  {observe_sessions} of {sessions} session(s) ran observe-only")
    if sessions and observe_sessions != sessions:
        add(
            "  ! mixed modes. Findings from guarded sessions describe an agent that was "
            "being\n    steered, which is a different quantity from the unguarded baseline."
        )
    if census.observed:
        add(
            f"  AgentGuard would have spoken {int(activity.get('would_have_spoken') or 0)} "
            "time(s) in observe-only sessions"
        )
    add("")

    if not census.has_data:
        add("  no recorded activity in this window — nothing to count")
        add("")

    _render_hosts(census, add)

    add("observed")
    if census.observed:
        # Wide enough for the longest instrumented mode, so no row is ever truncated to
        # something that reads as a different failure than the one being reported.
        width = max(len(o.spec.spec_text) for o in census.observed) + 2
        add(f"  {'#':<3}{'§3 failure mode':<{width}}{'tasks':>7}{'occurrences':>13}{'  rate':>8}")
        for rank, o in enumerate(census.observed, start=1):
            add(
                f"  {rank:<3}{o.spec.spec_text:<{width}}{_tasks_cell(o):>7}{o.occurrences:>13}"
                f"{_rate_cell(o):>8}"
            )
        add("")
        _render_denominators(census.observed, tasks, add)
        for o in census.observed:
            for example in o.examples[:1]:
                add(f"  {o.spec.spec_text}: {str(example.get('summary'))[:88]}")
    else:
        add("  nothing — no instrumented failure mode was observed in this window")
    add("")

    # "Never observed" claims we looked. With nothing recorded we did not, and saying
    # otherwise is the same overstatement as printing a zero for an uninstrumented mode.
    add(
        "instrumented, never observed"
        if census.has_data
        else "instrumented — but there was nothing to observe"
    )
    if census.silent:
        for spec in census.silent:
            add(f"  · {spec.spec_text}{_observable_note(census, spec)}")
    else:
        add("  —")
    add("")

    if census.unobservable:
        add("instrumented, but no active host can feed the detector — no number")
        for spec in census.unobservable:
            add(f"  · {spec.spec_text}")
            for host in census.blind_hosts(spec.mode):
                add(f"      {host.name}: {'; '.join(NEED_TEXT[need] for need in host.blind[spec.mode])}")
        add("")

    if census.unknown:
        add("recorded but not in the SPEC §3 taxonomy")
        for name in census.unknown:
            add(f"  ? {name}")
        add("")

    add("not instrumented — no detector, so no number")
    for spec in census.uninstrumented:
        add(f"  · {spec.spec_text}")
        because = NOT_INSTRUMENTED_BECAUSE.get(spec.mode, "")
        if because:
            add(f"      {because}")
    add("")
    add(
        "These modes are absent from the table above rather than reported as zero. A zero\n"
        "would say 'this does not happen'; the truth is 'nothing here looks for it'."
    )
    add("")
    _render_extension(census, add, tasks)
    return "\n".join(lines)


def _render_denominators(observed: list[ModeObservation], tasks: int, add: Any) -> None:
    """Say so where a rate is not over every task, or a count is not of tasks (H7)."""
    for o in observed:
        if o.denominator != tasks and o.rate is not None:
            add(f"  {o.spec.spec_text}: rate over the {o.denominator} task(s) on hosts that can show it")
    untasked = [o for o in observed if o.untasked]
    if untasked:
        add(
            "  occurrences outside any task (a host without a prompt event, or before the first "
            "prompt)\n  are counted as occurrences, never as tasks: "
            + ", ".join(f"{o.spec.spec_text} {o.untasked}" for o in untasked)
        )
    add("")


def _render_extension(census: Census, add: Any, tasks: int) -> None:
    """Beyond SPEC §3 — AgentGuard's own extension, in its own section, never mixed in."""
    add("beyond SPEC §3 — AgentGuard's own extension, not part of the SPEC")
    if census.extended_observed:
        width = max(len(o.spec.spec_text) for o in census.extended_observed) + 2
        add(f"  {'#':<3}{'failure mode':<{width}}{'tasks':>7}{'occurrences':>13}{'  rate':>8}")
        for rank, o in enumerate(census.extended_observed, start=1):
            add(
                f"  {rank:<3}{o.spec.spec_text:<{width}}{_tasks_cell(o):>7}{o.occurrences:>13}"
                f"{_rate_cell(o):>8}"
            )
    # Same rule as the §3 table: "never observed" claims we looked, which is only true
    # when there was recorded activity to look at.
    silent = (
        "instrumented, never observed"
        if census.has_data
        else "instrumented — but there was nothing to observe"
    )
    for spec in census.extended_silent:
        add(f"  · {spec.spec_text} — {silent}{_observable_note(census, spec)}")
    for spec in census.extended_unobservable:
        blind = "; ".join(
            f"{host.name}: {', '.join(NEED_TEXT[need] for need in host.blind[spec.mode])}"
            for host in census.blind_hosts(spec.mode)
        )
        add(f"  · {spec.spec_text} — not instrumented on the active hosts ({blind})")
    for spec in census.extended_uninstrumented:
        add(f"  · {spec.spec_text} — not instrumented")
        because = NOT_INSTRUMENTED_BECAUSE.get(spec.mode, "")
        if because:
            add(f"      {because}")


def render_detectors() -> str:
    """What each detector actually proves — the `--verbose` half of the report.

    Separated because it is the part that stops a number being over-read. "insufficient
    tests: 40%" means something quite specific and considerably narrower than the SPEC
    bullet it is filed under.
    """
    lines = ["what each observation actually establishes", ""]
    for spec in ALL_MODES:
        if not spec.instrumented:
            continue
        lines.append(f"  {spec.spec_text}")
        lines.append(f"      detector: {spec.detector}")
        lines.append(f"      proves:   {spec.proves}")
        needed = ", ".join(_NEED_NOUNS[need] for need in needs(spec.mode))
        lines.append(f"      needs:    {needed} from the host")
        lines.append("")
    return "\n".join(lines)


_NEED_NOUNS = {
    TASK: "a prompt event",
    PRE_TOOL: "a pre-tool event",
    POST_TOOL: "a post-tool event",
    STOP: "a stop event",
}
