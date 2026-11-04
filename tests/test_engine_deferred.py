"""WP9: a post-tool hook is answered before its bookkeeping when nothing it decides could speak.

Under the minimal profile nothing reaches the agent after a tool, so the daemon's guard answers
PostToolUse at once and records it right after, on the workspace's worker, in arrival order,
before any later event of that workspace is judged. Stop therefore still sees everything.
Synthetic repositories only.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from tests.test_profile import _python_repo, _session_ending_on_a_failing_run
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import DecisionAction, EventType
from truthstone.core.events import AgentEvent
from truthstone.core.models import Decision
from truthstone.core.store import Database


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


def _event(repo: Path, kind: EventType, **fields) -> AgentEvent:
    return AgentEvent(event=kind, agent="codex", workspace=str(repo), session_id="s", **fields)


def _slow_handlers(guard: Guard, log: list[str], delay: float = 0.3) -> None:
    def post(event: AgentEvent, ws) -> Decision:
        time.sleep(delay)
        log.append(f"post:{event.tool_use_id}")
        return Decision.allow()

    def pre(event: AgentEvent, ws) -> Decision:
        log.append(f"pre:{event.tool_use_id}")
        return Decision.allow()

    def stop(event: AgentEvent, ws) -> Decision:
        log.append("stop")
        return Decision.allow()

    guard._handlers[EventType.POST_TOOL_USE] = post
    guard._handlers[EventType.PRE_TOOL_USE] = pre
    guard._handlers[EventType.STOP] = stop


def test_a_post_tool_event_is_answered_at_once_and_recorded_before_the_next_event(tmp_path):
    repo = _python_repo(tmp_path)
    guard = Guard(Settings(), defer_bookkeeping=True)
    log: list[str] = []
    try:
        guard.workspace(repo).index.ready(timeout=30)
        _slow_handlers(guard, log)
        started = time.perf_counter()
        answer = guard.handle(_event(repo, EventType.POST_TOOL_USE, tool="Bash", tool_use_id="1"))
        assert time.perf_counter() - started < 0.2  # not the handler's 0.3 s
        assert answer.action is DecisionAction.ALLOW and answer.is_silent
        guard.handle(_event(repo, EventType.POST_TOOL_USE, tool="Bash", tool_use_id="2"))
        guard.handle(_event(repo, EventType.PRE_TOOL_USE, tool="Bash", tool_use_id="3"))
        guard.handle(_event(repo, EventType.STOP))
    finally:
        guard.close()
    assert log == ["post:1", "post:2", "pre:3", "stop"]


def test_stop_still_judges_a_test_run_answered_before_it_was_recorded(tmp_path):
    """The red run arrives as a deferred PostToolUse; the Stop right after still holds on it."""
    repo = _python_repo(tmp_path)
    guard = Guard(Settings(), defer_bookkeeping=True)
    try:
        guard.workspace(repo).index.ready(timeout=30)
        output, _decision = _session_ending_on_a_failing_run(guard, repo)
    finally:
        guard.close()
    assert output["decision"] == "block"


def test_the_worker_records_without_a_later_event(tmp_path, isolated_home):
    repo = _python_repo(tmp_path)
    guard = Guard(Settings(), defer_bookkeeping=True)
    try:
        ws = guard.workspace(repo)
        ws.index.ready(timeout=30)
        guard.handle(
            _event(
                repo,
                EventType.POST_TOOL_USE,
                tool="Bash",
                tool_use_id="1",
                arguments={"command": "ls"},
                result={"stdout": "a\n", "exit_code": 0},
            )
        )
        deadline = time.monotonic() + 10
        while ws._deferred and time.monotonic() < deadline:
            time.sleep(0.01)
        with ws.event_lock:  # the worker finished the one it took
            assert not ws._deferred
        rows = Database.shared().query("SELECT type FROM events WHERE type = 'post_tool_use'")
        assert len(rows) == 1
    finally:
        guard.close()


def test_closing_records_what_was_answered(tmp_path):
    repo = _python_repo(tmp_path)
    guard = Guard(Settings(), defer_bookkeeping=True)
    log: list[str] = []
    guard.workspace(repo).index.ready(timeout=30)
    _slow_handlers(guard, log, delay=0.05)
    for n in range(5):
        guard.handle(_event(repo, EventType.POST_TOOL_USE, tool="Bash", tool_use_id=str(n)))
    guard.close()
    assert log == [f"post:{n}" for n in range(5)]


@pytest.mark.parametrize(
    "settings, defers",
    [
        (lambda: Settings(), True),
        (lambda: Settings(observe_only=True), True),
        (lambda: Settings(profile="full"), False),  # a post-tool decision could speak: synchronous
    ],
)
def test_only_a_guard_whose_post_tool_decisions_cannot_speak_defers(tmp_path, settings, defers):
    repo = _python_repo(tmp_path)
    post = _event(repo, EventType.POST_TOOL_USE, tool="Bash")
    assert Guard(settings(), defer_bookkeeping=True)._defers(post) is defers
    assert not Guard(settings())._defers(post)  # in-process callers and replay: synchronous
    assert not Guard(settings(), defer_bookkeeping=True)._defers(
        _event(repo, EventType.PRE_TOOL_USE, tool="Bash")
    )


def test_concurrent_events_of_one_workspace_keep_arrival_order(tmp_path):
    repo = _python_repo(tmp_path)
    guard = Guard(Settings(), defer_bookkeeping=True)
    log: list[str] = []
    try:
        guard.workspace(repo).index.ready(timeout=30)
        _slow_handlers(guard, log, delay=0.02)
        for n in range(10):
            guard.handle(_event(repo, EventType.POST_TOOL_USE, tool="Bash", tool_use_id=str(n)))
        racer = threading.Thread(
            target=guard.handle, args=(_event(repo, EventType.PRE_TOOL_USE, tool="Bash", tool_use_id="x"),)
        )
        racer.start()
        racer.join(timeout=30)
    finally:
        guard.close()
    assert log == [f"post:{n}" for n in range(10)] + ["pre:x"]


def test_the_daemon_defers(tmp_path):
    from truthstone.daemon.app import create_app

    app = create_app("token", Settings())
    try:
        assert app.state.guard.defer_bookkeeping is True
    finally:
        app.state.guard.close()
