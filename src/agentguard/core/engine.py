"""The Guard: the one place an AgentEvent becomes a Decision.

This is "AgentGuard Core" from SPEC §28 — the actual product. Everything else (hooks,
MCP, CLI, adapters) is an integration surface around this object.

Fail-open is structural
-----------------------
SPEC §8/§39 require that AgentGuard be invisible in normal operation. The corollary is
that a *broken* AgentGuard must also be invisible. Every path through `handle()` is
wrapped: any exception, any timeout, any missing index yields ALLOW. There is no failure
mode in which AgentGuard stops a developer from working.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

from agentguard import complexity, intent, planning, validate
from agentguard.challenge.ledger import ChallengeLedger
from agentguard.core import observe, rehydrate, shellchanges
from agentguard.core.config import Settings
from agentguard.core.enums import DecisionAction, EscalationLevel, EventType
from agentguard.core.events import SHELL_TOOLS, AgentEvent
from agentguard.core.metrics import (
    M_DECISION,
    M_FALSE_COMPLETION_BLOCKED,
    M_HOOK_LATENCY,
    METRICS,
    Timer,
)
from agentguard.core.models import Decision
from agentguard.core.store import ProjectStore
from agentguard.core.taskstate import TaskState
from agentguard.daemon import degraded
from agentguard.intent.models import TaskSpec
from agentguard.repo import symbols_ts
from agentguard.repo.gitinfo import repository_root
from agentguard.repo.index import IndexDelta, RepoIndex
from agentguard.validate import checks
from agentguard.verify import completion_gate, runners, static

log = logging.getLogger(__name__)

# Events that act on the workspace, and so need a task to be judged against (H2).
_TOOL_EVENTS = frozenset({EventType.PRE_TOOL_USE, EventType.POST_TOOL_USE, EventType.POST_TOOL_FAILURE})

# How often a session start or a prompt may re-scan the tree for changes made outside
# the agent (R4). Off the per-tool path; about 100 ms on a large repository.
BOUNDARY_REFRESH_INTERVAL = 30.0
# How often a shell command may sweep the tree. A sweep it skips is not lost: the change
# waits, attributed to the command, for whichever sweep comes next (G5).
SHELL_SWEEP_INTERVAL = 2.0
# Stop's sweep, when no shell change is waiting for one.
STOP_SWEEP_INTERVAL = 5.0

# The tool arguments that name the file an edit changes. The workspace rebases them, and
# a rebuilt task reads them back from the stored events (R14).
PATH_ARGUMENTS = ("file_path", "notebook_path")

# Live tasks kept in memory per workspace, evicted least recently active first — never a
# session's current task (R14). Past the hard cap, an idle session's current task goes
# too; it is rebuilt from the store when its session comes back.
MAX_LIVE_TASKS = 64
HARD_MAX_LIVE_TASKS = 512
# Task ids the store does not know (memory-only ids, closed tasks), remembered so a miss
# does not query the store on every event.
MAX_UNKNOWN_TASKS = 256

# Reported once per rebuild through the R9 registry, for as long as it matters.
TASK_REBUILT = "task_rebuilt"
TASK_REBUILT_REASON = (
    "a task's state was rebuilt from the store after the daemon restarted or set it aside; "
    "its edits and test runs are back, but changes made through shell commands, the tests "
    "that covered a deleted file and the gate's block count could not be recovered."
)
TASK_REBUILT_TTL_S = 900.0


def memory_task_id() -> str:
    """A task id minted without the store, for when it cannot record one (H2)."""
    return f"mem-{uuid.uuid4().hex}"


class Workspace:
    """Per-repository state: the decision store and the repository index."""

    def __init__(self, root: Path, settings: Settings) -> None:
        self.root = root
        self.settings = settings
        # A project-scoped handle on the shared database. It has no way to reach another
        # project's rows (Memory plan §4).
        self.store = ProjectStore.for_workspace(root, settings)
        # Built in the background: a large monorepo takes seconds, and no developer
        # should wait on it. Until it is ready every query answers "unknown", which
        # resolves to ALLOW (SPEC §39).
        self.index = RepoIndex(root, settings.index)
        self.index.build_async()
        # The TaskSpec for the prompt currently being worked on.
        self.current_spec: TaskSpec | None = None
        self.ledger = ChallengeLedger(self.store, settings.challenge)
        # Live task state: files touched, tests observed, gate budget. In memory, least
        # recently active first; a task that is not here but is in the store is rebuilt
        # from it (R14), and only a task nobody recorded is judged without history.
        self._tasks: OrderedDict[str, TaskState] = OrderedDict()
        self._unknown_tasks: OrderedDict[str, None] = OrderedDict()
        self.tasks_rebuilt = 0
        # Hook requests for one repository may arrive concurrently once the daemon
        # dispatches them away from FastAPI's event loop. State transitions must remain
        # ordered per workspace, while unrelated repositories can still proceed in
        # parallel.
        self.event_lock = threading.RLock()
        # A daemon can serve more than one Claude session in the same repository. Keep
        # task ownership keyed by session so a tool event from session A can never inherit
        # the most recently-created task from session B.
        self._session_tasks: dict[str, str] = {}
        self._session_task_ids: dict[str, list[str]] = {}
        self._task_sessions: dict[str, str] = {}
        # Sessions whose developer said not to run tests (G6). The instruction holds for
        # the rest of the session — "don't run the tests" then "now fix the other one"
        # is one instruction — until a later prompt asks for tests.
        self.session_waivers: set[str] = set()
        # Shell commands' changes, each holding its place on its task's timeline until a
        # sweep of the tree attributes them (G5).
        self.shell = shellchanges.ShellChanges()

    def begin_task(self, task_id: str, spec: TaskSpec, session_id: str = "") -> TaskState | None:
        if not task_id:
            return None
        state = TaskState(task_id=task_id, spec=spec, session_id=session_id)
        self._adopt(state, current=True)
        return state

    def _adopt(self, state: TaskState, current: bool) -> None:
        """Make ``state`` live (most recently active), and its session's current task."""
        task_id, session_id = state.task_id, state.session_id
        self._tasks[task_id] = state
        self._tasks.move_to_end(task_id)
        self._unknown_tasks.pop(task_id, None)
        if session_id:
            if current:
                self._session_tasks[session_id] = task_id
            owned = self._session_task_ids.setdefault(session_id, [])
            if task_id not in owned:
                owned.append(task_id)
            self._task_sessions[task_id] = session_id
        self._evict()

    def _evict(self) -> None:
        """Keep the live window bounded: least recently active first (R14).

        It used to keep eight tasks in insertion order, so a ninth concurrent session —
        or one session sending eight prompts — dropped another session's open task, and
        Stop after its failing tests returned allow (D3). A session's current task is
        never evicted below the hard cap; an evicted one is rebuilt from the store.
        """
        if len(self._tasks) <= MAX_LIVE_TASKS:
            return
        current = set(self._session_tasks.values())
        for task_id in list(self._tasks):
            if len(self._tasks) <= MAX_LIVE_TASKS:
                return
            if task_id not in current:
                self._forget_task(task_id)
        for task_id in list(self._tasks):
            if len(self._tasks) <= HARD_MAX_LIVE_TASKS:
                return
            self._forget_task(task_id, keep_current=True)

    def ensure_task(self, session_id: str) -> TaskState | None:
        """The session's task, created on demand when no prompt ever opened one (H2).

        Hosts without a prompt event — or a prompt whose task could not be stored — left
        no task at all, so every challenge became "no task context" and scope, test
        recording and the Completion Gate all switched off. An implicit task has an empty
        scope and no planning depth (so proportionality cannot fire on work nobody
        described); it is persisted when the store works (prompt "", tagged implicit for
        the census) and lives in memory otherwise.
        """
        if not session_id:
            return None
        current = self._session_tasks.get(session_id)
        if current is not None:
            live = self.task_state(current, session_id)
            if live is not None:
                return live
        spec = TaskSpec.implicit()
        task_id = self.store.create_task(
            session_id, "", spec={**spec.model_dump(mode="json"), "implicit": True}, depth="implicit"
        )
        return self.begin_task(task_id or memory_task_id(), spec, session_id)

    def live_task(self, task_id: str) -> TaskState | None:
        """The in-memory state of ``task_id``, without any ownership check."""
        return self._tasks.get(task_id)

    def _forget_task(self, task_id: str, keep_current: bool = False) -> None:
        """Drop a task's live state. With ``keep_current`` its session still points at
        it, so the session's next event rebuilds it from the store (R14)."""
        self._tasks.pop(task_id, None)
        session_id = self._task_sessions.pop(task_id, None)
        if session_id is None:
            return
        task_ids = self._session_task_ids.get(session_id, [])
        self._session_task_ids[session_id] = [item for item in task_ids if item != task_id]
        if self._session_tasks.get(session_id) == task_id and not keep_current:
            remaining = self._session_task_ids[session_id]
            if remaining:
                self._session_tasks[session_id] = remaining[-1]
            else:
                self._session_tasks.pop(session_id, None)
                self._session_task_ids.pop(session_id, None)

    def _rebuild(self, task_id: str, session_id: str = "") -> TaskState | None:
        """Rebuild a task the store knows but memory does not (R14), or None.

        After a daemon restart, or once the live window set the task aside, its edits
        and test runs come back from the store: Stop after failing tests blocks again.
        Only an open task, and only for the session that owns it.
        """
        if task_id in self._unknown_tasks:
            return None
        record = self.store.task_record(task_id)
        if not record or record.get("status") != "open":
            self._unknown_tasks[task_id] = None
            while len(self._unknown_tasks) > MAX_UNKNOWN_TASKS:
                self._unknown_tasks.popitem(last=False)
            return None
        owner = str(record.get("session_id") or "")
        if session_id and owner and owner != session_id:
            return None  # another session's task: an attribution claim, rejected
        try:
            state, replayed = rehydrate.rebuild(self.store, self.index, record, PATH_ARGUMENTS)
        except Exception:
            log.exception("agentguard: could not rebuild task state from the store")
            return None
        held = self._session_tasks.get(owner) if owner else None
        current = bool(owner) and held in (None, task_id) and self.store.current_task_id(owner) == task_id
        self._adopt(state, current=current)
        self.tasks_rebuilt += 1
        log.warning(
            "agentguard: rebuilt task state from the store (%d change(s), %d run(s))",
            replayed["changes"],
            replayed["runs"],
        )
        degraded.report(
            TASK_REBUILT,
            TASK_REBUILT_REASON,
            ttl_s=TASK_REBUILT_TTL_S,
            detail={"tasks": self.tasks_rebuilt, **replayed},
        )
        return state

    def resolve_task_id(self, session_id: str) -> str | None:
        """The task a tool event belongs to. In-memory first; the store is the fallback
        after a daemon restart."""
        if session_id:
            task_id = self._session_tasks.get(session_id)
            if task_id is not None:
                return task_id
        return self.store.current_task_id(session_id) if session_id else None

    def task_state(self, task_id: str | None, session_id: str = "") -> TaskState | None:
        """Return live state for an explicit task, or resolve one within a session.

        Explicit ids are never treated as hints: an unknown id returns ``None`` instead
        of silently selecting the session's current task. Supplying ``session_id`` also
        enforces ownership, which is what event handlers use to isolate concurrent
        host sessions. Diagnostics with an already-validated id may omit the session.
        """
        if task_id:
            state = self._tasks.get(task_id)
            # An explicit id is an attribution claim, not a hint. Never fall back to
            # the session's current task when the claim is stale or unknown: doing so
            # can attach a host event to unrelated in-memory state. A task the store
            # knows is rebuilt from it instead (R14).
            if state is None:
                state = self._rebuild(task_id, session_id)
            if state is None:
                return None
            owner = self._task_sessions.get(task_id) or state.session_id
            if session_id and owner and owner != session_id:
                return None
            self._tasks.move_to_end(task_id)  # activity: the window evicts the idle first
            return state
        # Tool events can arrive before the store has attributed them to a task. Resolve
        # only within the event's session; an unscoped fallback would cross-contaminate
        # concurrent sessions in the same repository.
        resolved = self.resolve_task_id(session_id) if session_id else None
        if resolved:
            return self.task_state(resolved, session_id)
        return None

    def event_task_state(self, event: AgentEvent) -> TaskState | None:
        """Resolve live state while preserving rejected explicit attribution claims."""
        if event._task_id_rejected:
            return None
        return self.task_state(event.task_id, event.session_id)

    def end_session(self, session_id: str) -> None:
        """Drop in-memory state owned by a finished host session."""
        for task_id in self._session_task_ids.pop(session_id, []):
            self._tasks.pop(task_id, None)
            self._task_sessions.pop(task_id, None)
        self._session_tasks.pop(session_id, None)
        self.session_waivers.discard(session_id)
        self.shell.forget_session(session_id)

    def carry_waiver(self, session_id: str, spec: TaskSpec) -> None:
        """Apply, record or end the session's test waiver for a new prompt (G6)."""
        if not session_id:
            return
        if spec.tests_waiver is not None:  # the host decided
            if spec.tests_waiver:
                self.session_waivers.add(session_id)
            else:
                self.session_waivers.discard(session_id)
        elif spec.tests_requested:
            self.session_waivers.discard(session_id)
        elif spec.tests_waived:
            self.session_waivers.add(session_id)
        elif session_id in self.session_waivers:
            spec.session_waiver = True

    def close(self) -> None:
        self.store.close()


