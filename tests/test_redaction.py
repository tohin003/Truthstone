"""Secrets never reach the database (R17).

Before: prompts (2,000 chars, kept 270 days), tool-argument strings, verification
details and finding text were stored verbatim (x_secrets.py). Every credential below is
fake: generated strings in the documented shapes.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

import pytest

from agentguard.adapters.claude_code import translate as claude
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import ChallengeCategory, DecisionAction, FailureMode, Severity, Verdict
from agentguard.core.models import Decision, EvidenceRef, Finding
from agentguard.core.store import REDACTED, ProjectStore, redact_secrets, summarize_value

FIXTURES = Path(__file__).parent / "fixtures"

ANTHROPIC = "sk-ant-api03-" + "Fa1KeAnthropicKey0123456789abcdefghijklmnopqrstuv"
OPENAI_PROJECT = "sk-proj-" + "FAKEopenaiProjectKey0123456789ABCDEFGHIJ"
OPENAI = "sk-" + "FAKElegacyOpenAIkey0123456789abcdefghijklmnop"
GITHUB_CLASSIC = "ghp_" + "FAKEgithubToken0123456789abcdefghijk"
GITHUB_FINE = "github_pat_" + "11FAKEFINE0123456789_abcdefghijklmnopqrstuvwxyz0123456789ABCD"
AWS = "AKIA" + "FAKE0123456789AB"
SLACK = "xoxb-" + "123456789012-1234567890123-FAKEslackTokenValue0"
GOOGLE = "AIza" + "SyFAKEgoogleApiKey0123456789abcdefg"
BEARER = "FAKEbearer.eyJzdWIiOiJmYWtlIn0.c2lnbmF0dXJl"
PASSWORD = "hunter2-FAKE-pw"
PASSWD = "FAKEpasswd99"
SECRET = "FAKEsecretValue42"
TOKEN = "FAKEtokenValue77"
URL_PASSWORD = "FAKEurlPassw0rd"
PEM_BODY = "MIIEFAKEowIBAAKCAQEAfakeRSAkeyMaterial0123456789abcdefFAKE"
PEM = f"-----BEGIN RSA PRIVATE KEY-----\n{PEM_BODY}\n{PEM_BODY}\n-----END RSA PRIVATE KEY-----"

SECRETS = (
    ANTHROPIC, OPENAI_PROJECT, OPENAI, GITHUB_CLASSIC, GITHUB_FINE, AWS, SLACK, GOOGLE,
    BEARER, PASSWORD, PASSWD, SECRET, TOKEN, URL_PASSWORD, PEM_BODY,
)

# One text carrying every shape, the way agents actually meet them.
EVERYTHING = "\n".join(
    [
        f"ANTHROPIC_API_KEY={ANTHROPIC}",
        f"export OPENAI_API_KEY='{OPENAI_PROJECT}'",
        f"legacy key {OPENAI} in prose",
        f"git push https://{GITHUB_CLASSIC}@github.com/acme/repo.git",
        f'gh auth login --with-token <<< "{GITHUB_FINE}"',
        f"aws_access_key_id = {AWS}",
        f"SLACK_BOT={SLACK}",
        f"https://maps.example.invalid/api?key={GOOGLE}",
        f'curl -H "Authorization: Bearer {BEARER}" https://api.example.invalid',
        f"DB_PASSWORD={PASSWORD}",
        f"passwd={PASSWD}",
        f'{{"client_secret": "{SECRET}"}}',
        f"token={TOKEN}",
        f"psql postgres://admin:{URL_PASSWORD}@db.example.invalid/prod",
        PEM,
    ]
)


def _assert_clean(text: str) -> None:
    leaked = [secret for secret in SECRETS if secret in text]
    assert not leaked, f"credentials survived redaction: {leaked}"


class TestRedactSecrets:
    def test_every_shape_is_redacted(self):
        out = redact_secrets(EVERYTHING)
        _assert_clean(out)
        assert out.count(REDACTED) >= 14
        assert "[REDACTED PRIVATE KEY]" in out

    @pytest.mark.parametrize(
        ("text", "kept"),
        [
            (f"Authorization: Bearer {BEARER}", "Authorization: Bearer "),
            (f"{ANTHROPIC}", "sk-"),
            (f"ANTHROPIC_API_KEY={ANTHROPIC}", "ANTHROPIC_API_KEY=sk-"),
            (f"{GITHUB_CLASSIC}", "ghp_"),
            (f"{AWS}", "AKIA"),
            (f"https://bob:{URL_PASSWORD}@example.invalid", "https://bob:"),
            (f"DB_PASSWORD={PASSWORD}", "DB_PASSWORD="),
            (f'"password": "{PASSWORD}"', '"password": "'),
        ],
    )
    def test_the_kind_of_credential_stays_readable(self, text, kept):
        out = redact_secrets(text)
        assert out.startswith(kept)
        assert REDACTED in out

    def test_a_password_in_prose_is_redacted(self):
        out = redact_secrets(f"deploy it, the db password is {PASSWORD} and the user is admin")
        assert PASSWORD not in out
        assert "the user is admin" in out

    def test_a_truncated_private_key_is_still_redacted(self):
        assert PEM_BODY not in redact_secrets(PEM[:80])

    @pytest.mark.parametrize(
        "text",
        [
            "add a password reset flow and a password manager link",
            "max_tokens=4096",
            "tokenizer = AutoTokenizer.from_pretrained(name)",
            "def check(password: str) -> bool:",
            "the task-runner-configuration-service and disk-usage-monitor-daemon",
            "sk-learn",
            "if secret == other_secret:",
            "Bearer",
            "https://example.com:8080/path",
            "result = cache.get(key)",
        ],
    )
    def test_ordinary_code_and_prose_are_left_alone(self, text):
        assert redact_secrets(text) == text

    def test_redaction_is_idempotent(self):
        once = redact_secrets(EVERYTHING)
        assert redact_secrets(once) == once

    def test_secret_straddling_the_column_limit_is_removed_whole(self):
        # The key starts at 191 of a 200-char column: cutting first would keep "sk-ant-ap".
        summarised = summarize_value("x" * 190 + f" {ANTHROPIC}")
        assert "sk-ant" not in summarised
        assert summarised.startswith("x" * 190 + " sk-[REDAC")

    def test_task_spec_is_scrubbed_of_secrets_found_in_the_prompt(self, workspace):
        store = ProjectStore.for_workspace(workspace)
        prompt = f'curl -H "Authorization: Bearer {BEARER}" and DB_PASSWORD={PASSWORD}'
        # Intent extraction keeps bare fragments, out of the context that marks them.
        spec = {"prompt": prompt, "targets": [{"token": BEARER}, {"token": PASSWORD}], "goal": "deploy"}
        task_id = store.create_task("s1", prompt, spec=spec)
        row = store.db.query("SELECT prompt, spec FROM tasks WHERE id=?", (task_id,))[0]
        _assert_clean(row["prompt"] + row["spec"])
        assert '"goal": "deploy"' in row["spec"]

    @pytest.mark.parametrize(
        "text",
        [
            ("a." * 40_000)[:65_533] + "://",
            "http://" + "a" * 32_000 + ":" + "b" * 32_000,
            "password " * 7_000,
            "sk-" * 21_000,
            "token=" * 10_000,
            "-----BEGIN " * 5_900,
            EVERYTHING * 40,
        ],
    )
    def test_cost_is_bounded_on_64kb(self, text):
        text = text[: 64 * 1024]
        started = time.perf_counter()
        redact_secrets(text)
        # Measured at 0.3-5.7 ms; the bound is loose for slow CI machines.
        assert time.perf_counter() - started < 0.25


def _all_text(db_path: Path) -> str:
    """Every column of every row, plus the raw database and WAL bytes."""
    con = sqlite3.connect(str(db_path))
    chunks = []
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            for row in con.execute(f"SELECT * FROM {table}"):
                chunks.extend(str(value) for value in row)
    finally:
        con.close()
    for suffix in ("", "-wal"):
        raw = Path(f"{db_path}{suffix}")
        if raw.exists():
            chunks.append(raw.read_bytes().decode("latin-1"))
    return "\n".join(chunks)


def test_fake_credentials_are_never_persisted(tmp_path):
    repo = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", repo)

    def event(name: str, **extra):
        payload = {
            "session_id": "sec",
            "transcript_path": "/t",
            "cwd": str(repo),
            "permission_mode": "default",
            "hook_event_name": name,
            **extra,
        }
        return claude.to_event(payload)

    guard = Guard(Settings())
    try:
        ws = guard.workspace(repo)
        assert ws.index.ready(timeout=30)
        guard.handle(event("SessionStart", source="startup"))
        # The prompt: tasks.prompt and tasks.spec (which carries the prompt again).
        guard.handle(event("UserPromptSubmit", prompt=f"Deploy with these credentials:\n{EVERYTHING}"))
        # Tool arguments: events.arguments. One command per credential line, the private
        # key whole (a lone base64 line out of a PEM block is not recognisable as one).
        commands = [line for line in EVERYTHING.splitlines() if PEM_BODY not in line and "-----" not in line]
        commands.append(f"printf '%s' '{PEM}' > deploy.pem")
        for command in commands:
            guard.handle(event("PreToolUse", tool_name="Bash", tool_input={"command": command}))
        guard.handle(
            event(
                "PreToolUse",
                tool_name="Write",
                tool_input={"file_path": str(repo / ".env"), "content": EVERYTHING},
            )
        )
        # A failing test run quoting a token: verifications.detail.
        guard.handle(
            event(
                "PostToolUse",
                tool_name="Bash",
                tool_input={"command": "pytest -q"},
                tool_response={
                    "stdout": f"FAILED test_x - AssertionError: token {ANTHROPIC}\n1 failed",
                    "stderr": "",
                    "interrupted": False,
                },
            )
        )
        task_id = ws.store.current_task_id("sec")
        assert task_id

        # Finding text, decision reasons, challenge subjects, metrics, memory: direct.
        store: ProjectStore = ws.store
        finding = Finding(
            category=ChallengeCategory.EVIDENCE,
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            failure_mode=FailureMode.HALLUCINATED_API,
            severity=Severity.HIGH,
            subject=f"curl -H 'Authorization: Bearer {BEARER}'",
            summary=f"uses {GITHUB_CLASSIC}",
            detail=EVERYTHING,
            evidence=[EvidenceRef(source="bash", path=".env", symbol=f"DB_PASSWORD={PASSWORD}")],
        )
        decision = Decision(action=DecisionAction.CHALLENGE, reason=EVERYTHING, findings=[finding])
        assert store.record_event_and_decision(event("PreToolUse", tool_name="Bash"), decision)
        assert store.record_decision(event("PreToolUse", tool_name="Bash"), decision)
        store.record_challenge(task_id, "fp", f"token={TOKEN}")
        store.record_metric("m", 1.0, {"cmd": f"export SECRET={SECRET}"})
        store.remember("note", EVERYTHING, source=f"Bearer {BEARER}", source_files=[f"{AWS}.txt"])
        store.open_session("sec-2", "claude-code", meta={"auth": f"Bearer {BEARER}"})
        store.finish_verification(store.start_verification(task_id, "pytest"), "failed", {"out": EVERYTHING})
    finally:
        guard.close()

    stored = _all_text(Path(store.db.path))
    _assert_clean(stored)
    assert REDACTED in stored
    # The prompt is still useful: the redaction removed values, not the record.
    prompt = sqlite3.connect(str(store.db.path)).execute("SELECT prompt FROM tasks").fetchone()[0]
    assert prompt.startswith("Deploy with these credentials:")
    assert "ANTHROPIC_API_KEY=sk-[REDACTED]" in prompt
