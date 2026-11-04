"""A8: verification-bypass flags (IMPROVEMENTS.md A8).

`git commit --no-verify` and its relatives switch off the checks that verify the work.
Transcripts show five uses of `--no-verify`, none flagged. Pebble looks for the same
flags (`conventions.py:285-297`). Skipping a hook can be right, so the agent is told —
once per task — and not stopped; the census counts it as VERIFICATION_TAMPERING.
"""

from __future__ import annotations

import pytest

from agentguard.census.taxonomy import BY_MODE, NOT_INSTRUMENTED_BECAUSE
from agentguard.challenge.renderer import OVERRIDE
from agentguard.core.enums import DecisionAction, EventType, FailureMode, Severity
from agentguard.core.events import AgentEvent
from agentguard.validate import checks
from tests.test_asks_support import Session, make_guard, make_repo, permission, reason


def bash(command: str) -> AgentEvent:
    return AgentEvent(event=EventType.PRE_TOOL_USE, tool="Bash", arguments={"command": command})


def concerns(command: str) -> list[str]:
    return [f.subject for f in checks.verification_bypass(bash(command))]


@pytest.fixture
def session(tmp_path):
    repo = make_repo(tmp_path)
    guard = make_guard(repo)
    yield Session(guard, repo)
    guard.close()


class TestDetection:
    @pytest.mark.parametrize(
        "command",
        [
            "git commit --no-verify -m wip",
            "git commit -n -m wip",
            "git commit -anm wip",
            "git -C sub commit --no-verify -am x",
            "git push --no-verify origin feature",
            "git merge --no-verify feature",
            "git rebase --no-verify main",
            "HUSKY=0 git commit -m x",
            "env HUSKY=0 git push",
            "export HUSKY=0 && git commit -m x",
            "SKIP=flake8,mypy git commit -m x",
            "SKIP=ruff pre-commit run --all-files",
            'bash -c "git commit --no-verify -m x"',
            "for m in a b; do git commit --no-verify -m $m; done",
        ],
    )
    def test_hook_bypasses(self, command):
        assert concerns(command) == ["git hooks skipped"], command

    @pytest.mark.parametrize(
        "command",
        [
            "mvn -DskipTests package",
            "mvn install -Dmaven.test.skip=true",
            "./mvnw -DskipTests=true verify",
            "cargo make release --skip-tests",
            "SKIP_TESTS=1 make release",
        ],
    )
    def test_test_phase_bypasses(self, command):
        assert concerns(command) == ["test phase skipped"], command

    def test_push_dry_run_is_not_a_bypass(self, session):
        for command in [
            "git push -n origin main",
            "git push --dry-run origin feature",
            "git commit -m -n",  # -n is the message
            "git commit -mn",  # so is this
            "git log -n 5",
            "git commit -m 'stop using --no-verify'",
            "grep -rn -- --no-verify docs/",
            "echo HUSKY=0",
            "SKIP=1 make test",  # not pre-commit's SKIP
            "HUSKY=1 git commit -m x",
        ]:
            assert concerns(command) == [], command
        session.prompt("Publish the branch.")
        assert session.pre("Bash", command="git push -n origin feature").action is DecisionAction.ALLOW


class TestThroughTheGuard:
    def test_hook_bypass_is_challenged_once(self, session):
        session.prompt("Commit the work in progress.")
        first = session.pre("Bash", command="git commit --no-verify -m wip")
        assert first.action is DecisionAction.CHALLENGE
        finding = next(f for f in first.findings if f.failure_mode is FailureMode.VERIFICATION_TAMPERING)
        assert finding.severity is Severity.MEDIUM
        assert "--no-verify" in first.reason and OVERRIDE in first.reason

        # Heard once: another way round the same hooks proceeds, and is still recorded.
        for command in ["git commit -n -m 'wip 2'", "HUSKY=0 git commit -m 'wip 3'"]:
            again = session.pre("Bash", command=command)
            assert again.action is DecisionAction.ALLOW, command
            assert any(f.failure_mode is FailureMode.VERIFICATION_TAMPERING for f in again.findings)

        # A different concern — the build's tests — is its own.
        tests = session.pre("Bash", command="mvn -DskipTests package")
        assert tests.action is DecisionAction.CHALLENGE

    def test_both_hosts_hear_it(self, session):
        session.prompt("Ship it.")
        claude = session.claude("Bash", command="git push --no-verify origin feature")
        assert permission(claude) == "deny" and "git hooks" in reason(claude)

    def test_codex_hears_it(self, tmp_path):
        repo = make_repo(tmp_path)
        guard = make_guard(repo)
        try:
            codex = Session(guard, repo, session_id="sess-codex")
            codex.codex("UserPromptSubmit", prompt="Ship it.")
            out = codex.codex_bash("git commit --no-verify -m wip")
            assert permission(out) == "deny" and "git hooks" in reason(out)
        finally:
            guard.close()


def test_the_census_says_what_a_bypass_proves():
    entry = BY_MODE[FailureMode.VERIFICATION_TAMPERING]
    assert entry.instrumented and "--no-verify" in entry.detector
    assert "does not prove" in entry.proves.lower()
    assert FailureMode.VERIFICATION_TAMPERING not in NOT_INSTRUMENTED_BECAUSE
