"""A9-perf: self-protection works out Truthstone's own paths once per validation.

`protected_path` recomputed Truthstone's home (a walk of every ancestor resolving trusted
symlinks), the Codex home and the user's home for every write target. The 900 KB
"writes" line of `test_asks_linear.py` names `~/.zshrc` 3,449 times: 3,449 root
computations, 10,347 home walks and 82,793 `lstat`s in one PreToolUse, which flaked its
1-second budget under load. Now the roots are computed once per validation (by the
validator for a file tool, which two checks judge; at the first write target for a shell
command), and a target named many times is judged once.

The counts are the regression test: timing a loaded machine is not.
"""

from __future__ import annotations

import pytest

from tests.test_asks_linear import THROUGH_THE_GUARD
from tests.test_asks_support import Session, make_guard, make_repo
from truthstone.core.enums import DecisionAction
from truthstone.validate import checks


@pytest.fixture
def session(tmp_path):
    repo = make_repo(tmp_path)
    guard = make_guard(repo)
    session = Session(guard, repo)
    session.prompt("Tidy up.")
    yield session
    guard.close()


@pytest.fixture
def root_calls(monkeypatch) -> list[int]:
    calls: list[int] = []
    original = checks._protected_roots

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(checks, "_protected_roots", counted)
    return calls


def test_a_900kb_line_of_writes_works_out_the_roots_once(session, root_calls):
    decision = session.pre("Bash", command=THROUGH_THE_GUARD["writes"](900_000))
    assert decision.action is DecisionAction.REQUEST_REVIEW, "writing ~/.zshrc is still asked"
    assert len(root_calls) == 1, f"{len(root_calls)} root computations for one validation"


def test_a_file_tool_works_them_out_once_for_both_checks(session, root_calls, isolated_home):
    """A file tool is judged by self-protection and by the outside-write check."""
    assert session.pre("Write", file_path="~/.zshrc", content="export X=1\n").signoff_required
    assert len(root_calls) == 1
    root_calls.clear()
    own = session.pre("Write", file_path=str(isolated_home / "config.toml"), content="enabled = false\n")
    assert own.signoff_required and len(root_calls) == 1


@pytest.mark.parametrize("command", ["pytest -q", "ls -la src", "git commit -m 'tidy'", "make build"])
def test_a_command_that_writes_nothing_never_works_them_out(session, root_calls, command):
    session.pre("Bash", command=command)
    assert root_calls == []


def test_every_distinct_target_is_still_judged(session):
    """Judging a repeated target once must not skip a different one after it."""
    command = "echo x > out.txt; " * 1_000 + "echo '{}' > .claude/settings.json"
    decision = session.pre("Bash", command=command)
    assert decision.signoff_required
    assert any("Claude Code's settings" in finding.summary for finding in decision.findings)


def test_the_same_target_under_another_directory_is_judged_again(session):
    """The memo is keyed on the directory too: `settings.json` is harmless at the root."""
    command = "echo '{}' > settings.json; cd .claude && echo '{}' > settings.json"
    assert session.pre("Bash", command=command).signoff_required


def test_protected_path_keeps_its_signature(tmp_path, isolated_home):
    roots = checks.ProtectedRoots.now()
    for raw in ("~/.truthstone/token", "$TRUTHSTONE_HOME/config.toml", str(isolated_home / "token")):
        alone = checks.protected_path(raw, str(tmp_path))
        assert alone == checks.protected_path(raw, str(tmp_path), roots=roots)
        assert alone == "Truthstone's own configuration and state", raw
    assert checks.protected_path("notes.md", str(tmp_path), roots=roots) == ""
