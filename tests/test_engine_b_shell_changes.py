"""G5 (shell): changes made through a shell command reach the task.

After a shell command the index swept the tree and learned about `sed -i`, `rm`, `git mv`
or a generator, but the *task* did not: `touched_files` stayed empty, so the gate never
asked for tests (D6 E12, D5). The engine now attributes what each sweep finds to the
shell command that made it, at the place that command took on the task's timeline
(`core/shellchanges.py`). Claude-Code-shaped payloads through the real adapter and Guard.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from truthstone.adapters.claude_code import translate as claude
from truthstone.core import shellchanges
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import DecisionAction

FIXTURES = Path(__file__).parent / "fixtures"
PAGINATION = "src/shop/utils/pagination.py"
MODELS = "src/shop/models.py"
COVERING_TEST = "tests/test_pagination.py"
PASS = "..\n2 passed in 0.10s\n"


@pytest.fixture
def repo(tmp_path) -> Path:
    return Path(shutil.copytree(FIXTURES / "pyrepo", tmp_path / "pyrepo"))


class Agent:
    """One Claude Code session driving the real adapter and Guard."""

    def __init__(self, guard: Guard, repo: Path, session: str = "sess-1") -> None:
        self.guard, self.repo, self.session = guard, repo, session
        self.calls = 0

    @property
    def ws(self):
        return self.guard.workspace(self.repo)

    def send(self, payload: dict):
        payload = {"session_id": self.session, "cwd": str(self.repo), **payload}
        return self.guard.handle(claude.to_event(payload))

    def prompt(self, text: str = "Make paginate treat page 0 as page 1."):
        return self.send({"hook_event_name": "UserPromptSubmit", "prompt": text})

    def shell(self, command: str, change=None, output: str = "", sweep_now: bool = True):
        """PreToolUse, the command's effect on disk, then its PostToolUse."""
        self.calls += 1
        tool = {"tool_name": "Bash", "tool_input": {"command": command}, "tool_use_id": f"t{self.calls}"}
        self.send({"hook_event_name": "PreToolUse", **tool})
        if change is not None:
            change(self.repo)
        if sweep_now:
            self.ws.index.last_refresh = 0.0  # past the rate limit: this sweep runs
        else:
            self.ws.index.last_refresh = time.monotonic()  # a sweep just ran: rate-limited
        response = {"stdout": output, "stderr": "", "interrupted": False}
        return self.send({"hook_event_name": "PostToolUse", "tool_response": response, **tool})

    def stop(self, message: str = "Done."):
        return self.send(
            {"hook_event_name": "Stop", "last_assistant_message": message, "stop_hook_active": False}
        )

    def state(self):
        return self.ws.task_state(None, self.session)


@pytest.fixture
def guard(repo):
    g = Guard(Settings(profile="full"))
    assert g.workspace(repo).index.ready(timeout=30)
    yield g
    g.close()


def _edit(path: str, text: str = "\n# changed by a command\n"):
    def change(repo: Path) -> None:
        target = repo / path
        target.write_text(target.read_text() + text)

    return change


def _remove(path: str):
    return lambda repo: (repo / path).unlink()


def test_sed_in_place_counts_as_a_change(guard, repo):
    """D6 E12: the same change made with Edit blocks; made with `sed -i` it was silent."""
    agent = Agent(guard, repo)
    agent.prompt()
    agent.shell(f"sed -i '' 's/page - 1/max(page, 1) - 1/' {PAGINATION}", _edit(PAGINATION))

    state = agent.state()
    assert PAGINATION in state.touched_files
    held = agent.stop()
    assert held.action is DecisionAction.BLOCK
    assert COVERING_TEST in held.reason and "no tests were run" in held.reason


def test_rm_through_bash_is_a_deletion(guard, repo):
    """D5: after `rm` of a covered file the gate passed. The tests that reached it are
    read from the index as it was before the sweep forgot the file."""
    agent = Agent(guard, repo)
    agent.prompt("Remove the old pagination helper.")
    agent.shell(f"rm {PAGINATION}", _remove(PAGINATION))

    state = agent.state()
    assert state.deleted_files == {PAGINATION}
    assert COVERING_TEST in state.deleted_coverage[PAGINATION]
    held = agent.stop()
    assert held.action is DecisionAction.BLOCK
    assert COVERING_TEST in held.reason


