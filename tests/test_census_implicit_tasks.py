"""H7 x H2: the census counts tasks a prompt opened, everywhere it counts tasks.

A host without a prompt event gets one implicit task per session (H2), so the engine can
keep scope, the ledger and the gate working. That task bounds no work anyone described:
the census headline, the per-host counts and the per-mode counts must all leave it out,
or the same report says "1 task" in one place and "—" in another.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from truthstone.census import collect, render
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import EventType
from truthstone.core.events import AgentEvent
from truthstone.core.store import ProjectStore

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def repo(tmp_path) -> Path:
    return Path(shutil.copytree(FIXTURES / "pyrepo", tmp_path / "pyrepo"))


def _tool_only_session(repo: Path) -> None:
    """A host Truthstone has no profile for, sending tool events only: no prompt."""
    guard = Guard(Settings(observe_only=True))
    guard.workspace(repo).index.ready(timeout=30)
    try:
        for kind in (EventType.PRE_TOOL_USE, EventType.POST_TOOL_USE):
            guard.handle(
                AgentEvent(
                    event=kind,
                    agent="cursor",
                    workspace=str(repo),
                    session_id="x1",
                    tool="Write",
                    arguments={"file_path": "src/shop/api/new.py", "content": "VALUE = 1\n"},
                )
            )
    finally:
        guard.close()


def test_an_implicit_task_is_stored_but_never_counted_as_a_task(repo):
    _tool_only_session(repo)
    store = ProjectStore.for_workspace(repo)
    stored = store.db.query("SELECT depth FROM tasks")
    assert [row["depth"] for row in stored] == ["implicit"], "H2 still keeps a task for the engine"

    assert store.activity(0)["tasks"] == 0
    hosts = store.activity_by_host(0)
    assert set(hosts) == {"cursor"}, "attributed through its events, never to an unknown host"
    assert hosts["cursor"]["tasks"] == 0

    text = render(collect(store, days=1))
    headline = next(line for line in text.splitlines() if "session(s) ·" in line and "decision(s)" in line)
    assert "· 0 task(s) ·" in headline, "the headline agrees with the per-host count"
