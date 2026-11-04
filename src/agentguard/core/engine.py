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
import threading
import uuid
from collections.abc import Callable
from pathlib import Path

from agentguard import complexity, intent, planning, validate
from agentguard.challenge.ledger import ChallengeLedger
from agentguard.core import observe
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
from agentguard.intent.models import TaskSpec
from agentguard.repo import symbols_ts
from agentguard.repo.gitinfo import repository_root
from agentguard.repo.index import RepoIndex
from agentguard.verify import completion_gate, runners, static

log = logging.getLogger(__name__)

# Events that act on the workspace, and so need a task to be judged against (H2).
_TOOL_EVENTS = frozenset({EventType.PRE_TOOL_USE, EventType.POST_TOOL_USE, EventType.POST_TOOL_FAILURE})


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
        # Live task state: files touched, tests observed, gate budget. In memory only —
        # a lost task means the next action is judged without history, which is ALLOW.
        self._tasks: dict[str, TaskState] = {}
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

    def begin_task(self, task_id: str, spec: TaskSpec, session_id: str = "") -> TaskState | None:
        if not task_id:
            return None
        state = TaskState(task_id=task_id, spec=spec, session_id=session_id)
        self._tasks[task_id] = state
        if session_id:
            self._session_tasks[session_id] = task_id
            self._session_task_ids.setdefault(session_id, []).append(task_id)
            self._task_sessions[task_id] = session_id
        # Keep a small in-memory window for late-arriving events without allowing task
        # state to grow forever in a long-lived daemon.
        if len(self._tasks) > 8:
            retained = {
                task_id
                for task_ids in self._session_task_ids.values()
                for task_id in task_ids
            }
            for stale in list(self._tasks):
                if len(self._tasks) <= 8:
                    break
                if stale not in retained:
                    self._forget_task(stale)
            # More than eight concurrent sessions is unusual, but the daemon must stay
            # bounded even then. Dropping the oldest in-memory state is fail-open; the
            # persistent task id remains available for attribution after a restart.
            for stale in list(self._tasks):
                if len(self._tasks) <= 8:
                    break
                self._forget_task(stale)
        return state

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
        if current is not None and current in self._tasks:
            return self._tasks[current]
        spec = TaskSpec.implicit()
        task_id = self.store.create_task(
            session_id, "", spec={**spec.model_dump(mode="json"), "implicit": True}, depth="implicit"
        )
        return self.begin_task(task_id or memory_task_id(), spec, session_id)

    def _forget_task(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        session_id = self._task_sessions.pop(task_id, None)
        if session_id is None:
            return
        task_ids = self._session_task_ids.get(session_id, [])
        self._session_task_ids[session_id] = [item for item in task_ids if item != task_id]
        if self._session_tasks.get(session_id) == task_id:
            remaining = self._session_task_ids[session_id]
            if remaining:
                self._session_tasks[session_id] = remaining[-1]
            else:
                self._session_tasks.pop(session_id, None)
                self._session_task_ids.pop(session_id, None)

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
            # can attach a host event to unrelated in-memory state.
            if state is None:
                return None
            owner = self._task_sessions.get(task_id) or state.session_id
            if session_id and owner and owner != session_id:
                return None
            return state
        # Tool events can arrive before the store has attributed them to a task. Resolve
        # only within the event's session; an unscoped fallback would cross-contaminate
        # concurrent sessions in the same repository.
        resolved = self.resolve_task_id(session_id) if session_id else None
        if resolved:
            return self._tasks.get(resolved)
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
        for name in ("file_path", "notebook_path"):
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
                    # lose or reorder the event that preceded it.
                    decision.latency_ms = t.elapsed_ms()
                    try:
                        ws.store.record_event(event)
                        decision.decision_id = (
                            ws.store.record_decision(event, decision) or decision.decision_id
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
        return Decision.allow()

    def _on_user_prompt(self, event: AgentEvent, ws: Workspace) -> Decision:
        """Intent Gateway + Complexity Engine + Planning Governor (SPEC §9, §12, §13).

        The planning budget rides back on `additionalContext`, which the developer never
        sees — so this shapes the agent's approach without adding anything to the UI
        (SPEC §39).
        """
        self._open_session(event, ws)

        prompt = event.prompt_text or ""
        index = ws.index if ws.index.is_built else None
        spec = intent.extract(prompt, index)
        spec.complexity = complexity.assess(spec, index)
        hint = event.host_hints.get("tests_waived")
        if isinstance(hint, bool):
            spec.tests_waiver = hint  # the host decides, either way (H5)
        ws.carry_waiver(event.session_id, spec)
        ws.current_spec = spec

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
            ws.begin_task(task_id, spec, event.session_id)

        budget = planning.render(spec, index)
        if not budget:
            return Decision.allow(EscalationLevel.REPOSITORY)

        return Decision(
            action=DecisionAction.ALLOW,
            level=EscalationLevel.REPOSITORY,
            additional_context=budget,
        )

    def _on_pre_tool_use(self, event: AgentEvent, ws: Workspace) -> Decision:
        """Action Validator (SPEC §18), which runs the Evidence Engine inside it."""
        # SPEC §7/§8: read-only tools never leave Level 0. This short-circuit is what
        # keeps ordinary exploration free.
        if event.is_read_only:
            return Decision.allow()

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
            if isinstance(command, str):
                self._record_test_run(event, ws, state, command)
            # A shell command can touch anything; fall back to a rate-limited sweep.
            if ws.index.is_built:
                ws.index.refresh(min_interval=2.0)

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
            ws.store.finish_verification(
                ws.store.start_verification(state.task_id, outcome.runner),
                "passed" if outcome.passed else "failed",
                {"command": outcome.command, "summary": outcome.summary, "failed": outcome.failed},
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
        # benchmark run 01, where it recommended a deleted test.
        ws.index.refresh(min_interval=5.0)

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
