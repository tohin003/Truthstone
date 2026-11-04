"""H3: reads are not writes.

`_on_post_tool_use` marked any event carrying `file_path` or `notebook_path` as a
touched file, whatever the tool. Hosts whose post-hooks fire for reads (Cursor, Gemini)
would thereby "change" every file the agent looked at, feeding scope false positives
and making the gate demand tests for code nobody edited (D5 F3; Pebble strips the same
thing, guard.py:559-563). Only an edit, a write or a deletion that went through touches
a file now.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import DecisionAction, EventType
from agentguard.core.events import AgentEvent

FIXTURES = Path(__file__).parent / "fixtures"
COVERED = "src/shop/utils/pagination.py"


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", dest)
    return dest


@pytest.fixture
def guard(repo):
    g = Guard(Settings())
    g.workspace(repo).index.ready(timeout=30)
    g.handle(
        AgentEvent(
            event=EventType.USER_PROMPT,
            agent="cursor",
            workspace=str(repo),
            session_id="s1",
            prompt_text="Fix the paginate helper.",
        )
    )
    yield g
    g.close()


def _post(repo: Path, tool: str, kind: EventType = EventType.POST_TOOL_USE, **args) -> AgentEvent:
    return AgentEvent(
        event=kind, agent="cursor", workspace=str(repo), session_id="s1", tool=tool, arguments=args
    )


def _touched(guard, repo: Path) -> set[str]:
    return guard.workspace(repo).task_state(None, "s1").touched_files


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("Read", {"file_path": COVERED}),
        ("NotebookRead", {"notebook_path": "notebooks/a.ipynb"}),
        ("Grep", {"file_path": COVERED, "pattern": "paginate"}),
        ("mcp__docs__fetch", {"file_path": COVERED}),
    ],
)
def test_a_read_post_event_touches_nothing(guard, repo, tool, args):
    guard.handle(_post(repo, tool, **args))
    assert _touched(guard, repo) == set()
    assert guard.handle(_post(repo, "", EventType.STOP)).action is DecisionAction.ALLOW


def test_an_edit_still_touches_its_file(guard, repo):
    guard.handle(_post(repo, "Edit", file_path=COVERED))
    assert _touched(guard, repo) == {COVERED}


def test_a_failed_edit_touches_nothing(guard, repo):
    """PostToolUseFailure: the edit did not happen."""
    guard.handle(_post(repo, "Edit", EventType.POST_TOOL_FAILURE, file_path=COVERED))
    assert _touched(guard, repo) == set()


def test_reading_then_editing_counts_the_edit_only(guard, repo):
    guard.handle(_post(repo, "Read", file_path="src/shop/api/users.py"))
    guard.handle(_post(repo, "Write", file_path=COVERED, content="x = 1\n"))
    assert _touched(guard, repo) == {COVERED}
