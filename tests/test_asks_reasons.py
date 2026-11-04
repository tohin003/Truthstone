"""A10: reasons the recipient can act on (IMPROVEMENTS.md A10, section 4.5).

* A review request is read by the developer, in their own permission prompt. It carried
  the agent's header ("AgentGuard — evidence check") and an agent's closing ("Confirm
  this against the repository") (D2 R5).
* Challenges asked the agent to "explain" or "say so", but nothing reads the reply. The
  only override that works — re-issuing the same action, which the ledger then allows —
  was never stated (D2 R1).
* A requested `uv add httpx` was told to "add it to the project manifest"; text in a PR
  body was challenged as an install (D2 R2).
"""

from __future__ import annotations

import pytest

from agentguard.challenge import render
from agentguard.challenge.renderer import OVERRIDE, REVIEW_HEADER
from agentguard.core.enums import ChallengeCategory, DecisionAction, FailureMode, Severity, Verdict
from agentguard.core.models import Finding
from agentguard.validate.validator import AD_HOC_INSTALL
from tests.test_asks_support import HALLUCINATION, Session, make_guard, make_repo, permission, reason

AGENT_CLOSING = "Confirm this against the repository"


@pytest.fixture
def session(tmp_path):
    repo = make_repo(tmp_path)
    guard = make_guard(repo)
    yield Session(guard, repo)
    guard.close()


def risk(summary: str = "Irreversible command: force push") -> Finding:
    return Finding(
        category=ChallengeCategory.RISK,
        verdict=Verdict.REQUIRES_HUMAN,
        failure_mode=FailureMode.DESTRUCTIVE_ACTION,
        severity=Severity.HIGH,
        summary=summary,
    )


class TestTheReviewIsForTheDeveloper:
    def test_review_text_addresses_the_human(self, session):
        session.prompt("Squash my last three commits and update the remote branch.")
        decision = session.pre("Bash", command="git push --force origin main")
        assert decision.action is DecisionAction.REQUEST_REVIEW
        assert decision.reason.startswith(REVIEW_HEADER)
        assert AGENT_CLOSING not in decision.reason
        assert OVERRIDE not in decision.reason, "an ask is asked every time: no override exists"

        out = session.claude("Bash", command="git push --force origin main")
        assert permission(out) == "ask"
        assert reason(out).startswith(REVIEW_HEADER)

    def test_a_suggestion_still_follows_the_review(self, session):
        session.prompt("Clean the build outputs.")
        decision = session.pre("Bash", command="rm -rf $A $B/")
        assert decision.reason.startswith(REVIEW_HEADER)
        assert "Safer form:" in decision.reason

    def test_render_by_audience(self):
        human = render([risk()], audience="human")
        agent = render([risk()])
        assert human.startswith(REVIEW_HEADER) and AGENT_CLOSING not in human and OVERRIDE not in human
        assert agent.startswith("AgentGuard — evidence check") and agent.endswith(OVERRIDE)


class TestTheAgentIsToldTheRealOverride:
    def test_challenge_states_the_override(self, session):
        session.prompt("Add an active-users report.")
        write = {"file_path": "src/shop/api/report.py", "content": HALLUCINATION.format(member="active")}
        decision = session.pre("Write", **write)
        assert decision.action is DecisionAction.CHALLENGE
        assert decision.reason.endswith(OVERRIDE)

        # And the override is true: the identical action is not challenged again.
        assert session.pre("Write", **write).action is DecisionAction.ALLOW
        assert session.claude("Write", **write) == {}

    def test_both_hosts_carry_it(self, session):
        session.prompt("Add a cache client.")
        claude = session.claude("Bash", command="pip install memcache-client")
        assert permission(claude) == "deny" and OVERRIDE in reason(claude)
        codex = session.codex_bash("pip install pymemcache-client")
        assert permission(codex) == "deny" and OVERRIDE in reason(codex)


class TestDependencyReasons:
    def test_requested_dependency_not_challenged(self, session):
        session.prompt("Add httpx as a dependency and use it in a new client to call the rates API.")
        for command in ["uv add httpx", "pip install httpx", "poetry add HTTPX", "npm install httpx"]:
            decision = session.pre("Bash", command=command)
            assert decision.action is DecisionAction.ALLOW, command
            assert not any(f.category is ChallengeCategory.DEPENDENCY for f in decision.findings), command

    def test_a_package_the_prompt_does_not_name_is_still_challenged(self, session):
        session.prompt("Add httpx as a dependency and use it to call the rates API.")
        manifest = session.pre("Bash", command="uv add aiocache")
        assert manifest.action is DecisionAction.CHALLENGE
        assert "manifest" not in manifest.reason.lower(), "uv add already writes the manifest"

        ad_hoc = session.pre("Bash", command="pip install cachetools")
        assert ad_hoc.action is DecisionAction.CHALLENGE
        assert AD_HOC_INSTALL in ad_hoc.reason

    @pytest.mark.parametrize(
        ("prompt", "command", "requested"),
        [
            ("Use python-dateutil to parse the dates.", "pip install python_dateutil", True),
            ("Add the @types/node typings.", "npm i -D @types/node", True),
            ("Add the @types/node typings.", "npm i -D node", False),
            ("Switch to requests-oauthlib.", "pip install requests", False),
            ("Add httpx.", "uv add httpx", True),
        ],
    )
    def test_naming_is_by_package_not_by_substring(self, session, prompt, command, requested):
        session.prompt(prompt)
        decision = session.pre("Bash", command=command)
        challenged = any(f.category is ChallengeCategory.DEPENDENCY for f in decision.findings)
        assert challenged is not requested, (prompt, command)

    def test_install_text_in_pr_body_ignored(self, session):
        session.prompt("Open a PR for the shop client.")
        for command in [
            'gh pr create --title "Add rates client" --body "Run: pip install shop-client"',
            'git commit -m "docs: tell users to npm install shop-client first"',
            "echo 'pip install shop-client' >> README.md",
        ]:
            decision = session.pre("Bash", command=command)
            assert not any(f.category is ChallengeCategory.DEPENDENCY for f in decision.findings), command
            assert session.claude("Bash", command=command) == {}, command
