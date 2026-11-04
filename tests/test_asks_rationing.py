"""A1: irreversible asks are never rationed or dropped (IMPROVEMENTS.md A1).

Review requests used to go through the challenge ledger, which silenced them three ways:
with no task, by deduplicating on the matched substring (a second, different `git reset
--hard` was silent), and by the advisory budget (after six challenges `rm -rf /` passed).
On Codex, whose sign-off is a deny, a plain re-run of a refused command then went through.

Truthstone cannot see whether the developer approved or refused, so it asks every time —
and an ask never spends the budget that agent-facing challenges share.
"""

from __future__ import annotations

import pytest

from tests.test_asks_support import HALLUCINATION, Session, make_guard, make_repo, permission, reason
from truthstone.adapters.codex import render as codex_render
from truthstone.challenge.ledger import ChallengeLedger
from truthstone.core.config import ChallengeSettings
from truthstone.core.enums import ChallengeCategory, DecisionAction, FailureMode, Severity, Verdict
from truthstone.core.models import Finding
from truthstone.core.store import ProjectStore


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path)


@pytest.fixture
def session(repo):
    guard = make_guard(repo)
    yield Session(guard, repo)
    guard.close()


def assert_codex_sign_off(out: dict) -> None:
    assert permission(out) == "deny"
    assert reason(out).startswith(codex_render.SIGN_OFF)


class TestAsksAreNeverRationed:
    def test_a_retried_irreversible_command_is_asked_again(self, session):
        session.prompt("Squash my last three commits and update the remote branch.")

        # Claude Code: the developer's own permission prompt, every time.
        for _ in range(3):
            assert permission(session.claude("Bash", command="git push --force origin main")) == "ask"
        # A different target of the same concern is not swallowed by substring dedupe.
        for target in ("HEAD~1", "origin/main", "HEAD~1"):
            assert permission(session.claude("Bash", command=f"git reset --hard {target}")) == "ask"

        # Codex has no ask: the sign-off is a deny, so a plain re-run must be denied again
        # rather than run.
        for _ in range(3):
            assert_codex_sign_off(session.codex_bash("git push --force origin main"))

    def test_challenge_budget_never_silences_an_irreversible_command(self, session):
        session.prompt("Add an active-users report.")
        budget = ChallengeSettings().max_per_task
        for i in range(budget):
            decision = session.pre(
                "Write",
                file_path=f"src/shop/api/report_{i}.py",
                content=HALLUCINATION.format(member=f"get_active_users_{i}"),
            )
            assert decision.action is DecisionAction.CHALLENGE, i
        spent = session.pre(
            "Write",
            file_path="src/shop/api/report_last.py",
            content=HALLUCINATION.format(member="get_active_users_last"),
        )
        assert spent.action is DecisionAction.ALLOW and "budget" in spent.reason

        decision = session.pre("Bash", command="rm -rf /")
        assert decision.action is DecisionAction.REQUEST_REVIEW
        assert decision.signoff_required
        assert permission(session.claude("Bash", command="rm -rf /")) == "ask"
        assert_codex_sign_off(session.codex_bash("rm -rf /"))

    def test_no_task_still_asks(self, session):
        """Before the first prompt there is no task. The ask must not depend on one."""
        assert session.task_id is None
        decision = session.pre("Bash", command="git reset --hard HEAD~3")
        assert decision.action is DecisionAction.REQUEST_REVIEW
        assert decision.signoff_required
        assert permission(session.claude("Bash", command="git reset --hard HEAD~3")) == "ask"
        assert_codex_sign_off(session.codex_bash("git reset --hard HEAD~3"))

    def test_review_requests_do_not_spend_the_advisory_budget(self, session):
        session.prompt("Tidy the repository and publish it.")
        task_id = session.task_id
        for command in ["rm -rf /", "git push --force origin main", "git reset --hard"] * 4:
            assert session.pre("Bash", command=command).action is DecisionAction.REQUEST_REVIEW

        store = session.workspace.store
        assert store.challenge_count(task_id) == 0, "an ask was charged to the advisory budget"

        # The whole budget is still there for agent-facing challenges.
        for i in range(ChallengeSettings().max_per_task):
            decision = session.pre(
                "Write",
                file_path=f"src/shop/api/report_{i}.py",
                content=HALLUCINATION.format(member=f"get_active_users_{i}"),
            )
            assert decision.action is DecisionAction.CHALLENGE, i

    def test_the_ask_is_still_recorded_for_the_log(self, session):
        session.prompt("Publish the branch.")
        decision = session.pre("Bash", command="git push --force origin main")
        rows = session.workspace.store.recent_decisions(5)
        assert any(row["action"] == "request_review" for row in rows)
        assert decision.findings and decision.findings[0].failure_mode is FailureMode.DESTRUCTIVE_ACTION


class TestTheLedgerNeverRationsAReviewRequest:
    """Defence in depth: the rule also holds for any caller of the ledger."""

    @pytest.fixture
    def ledger(self, tmp_path):
        return ChallengeLedger(ProjectStore.for_workspace(tmp_path), ChallengeSettings(max_per_task=1))

    @staticmethod
    def ask(subject: str = "git push --force") -> Finding:
        return Finding(
            category=ChallengeCategory.RISK,
            verdict=Verdict.REQUIRES_HUMAN,
            failure_mode=FailureMode.DESTRUCTIVE_ACTION,
            severity=Severity.HIGH,
            subject=subject,
        )

    @staticmethod
    def challenge(subject: str) -> Finding:
        return Finding(
            category=ChallengeCategory.EVIDENCE,
            verdict=Verdict.CONTRADICTED,
            failure_mode=FailureMode.HALLUCINATED_API,
            severity=Severity.HIGH,
            subject=subject,
        )

    def test_asks_pass_without_a_task(self, ledger):
        assert ledger.admit(None, [self.ask()]).raise_now == [self.ask()]

    def test_asks_pass_repeatedly_and_are_never_charged(self, ledger):
        for _ in range(3):
            verdict = ledger.admit("t", [self.ask()])
            assert verdict.raise_now == [self.ask()]
            ledger.record("t", verdict.raise_now)
        assert ledger.store.challenge_count("t") == 0

    def test_asks_pass_a_spent_budget(self, ledger):
        first = ledger.admit("t", [self.challenge("A.x")])
        ledger.record("t", first.raise_now)
        spent = ledger.admit("t", [self.challenge("A.y"), self.ask()])
        assert spent.raise_now == [self.ask()]
        assert "budget" in spent.reason