class Guard:
    """Routes events to handlers, records everything, never breaks the host."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()
        self._workspaces: dict[str, Workspace] = {}
        self._workspace_roots: dict[str, str] = {}
        self._lock = threading.Lock()
        self._handlers: dict[EventType, Callable[[AgentEvent, Workspace], Decision]] = {
            EventType.SESSION_START: self._on_session_start,
            EventType.USER_PROMPT: self._on_user_prompt,
            EventType.PRE_TOOL_USE: self._on_pre_tool_use,
            EventType.POST_TOOL_USE: self._on_post_tool_use,
            EventType.POST_TOOL_FAILURE: self._on_post_tool_use,
            EventType.STOP: self._on_stop,
            EventType.SUBAGENT_STOP: self._on_subagent_stop,
            EventType.SESSION_END: self._on_session_end,
        }

    # -- workspaces ---------------------------------------------------------------

    def workspace(self, root: str | Path) -> Workspace:
        candidate = Path(root).expanduser().resolve()
        candidate_key = str(candidate)
        with self._lock:
            key = self._workspace_roots.get(candidate_key)
        if key is None:
            key = str(repository_root(candidate))
            with self._lock:
                self._workspace_roots[candidate_key] = key
                self._workspace_roots.setdefault(key, key)
        with self._lock:
            ws = self._workspaces.get(key)
            if ws is None:
                ws = Workspace(Path(key), self.settings)
                self._workspaces[key] = ws
            return ws

    def close(self) -> None:
        with self._lock:
            for ws in self._workspaces.values():
                ws.close()
            self._workspaces.clear()
            self._workspace_roots.clear()

    def _normalize_event_workspace(self, event: AgentEvent) -> None:
        """Use the repository root as the workspace key without losing cwd-relative paths."""
        cwd = Path(event.workspace).expanduser().resolve()
        root = Path(self._workspace_root(cwd))
        if cwd == root:
            event.workspace = str(root)
            return

        # Claude may send a tool path relative to its current cwd. Rebase those paths
        # before the index (which is rooted at the repository top-level) sees them.
        for name in PATH_ARGUMENTS:
            raw = event.arguments.get(name)
            if isinstance(raw, str) and raw and not Path(raw).expanduser().is_absolute():
                event.arguments[name] = str(cwd / raw)
        event.workspace = str(root)

    def _workspace_root(self, root: Path) -> str:
        candidate = str(root)
        with self._lock:
            cached = self._workspace_roots.get(candidate)
        if cached is not None:
            return cached
        resolved = str(repository_root(root))
        with self._lock:
            self._workspace_roots[candidate] = resolved
            self._workspace_roots.setdefault(resolved, resolved)
        return resolved

    # -- entry point --------------------------------------------------------------

    def handle(self, event: AgentEvent) -> Decision:
        """Never raises. Never blocks on failure."""
        ws: Workspace | None = None
        if not self.settings.enabled:
            return Decision.allow()
        # The marker is per-dispatch, not part of the host event contract.  Reset it so
        # reusing an AgentEvent object cannot carry a prior stale-id rejection forward.
        event._task_id_rejected = False

        with Timer() as t:
            try:
                self._normalize_event_workspace(event)
                ws = self.workspace(event.workspace)
                with ws.event_lock:
                    try:
                        # Resolve the task *before* dispatching. Handlers need it: without a task
                        # id the challenge ledger has no way to avoid repeating itself, so it
                        # suppresses everything — which silently disabled every challenge.
                        if event.task_id:
                            # A host-provided id is an explicit attribution claim. If it is
                            # stale, unknown, or owned by another session, leave the event
                            # unscoped rather than silently attaching it to the session's
                            # current task. Reassigning a late event could contaminate the
                            # live task's scope and completion evidence.
                            if ws.task_state(event.task_id, event.session_id) is None:
                                event._task_id_rejected = True
                                event.task_id = None
                        else:
                            event.task_id = ws.resolve_task_id(event.session_id)
                            if (
                                event.task_id is None
                                and event.event in _TOOL_EVENTS
                                and not event.is_read_only
                            ):
                                implicit = ws.ensure_task(event.session_id)
                                event.task_id = implicit.task_id if implicit else None
                        handler = self._handlers.get(event.event)
                        decision = handler(event, ws) if handler else Decision.allow()
                    except Exception:
                        log.exception("agentguard: handler failed for %s; failing open", event.event)
                        decision = Decision.allow()

                    if self.settings.observe_only:
                        decision = observe.silence(decision)

                    # Keep persistence in the same critical section as state mutation. A
                    # SessionEnd arriving concurrently must not close a session and then
                    # lose or reorder the event that preceded it. One transaction (R7):
                    # the event, its decision and the findings are recorded together or
                    # not at all — never an event whose decision was lost — in one commit
                    # instead of two or more. The id is set only when it was persisted.
                    decision.latency_ms = t.elapsed_ms()
                    try:
                        decision.decision_id = (
                            ws.store.record_event_and_decision(event, decision) or decision.decision_id
                        )
                    except Exception:
                        log.exception("agentguard: failed to persist event/decision")
            except Exception:
                log.exception("agentguard: event handling failed for %s; failing open", event.event)
                decision = Decision.allow()
                ws = None

        decision.latency_ms = t.ms
        METRICS.observe(M_HOOK_LATENCY, t.ms, {"event": str(event.event)})
        METRICS.increment(M_DECISION, labels={"action": str(decision.action)})

        return decision

    # -- handlers -----------------------------------------------------------------
    #
    #   session_start -> warm the index
    #   user_prompt   -> Intent Gateway, Complexity Engine, Planning Governor (§9-§13)
    #   pre_tool_use  -> Action Validator: evidence, scope, risk (§14-§18)
    #   post_tool_use -> observe what happened: files touched, tests run (§19)
    #   stop          -> Completion Gate (§19, §20)
    #   session_end   -> close out and run storage maintenance

    def _open_session(self, event: AgentEvent, ws: Workspace) -> None:
        """Record the session, and stamp it with the mode it ran under.

        The census has to be able to say which of its numbers came from an unguarded
        agent. Findings gathered while AgentGuard was challenging and injecting planning
        budgets describe a *steered* agent, and mixing the two silently would make the
        headline rate meaningless.
        """
        if not event.session_id:
            return
        ws.store.open_session(
            event.session_id,
            event.agent,
            str(ws.root),
            meta={"observe_only": self.settings.observe_only},
        )

    def _on_session_start(self, event: AgentEvent, ws: Workspace) -> Decision:
        self._open_session(event, ws)
        # Creating the Workspace already kicked off the build; this hook has a 20s
        # budget, so give it a moment to finish while the session is still starting up.
        ws.index.ready(timeout=5.0)
        self._refresh_at_boundary(ws)
        return Decision.allow()

    @classmethod
    def _refresh_at_boundary(cls, ws: Workspace) -> None:
        """Pick up what changed while no agent was working (R4).

        A long-lived daemon outlives sessions; between them the developer switches
        branches, reverts files, pulls. Its index only refreshed at Stop and after shell
        commands, so it went on vouching for a method reverted underneath it — silent
        where a fresh daemon challenged the same Write (D6 E4). Rate-limited, and only
        once the index exists: a first build is already current.
        """
        cls._sweep(ws, BOUNDARY_REFRESH_INTERVAL)

    @staticmethod
    def _sweep(ws: Workspace, min_interval: float = 0.0) -> IndexDelta:
        """Re-scan the tree, and give what changed to the shell commands that changed it.

        Every sweep goes through here — after a shell command, at Stop, at session and
        prompt boundaries — so a change that a rate-limited sweep missed still reaches the
        task whose command made it, at the place that command took on its timeline,
        whichever sweep sees it first (G5). With no shell change waiting, a sweep only
        refreshes the index. Never builds: an unbuilt index has no baseline to compare.
        """
        index = ws.index
        if not index.is_built:
            return IndexDelta()
        if min_interval and time.monotonic() - index.last_refresh < min_interval:
            return IndexDelta()
        # The coverage a removed file had is only known before the sweep forgets it.
        snapshot = shellchanges.Snapshot.take(index) if ws.shell.pending() else None
        delta = index.refresh_delta(min_interval)
        if snapshot is not None and delta.swept:
            ws.shell.apply(delta, snapshot, index, ws.live_task)
        return delta

    def _on_user_prompt(self, event: AgentEvent, ws: Workspace) -> Decision:
        """Intent Gateway + Complexity Engine + Planning Governor (SPEC §9, §12, §13).

        The planning budget rides back on `additionalContext`, which the developer never
        sees — so this shapes the agent's approach without adding anything to the UI
        (SPEC §39).
        """
        validate.signoff.note_prompt(ws.store, event)  # a sign-off reply grants first (A1b)
        self._open_session(event, ws)
        self._refresh_at_boundary(ws)  # the spec is grounded in the tree as it is now

        prompt = event.prompt_text or ""
        index = ws.index if ws.index.is_built else None
        spec = intent.extract(prompt, index)
        spec.complexity = complexity.assess(spec, index)
        hint = event.host_hints.get("tests_waived")
        if isinstance(hint, bool):
            spec.tests_waiver = hint  # the host decides, either way (H5)
        ws.carry_waiver(event.session_id, spec)
        ws.current_spec = spec

        # The task this prompt follows in the same session, read before the new task
        # replaces it: what it leaves unverified is not forgotten (G8).
        previous = ws.task_state(None, event.session_id) if event.session_id else None
        state = None
        if event.session_id:
            task_id = ws.store.create_task(
                event.session_id,
                prompt,
                spec=spec.model_dump(mode="json"),
                complexity=spec.complexity.score,
                depth=str(spec.complexity.depth),
            )
            # A store that cannot record the task must not switch guarding off (H2): the
            # task lives in memory, under an id minted here.
            task_id = task_id or memory_task_id()
            event.task_id = task_id
            state = ws.begin_task(task_id, spec, event.session_id)

        budget = planning.render(spec, index)
        if previous is not None and state is not None:
            try:
                self._inherit_debt(ws, previous, state)
            except Exception:  # a debt not carried is the old behaviour, never a failure
                log.exception("agentguard: could not carry verification debt to a new task")
        if not budget:
            return Decision.allow(EscalationLevel.REPOSITORY)

        return Decision(
            action=DecisionAction.ALLOW,
            level=EscalationLevel.REPOSITORY,
            additional_context=budget,
        )

    @classmethod
    def _inherit_debt(cls, ws: Workspace, old: TaskState, new: TaskState) -> bool:
        """Carry the verification debt of the session's previous task into ``new`` (G8).

        Every prompt started a fresh TaskState, so "continue" — or a host's Stop
        continuation arriving as a new prompt, or the developer's `approve <CODE>` reply —
        forgot the failing run and the unverified edits, and "All done, tests pass"
        then passed (probe H). Debt is what the completion gate would block on now,
        before any rationing: the latest run failing, changes after the last pass,
        covered changes never tested, unparsable files. Without it the new task starts
        clean; with it, the new task takes over the old one's changes and timeline.

        ``stop_blocks`` travels with the debt. The gate's budget bounds how often it may
        hold a session open over one unresolved problem; a new prompt does not resolve
        it, so it does not refresh the budget either — otherwise a host whose Stop
        continuation arrives as a prompt would be held forever, block after block. A
        genuinely new request therefore gets what remains of the budget: it is never
        held more than the budget allows, and once the budget is spent the developer
        is told the turn ended unverified (G10). Paying the debt (a passing run on the
        current files) means the next prompt starts clean, with a fresh budget.

        Never across sessions: ``old`` is the same session's task. The G6 waiver keeps
        its own logic (`Workspace.carry_waiver`).
        """
        if old.task_id == new.task_id or old.session_id != new.session_id:
            return False
        if ws.shell.pending(old.task_id):
            cls._sweep(ws)  # its shell commands' changes land first (G5)
        if not old.changed_files and not old.verification.outcomes:
            return False
        verdict = completion_gate.evaluate(state=old, index=ws.index, max_blocks=sys.maxsize)
        if not verdict.should_block:
            return False

        new.touched_files |= old.touched_files
        new.deleted_files |= old.deleted_files
        new.created_files |= old.created_files
        for path, seq in old.last_change_seq.items():
            new.last_change_seq[path] = max(seq, new.last_change_seq.get(path, 0))
        new.seq = max(new.seq, old.seq)
        new.verification.outcomes[:0] = old.verification.outcomes
        new.verification.commands_seen[:0] = old.verification.commands_seen
        new.verification.inconclusive[:0] = old.verification.inconclusive
        new.verification.background[:0] = old.verification.background
        for path, parsed in old.parse_baseline.items():
            new.parse_baseline.setdefault(path, parsed)
        for path, tests in old.deleted_coverage.items():
            new.deleted_coverage.setdefault(path, set()).update(tests)
        new.stop_blocks = max(new.stop_blocks, old.stop_blocks)
        new.started_at = min(new.started_at, old.started_at)
        # The inherited files are not this request's drift: a spec that resolved a scope
        # counts them in it, so scope judges only what the new request changes. (An
        # unresolved scope already calls nothing unrelated.)
        if new.spec.expected_scope:
            scope = list(new.spec.expected_scope)
            new.spec.expected_scope = scope + sorted(set(old.touched_files) - set(scope))
        log.info(
            "agentguard: carried verification debt into a new task (%s): %s",
            verdict.result.value,
            next((f.summary for f in verdict.findings if f.subject), ""),
        )
        return True

    def _on_pre_tool_use(self, event: AgentEvent, ws: Workspace) -> Decision:
        """Action Validator (SPEC §18), which runs the Evidence Engine inside it."""
        # SPEC §7/§8: read-only tools never leave Level 0. This short-circuit is what
        # keeps ordinary exploration free.
        if event.is_read_only:
            return Decision.allow()
        if event.tool in SHELL_TOOLS:
            # The command's window opens: a file it changes changes after this (G5).
            ws.shell.note_start(event.session_id, event.tool_use_id)

        try:
            self._record_parse_baseline(event, ws)
        except Exception:  # a missing baseline only means "blame as before"
            log.exception("agentguard: could not record a parse baseline; continuing")
        return validate.validate(
            event=event,
            index=ws.index,
            state=ws.event_task_state(event),
            ledger=ws.ledger,
            task_id=event.task_id,
        )

    @staticmethod
    def _record_parse_baseline(event: AgentEvent, ws: Workspace) -> None:
        """At a file's first change in a task, note whether it parses today (G15).

        Read from the index when its entry is current (no extra parse on the hot path),
        otherwise parsed once. A file that does not exist yet counts as parsing.
        """
        if not event.is_mutating or event.is_delete:
            return
        state = ws.event_task_state(event)
        raw = event.arg("file_path") or event.arg("notebook_path")
        if state is None or not isinstance(raw, str) or not raw:
            return
        path = ws.index.normalize(raw)
        if not path or path in state.parse_baseline:
            return
        record = ws.index.files.get(path) if ws.index.is_built else None
        try:
            stat = (ws.index.root / path).stat()
        except OSError:
            state.parse_baseline[path] = True  # about to be created
            return
        fresh = record is not None and (record.mtime_ns, record.size) == (stat.st_mtime_ns, stat.st_size)
        if fresh and (record.lang == "python" or symbols_ts.available(record.lang)):
            state.parse_baseline[path] = ws.index.is_parsed(path)
            return
        state.parse_baseline[path] = static.parses(ws.index.root, path)

    def _on_post_tool_use(self, event: AgentEvent, ws: Workspace) -> Decision:
        """Observe what actually happened (SPEC §19).

        Two jobs: keep the evidence base honest, and record what the Completion Gate will
        need — which files changed, and what the agent's own test runs reported.
        """
        state = ws.event_task_state(event)

        changed = event.arg("file_path") or event.arg("notebook_path")
        if isinstance(changed, str) and changed:
            path = ws.index.normalize(changed)
            # An absolute path outside the workspace (or a symlink escape) normalizes to
            # the empty sentinel.  Ignore it completely: recording ``""`` as a touched
            # file would pollute scope/completion state even though no file was indexed.
            if not path:
                return Decision.allow()
            # Reads are not writes (H3): only an edit, a write or a deletion that went
            # through changes the file. A Read's post-event (hosts such as Cursor and
            # Gemini send them) or a failed Edit touched nothing, and counting either fed
            # scope and the gate files the agent never changed.
            wrote = event.is_mutating and event.event is not EventType.POST_TOOL_FAILURE
            if state is not None and wrote and event.is_delete:
                # Snapshot the tests that reached the file *before* refresh_path drops it
                # from the index; afterwards nothing would say which tests to run (G5).
                covering = set(runners.affected_tests(ws.index, {path})) if ws.index.is_built else set()
                state.delete(path, covering)
            elif state is not None and wrote:
                if ws.index.is_built and path not in ws.index.files:
                    state.created_files.add(path)  # new to the repository: this task wrote it
                state.touch(path)
            # Re-parse exactly the file that changed (~1ms) rather than re-statting the
            # whole tree (~100ms on a large repo).
            if ws.index.is_built:
                ws.index.refresh_path(path)

        elif event.tool in SHELL_TOOLS:
            command = event.arg("command")
            command = command if isinstance(command, str) else ""
            # What the command changed reaches the task (G5): `sed -i`, a codemod, `rm`,
            # `git mv` name no file, so the sweep below finds the changes, and each lands
            # at the place the command holds on the timeline — before its own test run
            # when that run is its last stage (`sed -i … && pytest`), after it otherwise.
            # A command that only reads or runs tests (A4) changes nothing of the task's.
            writes = (
                state is not None and not event.is_read_only and not checks.read_only_bash(event)
            )
            first = writes and shellchanges.changes_precede_run(command)
            if first:
                ws.shell.reserve(state, event.tool_use_id)
            if command:
                self._record_test_run(event, ws, state, command)
            if writes and not first:
                ws.shell.reserve(state, event.tool_use_id)
            # A shell command can touch anything; fall back to a rate-limited sweep.
            self._sweep(ws, SHELL_SWEEP_INTERVAL)

        return Decision.allow()

    @staticmethod
    def _record_test_run(
        event: AgentEvent, ws: Workspace, state: TaskState | None, command: str
    ) -> None:
        """Read the agent's own test output.

        This is what lets the Completion Gate contradict "all tests pass" without running
        anything itself: the agent produced the evidence. Only a test runner in command
        position counts (G3a), and its exit status leads wherever it is the runner's
        (G1): a failing run on Claude Code arrives as PostToolUseFailure, with the
        status and the output in ``result``.
        """
        if state is None:
            return
        outcome = runners.outcome_from_result(command, event.result)
        if outcome is None:
            return
        # Its place on the task's timeline (G2a): the latest run decides, and a change
        # made after it leaves it stale.
        outcome.seq = state.next_seq()
        if outcome.background or event.arg("run_in_background") is True:
            # Launched, not finished: pending rather than an unreadable run. Stop asks the
            # host whether it is still running (G7).
            outcome.passed, outcome.background = None, True
            outcome.summary = "launched in the background; no result yet"
            state.verification.background.append(outcome)
            return
        state.verification.commands_seen.append(command.strip()[:200])
        if outcome.passed is None:
            state.verification.inconclusive.append(outcome)
        else:
            state.verification.outcomes.append(outcome)
            # The whole outcome, bounded (R14): after a restart the task's runs are rebuilt
            # from this row (`runners.outcome_from_detail`), and the timeline needs their
            # family, key and scope, not just a summary.
            ws.store.finish_verification(
                ws.store.start_verification(state.task_id, outcome.runner),
                "passed" if outcome.passed else "failed",
                runners.outcome_detail(outcome),
            )

    def _on_stop(self, event: AgentEvent, ws: Workspace) -> Decision:
        """Completion Gate (SPEC §19).

        "Done" is a claim like any other. Blocking Stop hands the turn back to the agent
        with the reason, so it keeps working rather than finishing on an unverified claim.
        """
        state = ws.event_task_state(event)
        if state is None or not ws.index.is_built:
            return Decision.allow()

        # Pick up anything changed underneath us — a branch switch, a `git clean`, a
        # colleague's rebase. `refresh_path` only covers files the *agent* touched, so
        # without this the gate can cite a test file that no longer exists. Observed in
        # benchmark run 01, where it recommended a deleted test. A shell command whose
        # sweep was rate-limited is drained first, so its changes are on the task before
        # the gate judges it (G5).
        drain = ws.shell.pending(state.task_id)
        self._sweep(ws, 0.0 if drain else STOP_SWEEP_INTERVAL)

        verdict = completion_gate.evaluate(
            state=state,
            index=ws.index,
            stop_hook_active=bool(event.raw.get("stop_hook_active")),
            max_blocks=self.settings.challenge.max_stop_blocks_per_task,
            message=event.last_assistant_message,
            pending_tasks=event.pending_tasks,
        )
        if not verdict.should_block:
            # Still carries findings: the gate can pass and have seen something worth
            # counting — untested code, most often (SPEC §3, "write insufficient tests").
            # When rationing muted a real objection the turn ends unverified, and the
            # decision says so explicitly, for the developer (G10) — never in observe
            # mode, where nothing is said at all.
            gave_up = verdict.unresolved if not self.settings.observe_only else ""
            return Decision(
                action=DecisionAction.ALLOW,
                level=EscalationLevel.DEEP_VERIFICATION,
                findings=verdict.findings,
                unverified_finish=gave_up or None,
            )

        # Bookkeeping for a block that will actually happen. `observe.silence()` will turn
        # this decision into an ALLOW, and counting a block that the agent never saw would
        # both inflate the metric and spend the gate's per-task budget on nothing. The
        # silence guarantee stays at the choke point; this is about side effects, which
        # genuinely belong to the handler that causes them.
        if not self.settings.observe_only:
            state.stop_blocks += 1
            METRICS.increment(M_FALSE_COMPLETION_BLOCKED, labels={"result": str(verdict.result)})
        return Decision(
            action=DecisionAction.BLOCK,
            level=EscalationLevel.DEEP_VERIFICATION,
            reason=f"AgentGuard — completion gate: {verdict.result.value}\n\n{verdict.reason}",
            findings=verdict.findings,
        )

    def _on_subagent_stop(self, event: AgentEvent, ws: Workspace) -> Decision:
        """A subagent finishing is not the task finishing (G9).

        The gate judges the *task*: its edits, its test runs. A subagent shares the
        session — on Codex, the very session id — so running the gate here told an
        Explore subagent to run the parent's tests, and spent the parent's block budget
        on it (probe F). The verdict is still computed, for the census, and returned on
        an ALLOW: it never blocks and never touches ``stop_blocks``.
        """
        state = ws.event_task_state(event)
        if state is None or not ws.index.is_built:
            return Decision.allow()
        verdict = completion_gate.evaluate(
            state=state,
            index=ws.index,
            max_blocks=self.settings.challenge.max_stop_blocks_per_task,
            message=event.last_assistant_message,
            pending_tasks=event.pending_tasks,
        )
        return Decision(
            action=DecisionAction.ALLOW,
            level=EscalationLevel.DEEP_VERIFICATION,
            findings=verdict.findings,
        )

    def _on_session_end(self, event: AgentEvent, ws: Workspace) -> Decision:
        ws.store.close_session(event.session_id)
        ws.end_session(event.session_id)
        # The one moment maintenance is safe to run: the agent has stopped, so pruning
        # and checkpointing cost nobody anything (Memory plan §7). Rate-limited inside,
        # and it can never raise.
        ws.store.db.maintain()
        return Decision.allow()
