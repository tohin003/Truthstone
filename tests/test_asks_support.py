"""Shared harness for the action-time policy tests (IMPROVEMENTS.md cluster A).

Every behaviour in cluster A is pinned through the real ``Guard`` *and* the real host
adapters, because the property that matters is what reaches the host: Claude Code's
``permissionDecision`` and Codex's hook output. A unit test of ``checks`` alone can pass
while the product says nothing (PROGRESS.md, "Design decisions worth remembering").

This module is imported by the ``test_asks_*`` files; its one test checks the harness
itself reaches a real Guard.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from agentguard.adapters.claude_code import translate as claude
from agentguard.adapters.codex import translate as codex
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import EventType
from agentguard.core.events import AgentEvent
from agentguard.core.models import Decision

FIXTURES = Path(__file__).parent / "fixtures"

# Writes a call to a member `UserRepository` does not have: a guaranteed CHALLENGE.
HALLUCINATION = (
    "from shop.repositories.user import UserRepository\n\n\n"
    "def report(session):\n"
    "    return UserRepository(session).{member}()\n"
)


def make_repo(tmp_path: Path, name: str = "pyrepo") -> Path:
    """A committed copy of the `pyrepo` fixture (git status is clean)."""
    dest = tmp_path / name
    shutil.copytree(FIXTURES / "pyrepo", dest)
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=dest,
        check=True,
    )
    return dest


def make_guard(repo: Path, settings: Settings | None = None) -> Guard:
    guard = Guard(settings or Settings())
    guard.workspace(repo).index.ready(timeout=30)
    return guard


class Session:
    """One host session against a real Guard.

    ``pre`` returns the core ``Decision``; ``claude`` and ``codex`` return exactly what each
    host would receive for the same proposed action.
    """

    def __init__(self, guard: Guard, repo: Path, session_id: str = "sess-asks") -> None:
        self.guard = guard
        self.repo = repo
        self.session_id = session_id

    @property
    def workspace(self):
        return self.guard.workspace(self.repo)

    @property
    def task_id(self) -> str | None:
        return self.workspace.store.current_task_id(self.session_id)

    def _event(self, kind: EventType, tool: str | None = None, **args: Any) -> AgentEvent:
        return AgentEvent(
            event=kind,
            agent="claude-code",
            workspace=str(self.repo),
            session_id=self.session_id,
            tool=tool,
            arguments=args,
            raw={},
        )

    def prompt(self, text: str) -> Decision:
        event = self._event(EventType.USER_PROMPT)
        event.prompt_text = text
        return self.guard.handle(event)

    def pre(self, tool: str, **args: Any) -> Decision:
        return self.guard.handle(self._event(EventType.PRE_TOOL_USE, tool, **args))

    def post(self, tool: str, result: Any = None, **args: Any) -> Decision:
        event = self._event(EventType.POST_TOOL_USE, tool, **args)
        event.result = result
        return self.guard.handle(event)

    def claude(self, tool: str, **args: Any) -> dict:
        """What Claude Code receives for this PreToolUse (``{}`` is silence)."""
        event = self._event(EventType.PRE_TOOL_USE, tool, **args)
        decision = self.guard.handle(event)
        return claude.from_decision(event, decision, "PreToolUse")

    def codex(self, hook: str, **fields: Any) -> dict:
        """What Codex receives, through the adapter's own daemon entry point."""
        payload = {
            "session_id": self.session_id,
            "turn_id": "turn-1",
            "transcript_path": None,
            "cwd": str(self.repo),
            "hook_event_name": hook,
            "model": "gpt-test",
            "permission_mode": "default",
            **fields,
        }
        return codex.handle_payload(self.guard, payload)

    def codex_bash(self, command: str) -> dict:
        return self.codex(
            "PreToolUse", tool_name="Bash", tool_input={"command": command}, tool_use_id="call-1"
        )


def permission(out: dict) -> str | None:
    """The PreToolUse permission decision a host received, or None for silence."""
    return out.get("hookSpecificOutput", {}).get("permissionDecision")


def reason(out: dict) -> str:
    return out.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


def test_the_harness_reaches_a_real_guard(tmp_path):
    repo = make_repo(tmp_path)
    guard = make_guard(repo)
    try:
        session = Session(guard, repo)
        session.prompt("Fix the paginate helper.")
        assert session.task_id
        assert session.claude("Bash", command="ls src") == {}
        assert session.codex_bash("ls src") == {}
    finally:
        guard.close()
