"""G8: verification debt survives follow-up prompts.

Every prompt started a fresh TaskState, so "continue" forgot the failing run and the
unverified edits, and "All done, tests pass." then passed (probe H). A host whose Stop
continuation arrives as a new prompt lost the debt the gate had just named. The session's
next task now inherits the debt — never across sessions — and the gate's block budget
travels with it, so no prompt can refresh it into a loop.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agentguard.adapters.claude_code import translate as claude
from agentguard.adapters.codex import translate as codex
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import DecisionAction

FIXTURES = Path(__file__).parent / "fixtures"
PAGINATION = "src/shop/utils/pagination.py"
FAIL = "F.\n=== FAILURES ===\nE   assert 0 == 1\n=== 1 failed, 1 passed in 0.12s ===\n"
PASS = "..\n=== 2 passed in 0.10s ===\n"


@pytest.fixture
def repo(tmp_path) -> Path:
    return Path(shutil.copytree(FIXTURES / "pyrepo", tmp_path / "pyrepo"))


@pytest.fixture
def guard(repo):
    g = Guard(Settings())
    assert g.workspace(repo).index.ready(timeout=30)
    yield g
    g.close()


class Claude:
    def __init__(self, guard: Guard, repo: Path, session: str = "sess-1") -> None:
        self.guard, self.repo, self.session = guard, repo, session

    def send(self, name: str, **fields):
        payload = {"session_id": self.session, "cwd": str(self.repo), "hook_event_name": name, **fields}
        return self.guard.handle(claude.to_event(payload))

    def prompt(self, text: str):
        return self.send("UserPromptSubmit", prompt=text)

    def edit(self, path: str = PAGINATION):
        full = self.repo / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text((full.read_text() if full.exists() else "") + "\n# edited\n")
        arguments = {"file_path": str(full), "old_string": "a", "new_string": "b"}
        self.send("PreToolUse", tool_name="Edit", tool_input=arguments)
        return self.send("PostToolUse", tool_name="Edit", tool_input=arguments,
                         tool_response={"filePath": str(full)})

    def pytest(self, passed: bool):
        tool = {"tool_name": "Bash", "tool_input": {"command": "pytest -q"}}
        if passed:
            return self.send("PostToolUse", tool_response={"stdout": PASS, "stderr": ""}, **tool)
        return self.send("PostToolUseFailure", error=f"Exit code 1\n{FAIL}", **tool)

    def stop(self, message: str = "All done, tests pass.", active: bool = False):
        return self.send("Stop", last_assistant_message=message, stop_hook_active=active)

    def state(self):
        return self.guard.workspace(self.repo).task_state(None, self.session)


def failing_task(agent: Claude) -> None:
    agent.prompt("Make paginate treat page 0 as page 1.")
    agent.edit()
    agent.pytest(passed=False)


def test_continue_keeps_failing_run(guard, repo):
    """Probe H: a failing run, then "continue", then "All done, tests pass."."""
    agent = Claude(guard, repo)
    failing_task(agent)
    agent.prompt("continue")
    state = agent.state()
    assert PAGINATION in state.touched_files and state.verification.outcomes[-1].passed is False
    held = agent.stop()
    assert held.action is DecisionAction.BLOCK
    assert "reported failures" in held.reason


def test_unverified_edits_survive_a_follow_up(guard, repo):
    agent = Claude(guard, repo)
    agent.prompt("Make paginate treat page 0 as page 1.")
    agent.edit()
    agent.prompt("Also make sure page_metadata is right.")
    held = agent.stop("Done.")
    assert held.action is DecisionAction.BLOCK
    assert "tests/test_pagination.py" in held.reason


def test_codex_continuation_prompt_keeps_task(guard, repo):
    """A Stop continuation that arrives as a new prompt — the gate's own reason — keeps
    the debt it names, and the block budget it has already spent."""

    def send(name: str, **fields):
        payload = {"session_id": "codex-1", "turn_id": "t1", "cwd": str(repo), "hook_event_name": name}
        payload.update(fields)
        (event,) = codex.to_events(payload)
        return guard.handle(event)

    send("UserPromptSubmit", prompt="Make paginate treat page 0 as page 1.")
    patch = (
        "*** Begin Patch\n*** Update File: src/shop/utils/pagination.py\n@@\n"
        "-    per_page = min(per_page, MAX_PAGE_SIZE)\n+    per_page = min(per_page, MAX_PAGE_SIZE)  # x\n"
        "*** End Patch"
    )
    target = repo / PAGINATION
    target.write_text(target.read_text().replace("MAX_PAGE_SIZE)\n", "MAX_PAGE_SIZE)  # x\n", 1))
    send("PostToolUse", tool_name="apply_patch", tool_input={"command": patch}, tool_response="Success.")
    send("PostToolUse", tool_name="Bash", tool_input={"command": "pytest -q"}, tool_response=FAIL)

    first = send("Stop", stop_hook_active=False, last_assistant_message="Done.")
    assert first.action is DecisionAction.BLOCK
    send("UserPromptSubmit", prompt=first.reason)  # the continuation, as a new prompt
    state = guard.workspace(repo).task_state(None, "codex-1")
    assert state.verification.outcomes[-1].passed is False and PAGINATION in state.changed_files
    assert state.stop_blocks == 1, "the budget it already spent came with it"

    second = send("Stop", stop_hook_active=False, last_assistant_message="Done.")
    assert second.action is DecisionAction.BLOCK
    send("UserPromptSubmit", prompt=second.reason)
    third = send("Stop", stop_hook_active=False, last_assistant_message="Done.")
    assert third.action is DecisionAction.ALLOW, "budget spent: no endless loop across prompts"
    assert third.unverified_finish, "and the developer is told the turn ended unverified (G10)"


def test_new_session_starts_clean(guard, repo):
    a, b = Claude(guard, repo, "sess-a"), Claude(guard, repo, "sess-b")
    failing_task(a)
    b.prompt("continue")
    state = b.state()
    assert state.changed_files == set() and not state.verification.outcomes
    assert b.stop().action is DecisionAction.ALLOW
    assert a.stop().action is DecisionAction.BLOCK


def test_the_block_budget_stays_bounded_across_prompts(guard, repo):
    """Two blocks for one unresolved debt, however many prompts follow — continuations
    and a genuinely new request alike."""
    agent = Claude(guard, repo)
    failing_task(agent)
    outcomes = []
    for prompt in ("continue", "continue", "keep going", "Now explain the models module."):
        outcomes.append(agent.stop().action)
        agent.prompt(prompt)
    outcomes.append(agent.stop().action)
    assert outcomes.count(DecisionAction.BLOCK) == 2
    assert outcomes[:2] == [DecisionAction.BLOCK, DecisionAction.BLOCK]
    assert agent.state().stop_blocks == 2


def test_a_signoff_reply_keeps_the_debt(guard, repo):
    """The developer's `approve <CODE>` reply (A1b) is a continuation, not a new task."""
    agent = Claude(guard, repo)
    failing_task(agent)
    agent.prompt("approve K7M2QX")
    assert agent.stop().action is DecisionAction.BLOCK


def test_a_paid_debt_leaves_the_next_task_clean(guard, repo):
    agent = Claude(guard, repo)
    failing_task(agent)
    agent.edit()
    agent.pytest(passed=True)
    agent.prompt("Now add a docstring to models.")
    state = agent.state()
    assert state.changed_files == set() and not state.verification.outcomes
    assert state.stop_blocks == 0


def test_inherited_files_are_not_the_new_requests_drift(guard, repo):
    """A follow-up naming its own scope is judged on what it changes, not on the files
    the unfinished task left behind."""
    agent = Claude(guard, repo)
    agent.prompt("Tidy things up.")
    for k in range(6):
        agent.edit(f"src/shop/extra/helper_{k}.py")
    agent.pytest(passed=False)
    agent.prompt("Add a total field to src/shop/api/orders.py")
    assert "src/shop/api/orders.py" in agent.state().spec.expected_scope
    orders = repo / "src/shop/api/orders.py"
    arguments = {"file_path": str(orders), "old_string": "a", "new_string": "b"}
    decision = agent.send("PreToolUse", tool_name="Edit", tool_input=arguments)
    assert not [f for f in decision.findings if f.category.value == "scope"]