def test_git_mv_counts_both_paths(guard, repo):
    """A move keeps the file's mtime; its ctime says when it moved."""
    agent = Agent(guard, repo)
    agent.prompt("Rename the pagination module to paging.")
    moved = "src/shop/utils/paging.py"
    agent.shell(f"git mv {PAGINATION} {moved}", lambda r: (r / PAGINATION).rename(r / moved))

    state = agent.state()
    assert state.deleted_files == {PAGINATION}
    assert moved in state.touched_files and moved in state.created_files
    assert agent.stop().action is DecisionAction.BLOCK


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_ignored_and_build_outputs_are_not_changes(guard, repo):
    """Only what the index tracks is a change: ignored files and build outputs are not."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    (repo / ".gitignore").write_text("*.log\ngenerated/\n")
    for argv in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "base"],
    ):
        subprocess.run(argv, cwd=repo, env=env, check=True, capture_output=True, timeout=60)
    guard.close()
    guard = Guard(Settings(profile="full"))
    assert guard.workspace(repo).index.ready(timeout=30)
    try:
        agent = Agent(guard, repo)
        agent.prompt()

        def build(root: Path) -> None:
            for path in (
                "build/lib/shop/models.py",  # a build output (exclude_dirs)
                "src/shop/__pycache__/models.cpython-313.pyc",
                "generated/client.py",  # ignored by .gitignore
                "debug.log",
                "NOTES.md",  # tracked by the index: the sweep did look
            ):
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text("x = 1\n")

        agent.shell("make build > debug.log", build)
        assert agent.state().changed_files == {"NOTES.md"}
        assert agent.stop().action is DecisionAction.ALLOW
    finally:
        guard.close()


def test_change_then_test_in_one_command_is_not_stale(guard, repo):
    """`sed -i … && pytest`: the run is the command's last stage, so the change it checked
    sits before it on the timeline. Recording the run first made the pass look stale."""
    agent = Agent(guard, repo)
    agent.prompt()
    agent.shell(f"sed -i '' 's/a/b/' {PAGINATION} && pytest -q 2>&1 | tail -3", _edit(PAGINATION), PASS)

    state = agent.state()
    assert PAGINATION in state.touched_files
    assert agent.stop().action is DecisionAction.ALLOW


def test_a_change_after_the_run_in_one_command_leaves_it_stale(guard, repo):
    """Conservatively after: `pytest && sed -i …` changed the file after the run checked it."""
    agent = Agent(guard, repo)
    agent.prompt()
    agent.shell(f"pytest -q && sed -i '' 's/a/b/' {PAGINATION}", _edit(PAGINATION), PASS)

    held = agent.stop()
    assert held.action is DecisionAction.BLOCK
    assert "changed after the last passing test run" in held.reason


def test_a_rate_limited_sweep_still_lands_on_the_right_task(guard, repo):
    """Session A's command was not swept (rate limit); session B's sweep sees A's change.
    It goes to A's task, at A's place on its timeline — never to B's."""
    a, b = Agent(guard, repo, "sess-a"), Agent(guard, repo, "sess-b")
    a.prompt()
    b.prompt("Explain the models module.")
    a.shell(f"sed -i '' 's/a/b/' {PAGINATION}", _edit(PAGINATION), sweep_now=False)
    assert PAGINATION not in a.state().touched_files, "not swept yet"

    b.shell("ls -la src/shop")  # read-only: holds no place, but its sweep runs
    assert PAGINATION in a.state().touched_files
    assert b.state().changed_files == set()
    assert b.stop().action is DecisionAction.ALLOW
    assert a.stop().action is DecisionAction.BLOCK


def test_stop_drains_a_rate_limited_sweep(guard, repo):
    """Stop's own sweep is rate-limited too; a change waiting for one is swept first."""
    agent = Agent(guard, repo)
    agent.prompt()
    agent.shell(f"sed -i '' 's/a/b/' {PAGINATION}", _edit(PAGINATION), sweep_now=False)
    agent.ws.index.last_refresh = time.monotonic()  # within Stop's interval as well
    held = agent.stop()
    assert held.action is DecisionAction.BLOCK
    assert COVERING_TEST in held.reason


def test_a_change_made_before_the_command_started_is_not_the_agents(guard, repo, monkeypatch):
    """The developer saved a file before the agent's command began: not the agent's."""
    monkeypatch.setattr(shellchanges, "SLACK_S", 0.05)
    agent = Agent(guard, repo)
    agent.prompt()
    _edit(MODELS, "\n# the developer\n")(repo)
    time.sleep(0.2)
    agent.shell("npm run codegen", _edit(PAGINATION))
    state = agent.state()
    assert PAGINATION in state.touched_files
    assert MODELS not in state.touched_files


def test_a_read_only_command_attributes_nothing(guard, repo):
    """A command that only reads (A4) changed nothing: what its sweep sees is not its."""
    agent = Agent(guard, repo)
    agent.prompt()
    agent.shell("grep -rn paginate src", _edit(PAGINATION))  # the developer, meanwhile
    assert agent.state().changed_files == set()
    assert agent.stop().action is DecisionAction.ALLOW


@pytest.mark.parametrize(
    ("command", "before"),
    [
        ("sed -i '' s/a/b/ x.py && pytest -q", True),
        ("sed -i '' s/a/b/ x.py && pytest -q 2>&1 | tail -5", True),
        ("black . && pytest || true", True),
        ("bash -c 'ruff --fix . && pytest'", True),
        ("pytest -q && sed -i '' s/a/b/ x.py", False),
        ("pytest -q; git stash pop", False),
        ("pytest | tee out.log", False),
        ("pytest && echo ok > status.txt", False),
        ("bash -c 'pytest && rm x.py'", False),
        ("sed -i '' s/a/b/ x.py", False),  # no run: nothing to be before
    ],
)
def test_changes_precede_the_run_only_when_it_is_the_last_stage(command, before):
    assert shellchanges.changes_precede_run(command) is before
