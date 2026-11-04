"""A5-core: MODIFY may only rewrite what it can make provably safe (IMPROVEMENTS.md A5).

MODIFY used to run *before* the risk checks, and its one rewrite was unsound in four
measured ways: `rm -rf $HOME` (critical) became a "guarded" command that still deletes
home, `${OUT:-/tmp/x}` became invalid shell, `rm -rf $A $B/` left `$B` unguarded, and a
quoted `$DIRS` changed meaning. The Codex adapter shows the guarded form to the agent as
"re-issue it in this guarded form", so an unsound rewrite is an active hazard.

Now the risk checks judge the original first, and a rewrite happens only when the one
serious finding is the unset-variable delete and the guard is sound. Otherwise the
developer is asked — with the guarded form as a suggestion when one is sound.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from agentguard.adapters.codex import render as codex_render
from agentguard.challenge.ledger import ChallengeLedger
from agentguard.core.enums import DecisionAction, EventType
from agentguard.core.events import AgentEvent
from agentguard.core.store import ProjectStore
from agentguard.repo import RepoIndex
from agentguard.validate import modify, validate
from tests.test_asks_support import Session, make_guard, make_repo, permission, reason

BASH = shutil.which("bash")


@pytest.fixture
def index(workspace) -> RepoIndex:
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "a.py").write_text("x = 1\n")
    return RepoIndex(workspace).build()


def decide(index: RepoIndex, command: str):
    ledger = ChallengeLedger(ProjectStore.for_workspace(index.root))
    event = AgentEvent(
        event=EventType.PRE_TOOL_USE,
        agent="claude-code",
        workspace=str(index.root),
        session_id="s1",
        tool="Bash",
        arguments={"command": command},
    )
    return validate(event, index, None, ledger, "task-1")


def bash_event(command: str) -> AgentEvent:
    return AgentEvent(event=EventType.PRE_TOOL_USE, tool="Bash", arguments={"command": command})


def parses(command: str) -> bool:
    return subprocess.run([BASH, "-n", "-c", command], capture_output=True).returncode == 0


@pytest.fixture
def session(tmp_path):
    repo = make_repo(tmp_path)
    guard = make_guard(repo)
    yield Session(guard, repo)
    guard.close()


class TestNeverRewriteWhatCannotBeMadeSafe:
    def test_home_delete_is_reviewed_not_rewritten(self, index, session):
        """`[ -n "$HOME" ] && rm -rf "$HOME"` still deletes home: no rewrite, no suggestion."""
        decision = decide(index, "rm -rf $HOME")
        assert decision.action is DecisionAction.REQUEST_REVIEW
        assert decision.signoff_required
        assert decision.updated_arguments is None
        assert "[ -n" not in decision.reason and "Safer form" not in decision.reason

        session.prompt("Clean up.")
        assert permission(session.claude("Bash", command="rm -rf $HOME")) == "ask"
        codex = session.codex_bash("rm -rf $HOME")
        assert permission(codex) == "deny"
        assert reason(codex).startswith(codex_render.SIGN_OFF)
        assert "[ -n" not in reason(codex)
        assert "guarded form" not in reason(codex)

    @pytest.mark.parametrize("variable", ["PWD", "TMPDIR", "USER", "OLDPWD", "PATH"])
    def test_always_set_variables_are_never_guarded(self, index, variable):
        decision = decide(index, f"rm -rf ${variable}")
        assert decision.action is DecisionAction.REQUEST_REVIEW
        assert decision.updated_arguments is None
        assert "Safer form" not in decision.reason

    def test_default_expansion_not_rewritten(self, index):
        """It used to become `[ -n "${OUT" ] && rm -rf "${OUT":-/tmp/x}` (`bash -n`: 2)."""
        alone = decide(index, "rm -rf ${OUT:-/tmp/x}")
        assert alone.action is not DecisionAction.MODIFY
        assert alone.updated_arguments is None
        assert modify.propose(bash_event("rm -rf ${OUT:-/tmp/x}")) is None

        mixed = decide(index, "rm -rf $A ${OUT:-/tmp/x}")
        assert mixed.action is DecisionAction.REQUEST_REVIEW
        assert mixed.updated_arguments is None
        assert "Safer form" not in mixed.reason

    def test_multi_variable_not_rewritten(self, index):
        """`rm -rf $A $B/` used to guard `$A` and leave `$B`. Now: asked, with both guarded
        in the suggestion."""
        decision = decide(index, "rm -rf $A $B/")
        assert decision.action is DecisionAction.REQUEST_REVIEW
        assert decision.updated_arguments is None
        suggestion = decision.reason.split("Safer form: `", 1)[1].rstrip("`")
        assert '[ -n "$A" ]' in suggestion and '[ -n "$B" ]' in suggestion
        assert '"$A"' in suggestion and '"$B"/' in suggestion

    def test_word_split_variable_not_rewritten(self, index):
        """Quoting `$DIRS` turns `rm -rf dist build` into `rm -rf "dist build"`."""
        decision = decide(index, 'DIRS="dist build"; rm -rf $DIRS')
        assert decision.action is not DecisionAction.MODIFY
        assert decision.updated_arguments is None
        assert "Safer form" not in decision.reason

    @pytest.mark.parametrize(
        "command",
        [
            "test -d out || rm -rf $OUT",  # a prefixed guard would run rm when `test` passes
            "rm -rf $OUT || echo failed",  # ... and the fallback when the guard fails
            "ls | xargs rm -rf $OUT",  # in a pipe
            "find . | rm -rf $OUT",
        ],
    )
    def test_a_guard_that_would_change_control_flow_is_refused(self, index, command):
        decision = decide(index, command)
        assert decision.action is not DecisionAction.MODIFY, command
        assert "Safer form" not in decision.reason

    def test_other_serious_findings_mean_review_with_a_suggestion(self, index):
        decision = decide(index, "rm -rf $OUT && git push --force origin main")
        assert decision.action is DecisionAction.REQUEST_REVIEW
        assert decision.signoff_required
        assert 'Safer form: `[ -n "$OUT" ] && rm -rf "$OUT" && git push --force origin main`' in (
            decision.reason
        )


class TestTheRewriteThatRemains:
    def test_plain_unset_variable_is_still_rewritten(self, index):
        decision = decide(index, "rm -rf $BUILD_DIR/artifacts")
        assert decision.action is DecisionAction.MODIFY
        assert decision.updated_arguments == {
            "command": '[ -n "$BUILD_DIR" ] && rm -rf "$BUILD_DIR"/artifacts'
        }

    def test_modify_reason_carries_guarded_form(self, index):
        decision = decide(index, "rm -rf $OUT_DIR")
        guarded = '[ -n "$OUT_DIR" ] && rm -rf "$OUT_DIR"'
        assert decision.updated_arguments["command"] == guarded
        assert guarded in decision.reason
        assert guarded in decision.additional_context
        assert "narrowed" in decision.reason

    def test_codex_renders_the_guarded_form(self, session):
        session.prompt("Clean the build output.")
        out = session.codex_bash("rm -rf $BUILD_DIR")
        assert permission(out) == "deny"
        assert '[ -n "$BUILD_DIR" ] && rm -rf "$BUILD_DIR"' in reason(out)
        assert not reason(out).startswith(codex_render.SIGN_OFF)
        # and Claude Code gets the rewrite in its permission prompt
        claude = session.claude("Bash", command="rm -rf $BUILD_DIR")["hookSpecificOutput"]
        assert claude["permissionDecision"] == "ask"
        assert claude["updatedInput"]["command"] == '[ -n "$BUILD_DIR" ] && rm -rf "$BUILD_DIR"'

    @pytest.mark.skipif(BASH is None, reason="bash is the oracle")
    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf $OUT",
            "rm -rf ${OUT}/dist",
            'rm -rf "$OUT"',
            "rm -rf $OUT/*",
            "cd build && rm -rf $OUT 2>/dev/null # tidy",
            "sudo rm -rf $CACHE",
            "rm -rf $OUT/a; rm -rf $OUT/b",
        ],
    )
    def test_every_rewrite_still_parses(self, index, command):
        assert parses(command)
        decision = decide(index, command)
        assert decision.action is DecisionAction.MODIFY, command
        rewritten = decision.updated_arguments["command"]
        assert parses(rewritten), rewritten

    @pytest.mark.skipif(BASH is None, reason="bash is the oracle")
    @pytest.mark.parametrize(
        "command", ["rm -rf $A $B/", "rm -rf $OUT && git push --force origin main", "rm -rf $X $Y"]
    )
    def test_every_suggestion_parses(self, index, command):
        decision = decide(index, command)
        suggestion = decision.reason.split("Safer form: `", 1)[1][:-1]
        assert parses(suggestion), suggestion
