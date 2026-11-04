"""G2a: verification is a timeline — the latest run decides, later edits make it stale.

Before, `VerificationState.any_failed` never forgot. Fail -> fix -> pass ended in
"verification_failed ... the task is not complete while its own tests are failing"
(probe B); in the lead's corpus 62 of 81 such real blocks were false because the latest
run was green, and 48 of 101 Codex test-running turns went fail -> pass. In the other
direction a pass was accepted however much changed after it (probe C).

Every scenario here is driven through Claude-Code-shaped payloads, the real adapter and
the real Guard, over a copy of the `pyrepo` fixture, where
`src/shop/utils/pagination.py` is covered by `tests/test_pagination.py`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.conftest import stop_event, user_prompt_submit
from truthstone.adapters.claude_code import translate as claude
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.verify import runners

FIXTURES = Path(__file__).parent / "fixtures"
SOURCE = "src/shop/utils/pagination.py"

FAIL = "F.\n=== FAILURES ===\nE   assert 0 == 1\n=== 1 failed, 1 passed in 0.12s ===\n"
PASS = "..\n=== 2 passed in 0.10s ===\n"


class Session:
    """A Claude Code session, one payload at a time, through the real adapter."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.guard = Guard(Settings(profile="full"))
        self.guard.workspace(repo).index.ready(timeout=30)

    def send(self, payload: dict) -> dict:
        event = claude.to_event({**payload, "cwd": str(self.repo)})
        return claude.from_decision(event, self.guard.handle(event), payload["hook_event_name"])

    def prompt(self, text: str = "Fix the paginate helper so page 0 is treated as page 1.") -> dict:
        return self.send(user_prompt_submit(text))

    def edit(self, path: str = SOURCE, append: str = "\n# touched\n") -> dict:
        full = self.repo / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text((full.read_text() if full.exists() else "") + append)
        return self.send(
            {
                "session_id": "sess-1",
                "hook_event_name": "PostToolUse",
                "tool_name": "Edit",
                "tool_input": {"file_path": str(full), "old_string": "a", "new_string": "b"},
                "tool_response": {"filePath": str(full)},
            }
        )

    def run(self, command: str, output: str, exit_code: int = 0, interrupted: bool = False) -> dict:
        """Exit 0 arrives as PostToolUse; anything else as PostToolUseFailure (A.1)."""
        if exit_code == 0 and not interrupted:
            payload = {
                "hook_event_name": "PostToolUse",
                "tool_response": {"stdout": output, "stderr": "", "interrupted": False},
            }
        else:
            payload = {
                "hook_event_name": "PostToolUseFailure",
                "error": f"Exit code {exit_code}\n{output}",
                "is_interrupt": interrupted,
            }
        return self.send(
            {**payload, "session_id": "sess-1", "tool_name": "Bash", "tool_input": {"command": command}}
        )

    def stop(self, message: str = "Done.") -> dict:
        return self.send(stop_event(message))

    def state(self):
        return self.guard.workspace(self.repo).task_state(None, "sess-1")

    def close(self) -> None:
        self.guard.close()


@pytest.fixture
def session(tmp_path):
    repo = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", repo)
    s = Session(repo)
    yield s
    s.close()


# -- the five cases ------------------------------------------------------------------------


def test_red_then_green_finishes_silently(session):
    """Probe B: a failing run visible through `| tail`, a fix, a passing run."""
    session.prompt()
    session.edit()
    session.run("pytest -q tests/ 2>&1 | tail -15", FAIL)
    session.edit()
    session.run("pytest -q tests/ 2>&1 | tail -15", PASS)
    assert session.stop("Fixed; the suite is green now.") == {}


def test_fail_pass_fail_blocks(session):
    session.prompt()
    session.edit()
    session.run("pytest -q", FAIL, exit_code=1)
    session.edit()
    session.run("pytest -q", PASS)
    session.edit()
    session.run("pytest -q", FAIL, exit_code=1)
    held = session.stop("All tests pass.")
    assert held["decision"] == "block"
    assert "verification_failed" in held["reason"]
    assert "`pytest -q`" in held["reason"]


def test_pass_then_edit_is_stale_incomplete(session):
    """Probe C: tests pass, more source edits, then "Done"."""
    session.prompt()
    session.edit()
    session.run("pytest -q", PASS)
    session.edit(append="\ndef paginate_v2(*a):\n    raise NotImplementedError\n")
    held = session.stop("Done, tests pass.")
    assert held["decision"] == "block"
    assert "incomplete" in held["reason"]
    assert SOURCE in held["reason"]
    assert "changed after the last passing test run" in held["reason"]
    findings = _last_findings(session)
    assert "stale-verification" in findings


