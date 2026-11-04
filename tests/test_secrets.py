"""A11: secrets in newly written content (IMPROVEMENTS.md A11).

GitGuardian's 2026 report puts secrets in Claude Code-assisted commits at about 3.2%,
against a 1.5% baseline. A strict credential format newly written into a file git does
not ignore is challenged once (HIGH, SECRET_EXPOSURE), with the value masked. A key in an
ignored `.env` belongs there; placeholders are not keys.

Every key below is generated at test time from split prefixes, so this file never holds a
string with a credential's shape — a push-side secret scanner has nothing to find here.
"""

from __future__ import annotations

import logging
import random
import string
import time

import pytest

from agentguard.core.enums import DecisionAction, FailureMode, Severity
from agentguard.validate import secrets
from tests.test_asks_support import Session, make_guard, make_repo, permission, reason

ALNUM = string.ascii_letters + string.digits


def fake(prefix: str, length: int, alphabet: str = ALNUM, seed: int = 11) -> str:
    rng = random.Random(f"{prefix}{length}{seed}")
    return prefix + "".join(rng.choice(alphabet) for _ in range(length))


KEYS = {
    "aws": fake("AK" + "IA", 16, string.ascii_uppercase + string.digits),
    "pem": "-----BEGIN RSA " + "PRIVATE KEY-----",
    "github": fake("gh" + "p_", 36),
    "github_pat": fake("github" + "_pat_", 82, ALNUM + "_"),
    "slack": "xo" + "xb-" + fake("", 12, string.digits) + "-" + fake("", 24),
    "stripe": fake("sk" + "_live_", 24),
    "anthropic": fake("sk-" + "ant-api03-", 80, ALNUM + "-_"),
    "openai": fake("sk-" + "proj-", 48, ALNUM + "-_"),
    "google": fake("AI" + "za", 35, ALNUM + "-_"),
}

PLACEHOLDERS = [
    "AK" + "IA" + "IOSFODNN7" + "EXAMPLE",  # AWS's documented example key id
    "gh" + "p_" + "x" * 36,
    "sk-" + "proj-" + "your_key_here_" + "a" * 10,
    "AI" + "za" + "0" * 35,
    "sk" + "_live_" + "X" * 24,
    "sk-" + "ant-" + "REDACTED-REDACTED-REDACTED",
]


@pytest.fixture
def session(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".gitignore").write_text(".env\n*.secret.toml\n")
    guard = make_guard(repo)
    yield Session(guard, repo)
    guard.close()


def secret_findings(decision):
    return [f for f in decision.findings if f.failure_mode is FailureMode.SECRET_EXPOSURE]


class TestScan:
    @pytest.mark.parametrize("kind", sorted(KEYS))
    def test_each_strict_format_is_recognised(self, kind):
        hits = secrets.scan(f'API = "{KEYS[kind]}"\n')
        assert len(hits) == 1, kind

    @pytest.mark.parametrize("value", PLACEHOLDERS)
    def test_placeholders_are_not_keys(self, value):
        assert secrets.scan(f"KEY={value}\n") == []

    @pytest.mark.parametrize(
        "text",
        [
            "sk-1234",  # too short to be anything
            "token = os.environ['GITHUB_TOKEN']",
            "AKIA is the prefix of an AWS access key id",
            "-----BEGIN PUBLIC KEY-----",
            "-----BEGIN CERTIFICATE-----",
        ],
    )
    def test_ordinary_text_is_not_a_key(self, text):
        assert secrets.scan(text) == []

    def test_only_new_lines_are_read(self):
        before = f"OLD = '{KEYS['github']}'\nx = 1\n"
        added, _ = secrets.new_lines(before, before + "y = 2\n")
        assert secrets.scan(added) == []

    def test_scan_latency(self):
        """D1 measured 0.62 ms on 131 KiB of new text. Recorded with a loose bound."""
        text = ("x = compute(alpha, beta) + gamma  # a typical line of code\n" * 2300)[: 131 * 1024]
        began = time.perf_counter()
        for _ in range(5):
            secrets.scan(text)
        assert (time.perf_counter() - began) / 5 < 0.05


