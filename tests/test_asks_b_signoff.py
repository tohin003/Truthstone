"""A1b: developer sign-off the agent cannot give itself (IMPROVEMENTS.md A1, §8).

A1 rightly asks about an irreversible action every time. On Codex, whose `ask` fails open,
the sign-off is a deny telling the agent to "ask the user to confirm, then re-run" — and
the re-run was denied again, every time. The instruction was false: a Codex agent could
never run an irreversible command, even after the developer said yes.

Now each held action carries a code bound to the session and the exact action. The
developer allows it once — a reply whose first line is `approve <CODE>`, or `agentguard
approve <CODE>` in a terminal — and the next attempt at exactly that action runs; the one
after is held again. No usable store means no grant: the one place AgentGuard fails closed.

Every behaviour is pinned through the real Guard and the real adapters (Codex through
`handle_payload`, its output checked against Codex's schema), because what reaches the
host is the property that matters.
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentguard.adapters.codex import render as codex_render
from agentguard.cli.main import app
from agentguard.core import hosts
from agentguard.core.enums import DecisionAction, EventType, FailureMode
from agentguard.core.events import AgentEvent
from agentguard.core.models import SIGNOFF_TTL_S, Decision
from agentguard.core.store import Database, ProjectStore
from agentguard.validate import checks, signoff
from tests.test_asks_support import Session, make_guard, make_repo, permission, reason
from tests.test_codex_translate import handle, load

FORCE_PUSH = "git push --force origin main"
RESET = "git reset --hard HEAD~1"


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path)


@pytest.fixture
def guard(repo):
    g = make_guard(repo)
    yield g
    g.close()


@pytest.fixture
def session(guard, repo):
    return Session(guard, repo, "sess-signoff")


def held(out: dict) -> bool:
    """A Codex sign-off deny: the action did not run."""
    return permission(out) == "deny" and reason(out).startswith(codex_render.SIGN_OFF)


def code_in(out: dict) -> str:
    """The code a Codex sign-off deny tells the agent the developer can approve."""
    match = re.search(r"reply `approve ([0-9A-Z]{6})`", reason(out))
    assert match, reason(out)
    return match.group(1)


def reply(session: Session, text: str) -> dict:
    return session.codex("UserPromptSubmit", prompt=text)


# -- the behaviour the user asked for -------------------------------------------------------


def test_signoff_reply_allows_exactly_one_rerun(session):
    reply(session, "Publish the branch, even if it rewrites the remote history.")
    first = session.codex_bash(FORCE_PUSH)
    assert held(first)
    code = code_in(first)
    assert "`agentguard approve " + code + "`" in reason(first), "both ways to grant are named"
    # The developer is told directly too, where a system message reaches them.
    assert f"reply `approve {code}`" in first["systemMessage"]

    reply(session, f"approve {code}")
    assert session.codex_bash(FORCE_PUSH) == {}, "signed off: this run goes through"

    third = session.codex_bash(FORCE_PUSH)
    assert held(third), "one sign-off, one run"
    assert code_in(third) == code, "asked again under the code the developer already saw"

    # The approved run is on the record, with the finding the census counts.
    rows = session.workspace.store.recent_decisions(10)
    approved = [r for r in rows if r["action"] == "allow" and code in r["reason"]]
    assert approved and "through a reply in the session" in approved[0]["reason"]


def test_signoff_code_is_bound_to_the_exact_command(guard, repo, session):
    reply(session, "Reset the branch.")
    one = code_in(session.codex_bash("git reset --hard HEAD~1"))
    two = code_in(session.codex_bash("git reset --hard HEAD~2"))
    assert one != two, "a different target is a different action"
    assert code_in(session.codex_bash("git  reset   --hard HEAD~1")) == one, "spacing is not"

    reply(session, f"approve {one}")
    assert held(session.codex_bash("git reset --hard HEAD~2")), "a grant never transfers"
    other = Session(guard, repo, "sess-other")
    assert held(other.codex_bash("git reset --hard HEAD~1")), "nor to another session"
    assert code_in(other.codex_bash("git reset --hard HEAD~1")) != one
    assert session.codex_bash("git reset --hard HEAD~1") == {}


@pytest.mark.parametrize(
    "template",
    [
        "what does approve {code} do?",
        "don't approve {code}",
        "Do not approve {code}.",
        "approve {code} but use --soft instead",
        "approve {code} before the release",
        "I'll approve {code} later",
        "Check the diff first.\napprove {code}",
        "Here is what you said: reply `approve {code}` to continue",
        "please approve {code}",
        "{code}",
        "approve",
    ],
)
def test_mentioning_a_code_does_not_grant(session, template):
    reply(session, "Reset the branch.")
    code = code_in(session.codex_bash(RESET))
    reply(session, template.format(code=code))
    assert held(session.codex_bash(RESET)), template


def test_a_reply_in_another_session_grants_nothing(guard, repo, session):
    reply(session, "Reset the branch.")
    code = code_in(session.codex_bash(RESET))
    reply(Session(guard, repo, "sess-elsewhere"), f"approve {code}")
    assert held(session.codex_bash(RESET))


def test_one_reply_can_sign_off_several_codes(session):
    reply(session, "Reset, then publish.")
    a = code_in(session.codex_bash(RESET))
    b = code_in(session.codex_bash(FORCE_PUSH))
    reply(session, f"Yes, approve {a.lower()} and {b}. Thanks")
    assert session.codex_bash(RESET) == {}
    assert session.codex_bash(FORCE_PUSH) == {}


@pytest.mark.parametrize(
    "command",
    [
        "agentguard approve {code}",
        "agentguard approve",
        "python -m agentguard.cli.main approve {code}",
        "uvx agentguard approve {code}",
        "cd /tmp && agentguard approve {code} --cwd {repo}",
        'codex exec resume --last "approve {code}"',
        "echo 'approve {code}' | codex exec resume --last -",
        "codex exec resume --last - < /tmp/reply.txt",
        "claude --resume abc -p go",
        "curl -s -d '{{\"hook_event_name\":\"UserPromptSubmit\",\"prompt\":\"approve {code}\"}}' "
        "http://127.0.0.1:1/hook/codex",
    ],
)
def test_agent_cannot_self_approve(session, command):
    reply(session, "Reset the branch.")
    code = code_in(session.codex_bash(RESET))
    command = command.format(code=code, repo=session.repo)

    decision = session.pre("Bash", command=command)
    assert decision.action is DecisionAction.REQUEST_REVIEW and decision.signoff_required, command
    assert any(f.failure_mode is FailureMode.VERIFICATION_TAMPERING for f in decision.findings)
    assert held(session.codex_bash(command))
    assert held(session.codex_bash(RESET)), "and nothing was granted"


def test_the_agents_route_needs_its_own_sign_off_which_only_the_developer_gives(session):
    """`agentguard approve` run by the agent is held under its own code; once the developer
    approves *that*, it may run — the developer has then signed off twice."""
    reply(session, "Reset the branch.")
    code = code_in(session.codex_bash(RESET))
    route = f"agentguard approve {code}"
    own = code_in(session.codex_bash(route))
    assert own != code
    reply(session, f"approve {own}")
    assert session.codex_bash(route) == {}


@pytest.mark.parametrize(
    "command",
    [
        "git log --grep approve",
        "echo approve change",
        "gh pr review 12 --approve",
        "agentguard log",
        'git commit -m "approve the release plan"',
    ],
)
def test_ordinary_mentions_of_approve_are_not_self_approval(session, command):
    reply(session, "Tidy up.")
    decision = session.pre("Bash", command=command)
    assert not [f for f in decision.findings if f.failure_mode is FailureMode.VERIFICATION_TAMPERING]


def test_cli_approve_grants_once(session, repo):
    reply(session, "Reset the branch.")
    code = code_in(session.codex_bash(RESET))
    runner = CliRunner()

    listed = runner.invoke(app, ["approve", "--cwd", str(repo)])
    assert listed.exit_code == 0 and code in listed.output and RESET in listed.output

    typed = code.lower().replace("0", "o").replace("1", "l")  # read aloud, retyped
    granted = runner.invoke(app, ["approve", typed, "--cwd", str(repo)])
    assert granted.exit_code == 0, granted.output
    assert f"{code} approved: {RESET}" in granted.output and "15 minutes" in granted.output

    assert session.codex_bash(RESET) == {}
    again = runner.invoke(app, ["approve", code, "--cwd", str(repo)])
    assert again.exit_code == 1 and "no sign-off request" in again.output, "a used code grants nothing"
    assert held(session.codex_bash(RESET))


def test_cli_approve_refuses_what_is_not_a_waiting_code(repo):
    runner = CliRunner()
    unknown = runner.invoke(app, ["approve", "K7M2QX", "--cwd", str(repo)])
    assert unknown.exit_code == 1 and "no sign-off request with code K7M2QX" in unknown.output
    junk = runner.invoke(app, ["approve", "yes", "--cwd", str(repo)])
    assert junk.exit_code == 1 and "is not a sign-off code" in junk.output
    empty = runner.invoke(app, ["approve", "--cwd", str(repo)])
    assert empty.exit_code == 0 and "no sign-off requests waiting" in empty.output


def test_expired_grant_is_ignored(session):
    reply(session, "Reset the branch.")
    code = code_in(session.codex_bash(RESET))
    reply(session, f"approve {code}")
    store = session.workspace.store
    stale = time.time() - SIGNOFF_TTL_S - 60
    store.db.write("UPDATE signoffs SET granted_at=? WHERE code=?", (stale, code))
    assert held(session.codex_bash(RESET)), "a grant older than the window is void"

    reply(session, f"approve {code}")  # the request is outstanding again; a fresh yes works
    fresh = time.time() - SIGNOFF_TTL_S + 60
    store.db.write("UPDATE signoffs SET granted_at=? WHERE code=?", (fresh, code))
    assert session.codex_bash(RESET) == {}


def test_degraded_store_fails_closed(session):
    reply(session, "Reset the branch.")
    code = code_in(session.codex_bash(RESET))
    reply(session, f"approve {code}")  # granted while storage worked
    session.workspace.store.db._degrade("test: the disk went away")

    out = session.codex_bash(RESET)
    assert held(out), "a grant that cannot be read was never given"
    lead = reason(out).split("\n\n", 1)[0]
    assert lead == hosts.SIGNOFF_WITHOUT_CODE, "no code is offered that could not be granted"
    decision = session.pre("Bash", command=RESET)
    assert decision.action is DecisionAction.REQUEST_REVIEW and decision.signoff_code is None
    reply(session, f"approve {code}")  # and a reply changes nothing
    assert held(session.codex_bash(RESET))


def test_a_busy_store_fails_closed(session, isolated_home):
    reply(session, "Reset the branch.")
    code = code_in(session.codex_bash(RESET))
    reply(session, f"approve {code}")
    other = sqlite3.connect(str(session.workspace.store.db.path), timeout=0)
    try:
        other.execute("BEGIN EXCLUSIVE")
        decision = session.pre("Bash", command=RESET)
        assert decision.action is DecisionAction.REQUEST_REVIEW and decision.signoff_code is None
    finally:
        other.rollback()
        other.close()
    assert session.codex_bash(RESET) == {}, "the grant survived the busy moment, unconsumed"


def test_settle_without_a_store_or_with_a_broken_one_holds(repo):
    event = AgentEvent(
        event=EventType.PRE_TOOL_USE, workspace=str(repo), session_id="s", tool="Bash",
        arguments={"command": RESET},
    )
    review = Decision(action=DecisionAction.REQUEST_REVIEW, reason="r", signoff_required=True)
    assert signoff.settle(event, None, review) == review

    class Broken:
        def signoff_settle(self, *args, **kwargs):
            raise RuntimeError("boom")

    assert signoff.settle(event, Broken(), review) == review


def test_claude_native_ask_unchanged(session):
    """On Claude Code the ask is the sign-off: no code is shown, nothing else changes."""
    session.prompt("Publish the branch.")
    decision = session.pre("Bash", command=FORCE_PUSH)
    assert decision.signoff_code, "recorded, so `agentguard approve` can list it"
    out = session.claude("Bash", command=FORCE_PUSH)
    assert permission(out) == "ask"
    assert reason(out) == decision.reason, "the reason is the core's, untouched"
    assert "approve" not in reason(out).lower() and "systemMessage" not in out


def test_codex_end_to_end_with_captured_payloads(guard, repo):
    """The captured `codex exec` payloads, re-pointed at a real repository: the prompt, a
    held command, the developer's reply, the one run, and the run after it."""
    session_id = load("UserPromptSubmit")["session_id"]

    def at(name: str, **fields) -> dict:
        return load(name, cwd=str(repo), session_id=session_id, **fields)

    assert "systemMessage" not in handle(guard, at("UserPromptSubmit", prompt="Publish my branch"))
    push = {"tool_name": "Bash", "tool_input": {"command": FORCE_PUSH}}
    first = handle(guard, at("PreToolUse.Bash.denied", **push))
    assert held(first)
    code = code_in(first)
    handle(guard, at("UserPromptSubmit", prompt=f"approve {code}"))
    assert handle(guard, at("PreToolUse.Bash.denied", **push)) == {}
    handle(guard, at("PostToolUse.Bash", **push, tool_response="Everything up-to-date\n"))
    assert held(handle(guard, at("PreToolUse.Bash.denied", **push)))


