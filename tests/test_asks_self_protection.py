"""A9: self-protection (IMPROVEMENTS.md A9).

An agent that can run `truthstone off`, or rewrite `.claude/settings.json`, can switch its
own guard off. That is the developer's decision, every time: a review request with
`signoff_required`, counted as VERIFICATION_TAMPERING. Reading any of it is fine. Pebble
asks the same way for its own data and the agents' settings (`shell_policy.py:47-83`).

`validator._edited_path` returns "" for a path outside the workspace, so these checks read
the raw path: `~/.claude/settings.json` is never inside the repository.

Nothing here writes anywhere: every path is only judged.
"""

from __future__ import annotations

import pytest

from tests.test_asks_support import Session, make_guard, make_repo, permission, reason
from truthstone.adapters.codex import render as codex_render
from truthstone.core.enums import DecisionAction, FailureMode
from truthstone.validate import checks


@pytest.fixture
def session(tmp_path):
    repo = make_repo(tmp_path)
    guard = make_guard(repo)
    yield Session(guard, repo)
    guard.close()


def assert_signoff(session: Session, tool: str, **args) -> None:
    decision = session.pre(tool, **args)
    assert decision.action is DecisionAction.REQUEST_REVIEW, (tool, args, decision.reason)
    assert decision.signoff_required
    assert any(f.failure_mode is FailureMode.VERIFICATION_TAMPERING for f in decision.findings)
    assert permission(session.claude(tool, **args)) == "ask"
    if tool == "Bash":
        out = session.codex_bash(args["command"])
        assert permission(out) == "deny" and reason(out).startswith(codex_render.SIGN_OFF)


OFF_SWITCHES = [
    "truthstone off",
    "truthstone uninstall",
    "truthstone uninstall --global",
    "truthstone observe on",
    "truthstone daemon stop",
    "python -m truthstone.cli.main off",
    "python3 -m truthstone.cli.main daemon stop",
    "uv run truthstone observe on",
    "uvx --from truthstone truthstone off",
    "pkill -f truthstone",
    "cd /tmp && truthstone off",
    'bash -c "truthstone daemon stop"',
    "for i in 1; do truthstone off; done",
    "truthstone daemon stop && truthstone daemon start",
]


@pytest.mark.parametrize("command", OFF_SWITCHES)
def test_turning_the_guard_off_needs_signoff(session, command):
    session.prompt("Speed things up.")
    assert_signoff(session, "Bash", command=command)


def test_the_off_switch_is_asked_every_time(session):
    session.prompt("Speed things up.")
    for _ in range(3):
        assert_signoff(session, "Bash", command="truthstone off")


class TestWritingTheHooksNeedsSignoff:
    def test_writing_claude_settings_needs_signoff(self, session, isolated_home):
        session.prompt("Tidy the editor configuration.")
        repo = session.repo
        for path in [
            str(repo / ".claude" / "settings.json"),
            str(repo / ".claude" / "settings.local.json"),
            ".claude/settings.local.json",
            "~/.claude/settings.json",
        ]:
            assert_signoff(session, "Write", file_path=path, content="{}")
            assert_signoff(session, "Edit", file_path=path, old_string="truthstone", new_string="")

    def test_writing_truthstones_home_needs_signoff(self, session, isolated_home):
        session.prompt("Tidy up.")
        for path in [str(isolated_home / "config.toml"), str(isolated_home / "token"), "~/.truthstone/x"]:
            assert_signoff(session, "Write", file_path=path, content="enabled = false\n")

    def test_writing_codex_hooks_needs_signoff(self, session):
        session.prompt("Tidy up.")
        project = str(session.repo / ".codex" / "hooks.json")
        for path in ["~/.codex/hooks.json", "~/.codex/config.toml", project]:
            assert_signoff(session, "Write", file_path=path, content="{}")

    @pytest.mark.parametrize(
        "command",
        [
            "echo '{}' > .claude/settings.json",
            "echo '{}' >> ~/.claude/settings.local.json",
            "jq 'del(.hooks)' .claude/settings.json | tee .claude/settings.json",
            "sed -i '' '/truthstone/d' .claude/settings.local.json",
            "rm ~/.truthstone/token",
            "rm -rf ~/.truthstone",
            "mv .claude/settings.json /tmp/settings.json",
            "cp /tmp/empty.json .claude/settings.local.json",
            "cd .claude && echo '{}' > settings.json",
            'echo "enabled = false" > "$TRUTHSTONE_HOME/config.toml"',
            "printf '[hooks]' > ~/.codex/config.toml",
            "for f in .claude/settings*.json; do sed -i '' '/hook/d' $f; done",
        ],
    )
    def test_shell_writes_need_signoff(self, session, command):
        session.prompt("Tidy up.")
        assert_signoff(session, "Bash", command=command)


class TestReadingIsFine:
    @pytest.mark.parametrize(
        "command",
        [
            "cat ~/.claude/settings.json",
            "jq . .claude/settings.json",
            "grep -n truthstone ~/.claude/settings.json",
            "cp .claude/settings.json /tmp/settings.backup.json",
            "ls -la ~/.truthstone",
            "cat ~/.truthstone/config.toml",
            "truthstone status",
            "truthstone doctor",
            "truthstone observe status",
            "truthstone observe off",
            "truthstone on",
            "truthstone daemon status",
            "truthstone log",
            'echo "run truthstone off to disable it" >> docs/notes.md',
            'git commit -m "docs: explain truthstone off"',
            'grep -rn "truthstone off" docs/',
        ],
    )
    def test_reading_settings_is_fine(self, session, command):
        session.prompt("Check how the hooks are configured.")
        decision = session.pre("Bash", command=command)
        tampering = [f for f in decision.findings if f.failure_mode is FailureMode.VERIFICATION_TAMPERING]
        assert not tampering, command
        assert permission(session.claude("Bash", command=command)) != "ask", command

    def test_reading_with_the_tools_is_fine(self, session):
        session.prompt("Check how the hooks are configured.")
        assert session.pre("Read", file_path="~/.claude/settings.json").is_silent
        assert session.pre("Grep", pattern="truthstone", path="~/.claude").is_silent

    @pytest.mark.parametrize(
        "path",
        ["docs/settings.json", "src/claude/settings.json", "config/codex.toml", ".claude/commands/review.md"],
    )
    def test_similar_names_elsewhere_are_not_protected(self, session, path):
        assert checks.protected_path(path, str(session.repo)) == ""