class TestThroughTheGuard:
    @pytest.mark.parametrize("kind", sorted(KEYS))
    def test_key_in_tracked_source_is_challenged(self, session, kind):
        session.prompt("Wire the payments client.")
        args = {"file_path": "src/shop/settings.py", "content": f'KEY = "{KEYS[kind]}"\n'}
        decision = session.pre("Write", **args)
        assert decision.action is DecisionAction.CHALLENGE, kind
        found = secret_findings(decision)
        assert found and found[0].severity is Severity.HIGH
        assert permission(session.claude("Write", **{**args, "file_path": "src/shop/other.py"})) == "deny"

    def test_edits_and_patches_are_read_too(self, session):
        session.prompt("Wire the client.")
        edit = session.pre(
            "Edit",
            file_path="src/shop/models.py",
            old_string="",
            new_string=f"\nTOKEN = '{KEYS['github']}'\n",
        )
        assert secret_findings(edit) and edit.action is DecisionAction.CHALLENGE
        multi = session.pre(
            "MultiEdit",
            file_path="src/shop/api/users.py",
            edits=[{"old_string": "", "new_string": f"\nKEY = '{KEYS['stripe']}'\n"}],
        )
        assert secret_findings(multi)
        patch = (
            "*** Begin Patch\n*** Add File: src/shop/keys.py\n"
            f"+GOOGLE = '{KEYS['google']}'\n*** End Patch"
        )
        out = session.codex(
            "PreToolUse", tool_name="apply_patch", tool_input={"command": patch}, tool_use_id="c"
        )
        assert permission(out) == "deny" and "Google API key" in reason(out)

    def test_key_in_gitignored_env_is_silent(self, session):
        session.prompt("Configure the local environment.")
        for path in [".env", "config/prod.secret.toml"]:
            decision = session.pre("Write", file_path=path, content=f"OPENAI_API_KEY={KEYS['openai']}\n")
            assert not secret_findings(decision), path
            assert decision.action is DecisionAction.ALLOW
            assert session.claude("Write", file_path=path, content=f"K={KEYS['aws']}\n") == {}

    def test_placeholder_is_silent(self, session):
        session.prompt("Document the configuration.")
        for value in PLACEHOLDERS:
            decision = session.pre("Write", file_path="docs/config.md", content=f"KEY={value}\n")
            assert not secret_findings(decision), value

    def test_secret_is_masked_in_message(self, session):
        session.prompt("Wire the client.")
        key = KEYS["anthropic"]
        decision = session.pre("Write", file_path="src/shop/llm.py", content=f'KEY = "{key}"\n')
        assert decision.action is DecisionAction.CHALLENGE
        stored = [decision.reason]
        for finding in decision.findings:
            stored += [finding.subject, finding.summary, finding.detail]
            stored += [ref.render() for ref in finding.evidence]
        assert all(key not in text and key[12:40] not in text for text in stored)
        assert "characters hidden" in decision.reason and "sk-ant-" in decision.reason
        rows = session.workspace.store.recent_decisions(3)
        assert all(key not in (row["reason"] or "") for row in rows)
        claude = session.claude("Write", file_path="src/shop/llm2.py", content=f'KEY = "{key}"\n')
        assert key not in reason(claude)

    def test_a_key_already_in_the_file_is_not_this_edits_doing(self, session):
        target = session.repo / "src" / "shop" / "legacy.py"
        target.write_text(f"LEGACY = '{KEYS['github']}'\nVALUE = 1\n")
        session.prompt("Bump the value.")
        decision = session.pre(
            "Edit", file_path="src/shop/legacy.py", old_string="VALUE = 1", new_string="VALUE = 2"
        )
        assert not secret_findings(decision)

    def test_raised_once_per_credential(self, session):
        session.prompt("Wire the client.")
        args = {"file_path": "src/shop/settings.py", "content": f'KEY = "{KEYS["aws"]}"\n'}
        assert session.pre("Write", **args).action is DecisionAction.CHALLENGE
        again = session.pre("Write", **args)
        assert again.action is DecisionAction.ALLOW and secret_findings(again)


def test_unknown_ignore_status_fails_open_with_a_warning(tmp_path, caplog):
    """No git repository: whether the file is tracked cannot be known, so nothing is raised
    — and the log says why, so it is not silent."""
    workspace = tmp_path / "plain"
    (workspace / "src").mkdir(parents=True)
    guard = make_guard(workspace)
    try:
        session = Session(guard, workspace)
        session.prompt("Wire the client.")
        with caplog.at_level(logging.WARNING, logger="agentguard.validate.secrets"):
            decision = session.pre("Write", file_path="src/keys.py", content=f"K = '{KEYS['aws']}'\n")
        assert not secret_findings(decision)
        assert any("not raised" in record.getMessage() for record in caplog.records)
    finally:
        guard.close()