def test_a_file_sign_off_is_bound_to_the_file_not_the_hunks(guard, repo):
    """apply_patch splits into Edit or MultiEdit by its hunks; the developer approved
    changing that file. A different file, or deleting it, is a different action."""
    settings = repo / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text('{\n  "a": 1,\n  "b": 2\n}\n')
    session_id = "sess-patch"

    def patch(text: str) -> dict:
        return load(
            "PreToolUse.apply_patch.update_absolute", cwd=str(repo), session_id=session_id,
            tool_input={"command": text},
        )

    one_hunk = f'*** Begin Patch\n*** Update File: {settings}\n@@\n-  "a": 1,\n+  "a": 3,\n*** End Patch'
    two_hunks = (
        f'*** Begin Patch\n*** Update File: {settings}\n@@\n-  "a": 1,\n+  "a": 4,\n'
        '@@\n-  "b": 2\n+  "b": 5\n*** End Patch'
    )
    first = handle(guard, patch(one_hunk))
    assert held(first)
    code = code_in(first)
    assert code_in(handle(guard, patch(two_hunks))) == code
    handle(guard, load("UserPromptSubmit", cwd=str(repo), session_id=session_id, prompt=f"approve {code}"))
    assert handle(guard, patch(two_hunks)) == {}
    assert held(handle(guard, patch(one_hunk))), "one run"


