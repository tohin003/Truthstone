"""G15: the syntax gate blames only files the task broke.

`static.py` parses with the daemon's own interpreter, which caused two false blocks (D2
st1, st2): a file the project's newer Python parses was "unparsable" to a 3.13 daemon even
after the project's own tests passed, and a template file that never parsed was blocked
as though the agent had broken it.

The baseline is taken at a file's first mutating PreToolUse in the task; each scenario
runs through Claude-Code-shaped PreToolUse/PostToolUse payloads and the real Guard.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.test_gate_timeline import PASS, Session

FIXTURES = Path(__file__).parent / "fixtures"
COVERED = "src/shop/utils/pagination.py"
BROKEN = "\ndef broken(:\n    pass\n"


class SyntaxSession(Session):
    def change(self, path: str, content: str) -> None:
        """PreToolUse (the baseline is taken here), the write, then PostToolUse."""
        full = self.repo / path
        pre = {
            "session_id": "sess-1",
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(full), "content": content},
        }
        self.send(pre)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        self.send({**pre, "hook_event_name": "PostToolUse", "tool_response": {"filePath": str(full)}})


@pytest.fixture
def session(tmp_path):
    repo = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", repo)
    (repo / "src/shop/templates").mkdir()
    (repo / "src/shop/templates/model.py").write_text("class {{ name }}:\n    pass\n")
    s = SyntaxSession(repo)
    yield s
    s.close()


def test_file_that_never_parsed_not_blamed(session):
    """A Jinja template with a .py suffix: it did not parse before the task touched it."""
    session.prompt("Rename the placeholder in the model template.")
    session.change("src/shop/templates/model.py", "class {{ model_name }}:\n    pass\n")
    assert session.state().parse_baseline["src/shop/templates/model.py"] is False
    assert session.stop() == {}


def test_newer_syntax_with_green_tests_not_blocked(session):
    """The daemon cannot parse the file; the project's own test run after the edit
    passed, so its interpreter can (D2 st1: Python 3.14 syntax under a 3.13 daemon)."""
    session.prompt()
    original = (session.repo / COVERED).read_text()
    session.change(COVERED, original + BROKEN)
    session.run("pytest -q", PASS)
    assert session.stop() == {}


def test_newly_broken_file_still_blocks(session):
    session.prompt()
    original = (session.repo / COVERED).read_text()
    session.change(COVERED, original + BROKEN)
    assert session.state().parse_baseline[COVERED] is True
    held = session.stop()
    assert held["decision"] == "block"
    assert "unparsable" in held["reason"]
    assert COVERED in held["reason"]


def test_an_edit_after_the_green_run_is_blamed_again(session):
    session.prompt()
    original = (session.repo / COVERED).read_text()
    session.change(COVERED, original + "\n# fine\n")
    session.run("pytest -q", PASS)
    session.change(COVERED, original + BROKEN)
    held = session.stop()
    assert held["decision"] == "block" and "unparsable" in held["reason"]


def test_a_new_file_counts_as_parsing_before(session):
    session.prompt("Add a helper module.")
    session.change("src/shop/utils/extra.py", "def extra(:\n")
    assert session.state().parse_baseline["src/shop/utils/extra.py"] is True
    held = session.stop()
    assert held["decision"] == "block" and "unparsable" in held["reason"]