def test_narrower_green_after_full_red_is_incomplete(session):
    """A green subset does not show the full suite's failure is fixed (D2)."""
    session.prompt()
    session.edit()
    session.run("pytest", FAIL, exit_code=1)
    session.edit()
    session.run("pytest tests/test_pagination.py::test_paginate", "1 passed in 0.01s\n")
    held = session.stop("Fixed.")
    assert held["decision"] == "block"
    assert "incomplete" in held["reason"]
    assert "Re-run `pytest`" in held["reason"]
    assert "verification_failed" not in held["reason"]
    assert "narrower-verification" in _last_findings(session)


def test_interrupted_run_is_not_a_failure(session):
    session.prompt()
    session.edit()
    session.run("pytest -q", "..\n!!! KeyboardInterrupt !!!\n", exit_code=130, interrupted=True)
    assert session.state().verification.outcomes == []
    assert session.stop() == {}, "an interrupted run is inconclusive, never a failure"


# -- the rules around them ----------------------------------------------------------------


def test_a_pass_followed_by_an_interrupted_run_still_passes(session):
    session.prompt()
    session.edit()
    session.run("pytest -q", PASS)
    session.run("pytest -q", "..", exit_code=130, interrupted=True)
    assert session.stop() == {}


def test_a_broader_green_closes_a_narrow_red(session):
    session.prompt()
    session.edit()
    session.run("pytest tests/test_pagination.py", FAIL, exit_code=1)
    session.edit()
    session.run("pytest", PASS)
    assert session.stop() == {}


def test_a_new_untested_file_after_the_pass_is_not_stale(session):
    """Re-running the suite would not check a module nothing tests."""
    session.prompt()
    session.edit()
    session.run("pytest -q", PASS)
    session.edit("src/shop/utils/brand_new.py", append="def helper():\n    return 1\n")
    assert session.stop() == {}


def test_a_test_written_after_the_pass_is_stale(session):
    session.prompt()
    session.edit()
    session.run("pytest -q", PASS)
    session.edit("tests/test_pagination.py", append="\n\ndef test_page_zero():\n    assert True\n")
    held = session.stop()
    assert held["decision"] == "block"
    assert "tests/test_pagination.py" in held["reason"]


def test_an_unreadable_run_after_the_edit_is_not_called_stale(session):
    """A run did happen after the edit; its output was unreadable. Could not tell is
    never a failure, so the earlier pass is not reported stale."""
    session.prompt()
    session.edit()
    session.run("pytest -q", PASS)
    session.edit()
    session.run("make test", "building...\nall done\n")
    assert session.stop() == {}


def test_a_waiver_excuses_a_stale_pass_but_not_a_failure(session):
    session.prompt("Fix the paginate helper. Do not run tests.")
    session.edit()
    session.run("pytest -q", PASS)
    session.edit()
    assert session.stop() == {}
    session.run("pytest -q", FAIL, exit_code=1)
    held = session.stop()
    assert held["decision"] == "block" and "verification_failed" in held["reason"]


def test_runs_carry_their_place_on_the_timeline(session):
    session.prompt()
    session.edit()
    session.run("uv run pytest -q tests/test_pagination.py", PASS)
    state = session.state()
    run = state.verification.outcomes[-1]
    assert run.seq is not None and run.seq > state.last_change_seq[SOURCE]
    assert run.family == "python"
    assert run.key == "pytest -q tests/test_pagination.py"
    assert run.scope == ("tests/test_pagination.py",)


def _last_findings(session: Session) -> set[str]:
    ws = session.guard.workspace(session.repo)
    rows = ws.store.db.query("SELECT subject FROM findings WHERE project_id=?", (ws.store.project_id,))
    return {row["subject"] for row in rows}


# -- coverage between runs --------------------------------------------------------------------


def _run(command: str, passed: bool) -> runners.TestOutcome:
    return runners.parse_output(command, PASS if passed else FAIL)


@pytest.mark.parametrize(
    ("later", "earlier", "covered"),
    [
        ("pytest", "pytest tests/test_a.py", True),
        ("pytest -q", "pytest -k slow", True),
        ("pytest tests/", "pytest", True),  # the top-level test folder is the suite
        ("pytest tests/test_a.py", "pytest tests/test_a.py::test_x", True),
        ("pytest tests/unit", "pytest tests/unit/test_a.py", True),
        ("pytest -k foo", "pytest -k foo", True),
        ("pytest tests/test_a.py::test_x", "pytest tests/test_a.py", False),
        ("pytest tests/test_b.py", "pytest tests/test_a.py", False),
        ("pytest -k foo", "pytest", False),
        ("pytest --lf", "pytest", False),
        ("npx jest src/a.test.ts", "npm test", False),
        ("npm test", "npx jest src/a.test.ts", True),
        ("go test ./...", "go test ./pkg/x", True),
        ("go test ./pkg/x", "go test ./...", False),
    ],
)
def test_covers(later, earlier, covered):
    assert runners.covers(_run(later, True), _run(earlier, False)) is covered