# -- the parts ---------------------------------------------------------------------------


def test_codes_have_one_shape_that_the_tripwire_knows():
    shape = re.compile(checks.SIGNOFF_CODE_SHAPE)
    codes = {signoff.code_for(f"session-{i}", f"shell\x00command {i}") for i in range(2_000)}
    assert len(codes) == 2_000, "no collisions in a realistic sample"
    for code in codes:
        assert len(code) == 6 and set(code) <= set(signoff.ALPHABET)
        assert not set(code) & set("ILOU")
        assert shape.fullmatch(code), code
    assert signoff.code_for("s", "k") == signoff.code_for("s", "k"), "deterministic"
    assert signoff.code_for("s", "k") != signoff.code_for("t", "k"), "bound to the session"


@pytest.mark.parametrize(
    ("typed", "issued"),
    [("K7M2QX", "K7M2QX"), ("k7m2qx", "K7M2QX"), (" 1o3l5i ", "103151"), ("K7M2QU", None), ("K7M2Q", None)],
)
def test_typed_codes_are_read_the_crockford_way(typed, issued):
    assert signoff.normalise_code(typed) == issued


@pytest.mark.parametrize(
    ("prompt", "codes"),
    [
        ("approve K7M2QX", ["K7M2QX"]),
        ("Approve k7m2qx.", ["K7M2QX"]),
        ("`approve K7M2QX`", ["K7M2QX"]),
        ("approve **K7M2QX**", ["K7M2QX"]),
        ("yes, approve K7M2QX", ["K7M2QX"]),
        ("OK approve K7M2QX please", ["K7M2QX"]),
        ("I approve K7M2QX", ["K7M2QX"]),
        ("approved: K7M2QX", ["K7M2QX"]),
        ("approve K7M2QX, P3N8RT", ["K7M2QX", "P3N8RT"]),
        ("\n\n   approve K7M2QX   \nThen carry on with the docs.", ["K7M2QX"]),
        ("approve K7M2QX?", []),
        ("approve K7M2QX now", []),
        ("approve change", []),
        ("approve 123456", []),
        ("approveK7M2QX", []),
        ("approve K7M2QX " + "x" * 300, []),
        (None, []),
    ],
)
def test_what_counts_as_a_reply(prompt, codes):
    assert signoff.reply_codes(prompt) == codes


def test_a_prompt_without_a_session_grants_nothing(repo):
    store = ProjectStore.for_workspace(repo)
    assert store.signoff_settle("", "K7M2QX", "a", "x", 900)[0] == "requested"
    event = AgentEvent(event=EventType.USER_PROMPT, workspace=str(repo), prompt_text="approve K7M2QX")
    signoff.note_prompt(store, event)
    assert store.signoff_requests()[0]["granted_at"] is None


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("git  reset --hard   HEAD~1", "git reset --hard HEAD~1", True),
        ("git reset --hard HEAD~1 # wipe it", "git reset --hard HEAD~1", True),
        ('echo "a  b" > f', 'echo "a b" > f', False),
        ("rm -rf a\nb", "rm -rf a b", False),
        ("a && b", "a ; b", False),
        ("cat <<EOF > f\na  b\nEOF", "cat <<EOF > f\na b\nEOF", False),
    ],
)
def test_normalised_command(a, b, same):
    assert (signoff.normalised_command(a) == signoff.normalised_command(b)) is same


def test_file_actions_are_keyed_on_effect_and_path(repo):
    def key(tool: str, path: str) -> str:
        event = AgentEvent(
            event=EventType.PRE_TOOL_USE, workspace=str(repo), session_id="s", tool=tool,
            arguments={"file_path": path},
        )
        return signoff.action_key(event)

    absolute = str(repo / "conf" / "x.json")
    assert key("Edit", absolute) == key("MultiEdit", absolute) == key("Write", "conf/../conf/x.json")
    assert key("Delete", absolute) != key("Write", absolute)
    assert key("Write", absolute) != key("Write", str(repo / "conf" / "y.json"))


def test_the_ladder_shows_every_code_a_merged_decision_carries():
    decision = Decision(
        action=DecisionAction.REQUEST_REVIEW, reason="r", signoff_required=True,
        signoff_code="K7M2QX, p3n8rt not-a-code K7M2QX",
    )
    rendering = hosts.render(decision, hosts.CODEX, EventType.PRE_TOOL_USE)
    assert "reply `approve K7M2QX P3N8RT`" in rendering.reason
    assert "`agentguard approve K7M2QX P3N8RT`" in rendering.system_message


def test_an_existing_database_gains_the_table(repo, isolated_home):
    store = ProjectStore.for_workspace(repo)
    task = store.create_task("s", "an old prompt")
    store.db.write("DROP TABLE signoffs", ())
    store.db.write("UPDATE schema_meta SET value='3' WHERE key='version'", ())
    Database.reset_shared()

    reopened = ProjectStore.for_workspace(repo)
    assert not reopened.degraded_reason
    assert reopened.db.query("SELECT value FROM schema_meta WHERE key='version'")[0]["value"] == "4"
    assert reopened.task_record(task)["prompt"] == "an old prompt", "nothing existing was touched"
    assert reopened.signoff_settle("s", "K7M2QX", "a", "x", 900)[0] == "requested"
    assert Path(reopened.db.path).stat().st_mode & 0o077 == 0, "owner-only, as before"
