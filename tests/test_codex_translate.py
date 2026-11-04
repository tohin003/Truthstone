"""Codex adapter: payload -> events, decision -> Codex output, and the real Guard behind it.

The payload side is driven by payloads captured from a live ``codex exec``
(``fixtures/codex_payloads``); the engine side goes through a real ``Guard`` over the
``pyrepo`` fixture, because unit tests that bypass the wiring can pass while the product
does nothing (PROGRESS.md, "Design decisions worth remembering").
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agentguard.adapters.codex import render
from agentguard.adapters.codex import translate as codex
from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import ChallengeCategory, DecisionAction, EventType, FailureMode, Severity, Verdict
from agentguard.core.models import Decision, Finding
from tests.codex_schema import validate

FIXTURES = Path(__file__).parent / "fixtures"
PAYLOADS = FIXTURES / "codex_payloads"


def load(name: str, **overrides) -> dict:
    payload = json.loads((PAYLOADS / f"{name}.json").read_text())
    payload.update(overrides)
    return payload


# -- payload -> events -------------------------------------------------------------


class TestEvents:
    @pytest.mark.parametrize(
        ("name", "event_type"),
        [
            ("SessionStart", EventType.SESSION_START),
            ("UserPromptSubmit", EventType.USER_PROMPT),
            ("PreToolUse.Bash.denied", EventType.PRE_TOOL_USE),
            ("PostToolUse.Bash", EventType.POST_TOOL_USE),
            ("Stop", EventType.STOP),
            ("SessionEnd", EventType.SESSION_END),
        ],
    )
    def test_every_captured_event_translates(self, name, event_type):
        payload = load(name)
        events = codex.to_events(payload)
        assert [e.event for e in events] == [event_type]
        assert events[0].agent == "codex"
        assert events[0].session_id == payload["session_id"] and len(payload["session_id"]) == 36
        assert events[0].workspace == "/workspace"

    def test_the_prompt_is_read(self):
        event = codex.to_event(load("UserPromptSubmit"))
        assert event.prompt_text and event.prompt_text.startswith("Do these steps")

    def test_stop_keeps_its_loop_breaker(self):
        assert codex.to_event(load("Stop")).raw["stop_hook_active"] is False
        continued = codex.to_event(load("Stop.continued"))
        assert continued.raw["stop_hook_active"] is True
        assert continued.last_assistant_message

    def test_bash_command_and_result(self):
        pre = codex.to_event(load("PreToolUse.Bash.denied"))
        assert (pre.tool, pre.arguments) == ("Bash", {"command": "rm -rf build ."})
        post = codex.to_event(load("PostToolUse.Bash"))
        # The adapter result contract. Codex sends only the output text: exit code unknown.
        assert post.result == {"stdout": "hello-codex\n", "exit_code": None, "interrupted": False}

    def test_a_read_is_not_judged_as_a_write(self):
        """Codex reads through Bash. A certain read skips the write-path checks..."""
        assert codex.to_events(load("PreToolUse.Bash")) == []  # `echo hello-codex`
        # ...but its PostToolUse is still recorded.
        assert [e.tool for e in codex.to_events(load("PostToolUse.Bash"))] == ["Bash"]

    def test_rewritten_command_is_what_post_tool_use_reports(self):
        post = codex.to_event(load("PostToolUse.Bash.rewritten"))
        assert post.arg("command") == "echo rewritten-cmd"

    def test_ignored_events(self):
        assert codex.to_events({"hook_event_name": "PermissionRequest"}) == []
        assert codex.to_events({"hook_event_name": "PreCompact"}) == []
        assert codex.to_events({}) == []
        assert codex.to_event({"hook_event_name": "Interrupt"}) is None

    @pytest.mark.parametrize(
        ("tool_input", "command"),
        [
            ({"command": "pytest -q"}, "pytest -q"),
            ({"command": ["bash", "-lc", "pytest -q"]}, "pytest -q"),
            ({"command": ["/bin/zsh", "-c", "rm -rf build"]}, "rm -rf build"),
            ({"command": ["git", "push", "--force"]}, "git push --force"),
            ({"command": ["python", "-c", "print(1)"]}, "python -c 'print(1)'"),
            ({"command": ["sh", "-c", 'rm -rf "$1"', "_", "/"]}, "sh -c 'rm -rf \"$1\"' _ /"),
            ("make build", "make build"),
        ],
    )
    def test_shell_argv_becomes_one_command_string(self, tool_input, command):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": tool_input}
        assert codex.to_event(payload).arg("command") == command

    @pytest.mark.parametrize(
        "command",
        [
            "ls",
            "ls -la src",
            "cat a.py | head -20",
            "rg foo src && git status",
            "git -C sub log --oneline",
            "sed -n '1,20p' f.py",
            'find . -name "*.py"',
            "ls ; pwd",
            "grep 'a|b' f",
        ],
    )
    def test_certain_reads(self, command):
        assert codex.is_read_only_command(command)

    @pytest.mark.parametrize(
        "command",
        [
            "wc -l < f",  # unsure means validated, never skipped
            "cat a > b",
            "ls; rm x",
            "ls && rm -rf build",
            "find . -delete",
            "find . -exec rm {} ;",
            "git push",
            "git diff --output=p.diff",
            "sed -i 's/a/b/' f",
            "echo $(rm x)",
            "echo `rm x`",
            "cat f | tee g",
            "cat a & rm b",
            "echo ok || rm x",
            "python -c 1",
            "X=1 ls",
            "pytest -q",
            "./ls",
            "ls\nrm x",
            "",
        ],
    )
    def test_anything_uncertain_is_not_a_read(self, command):
        assert not codex.is_read_only_command(command)

    def test_unparseable_shell_input_has_no_command(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"cmd": 1}}
        assert codex.to_event(payload).arguments == {}

    def test_exit_code_header_is_lifted_when_present(self):
        result = codex.shell_result("Exit code: 1\nWall time: 0.2 seconds\nOutput:\n1 failed\n")
        assert result == {"stdout": "1 failed\n", "exit_code": 1, "interrupted": False}
        assert codex.shell_result("plain") == {"stdout": "plain", "exit_code": None, "interrupted": False}
        assert codex.shell_result(None) is None

    def test_unknown_tools_are_recorded_never_judged(self):
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "mcp__fs__write_file",
            "tool_input": {"file_path": "/workspace/x.py", "content": "y"},
        }
        assert codex.to_events(payload) == []  # no write-path checks on an unknown tool
        payload["hook_event_name"] = "PostToolUse"
        event = codex.to_event(payload)
        assert event.tool == "mcp__fs__write_file"
        assert not event.is_read_only
        assert event.arg("file_path") is None  # never mistaken for a recorded edit
        assert event.arg("input")["file_path"] == "/workspace/x.py"


class TestApplyPatchEvents:
    def test_add_with_absolute_path(self):
        (event,) = codex.to_events(load("PreToolUse.apply_patch.add_absolute"))
        assert event.tool == "Write"
        assert event.arg("file_path") == "/workspace/notes.txt"
        assert event.arg("content") == "alpha\n"

    def test_add_and_delete_become_one_event_each(self):
        events = codex.to_events(load("PreToolUse.apply_patch.add_delete"))
        assert [(e.tool, e.arg("file_path")) for e in events] == [
            ("Write", "/workspace/b.txt"),
            ("Delete", "/workspace/old.txt"),
        ]
        assert len({e.tool_use_id for e in events}) == 2
        assert all(not e.is_read_only for e in events)

    def test_move_is_a_write_at_the_destination_and_a_delete_of_the_source(self):
        events = codex.to_events(load("PreToolUse.apply_patch.move"))
        assert [(e.tool, e.arg("file_path")) for e in events] == [
            ("Write", "/workspace/d.txt"),
            ("Delete", "/workspace/c.txt"),
        ]

    def test_update_reads_the_file_and_reproduces_codex(self, tmp_path):
        (tmp_path / "README.md").write_text("".join(f"line {i}\n" for i in range(1, 8)))
        payload = load("PreToolUse.apply_patch.two_hunks", cwd=str(tmp_path))
        payload["tool_input"]["command"] = (
            "*** Begin Patch\n*** Update File: README.md\n@@\n line 1\n-line 2\n+line two\n line 3\n"
            "@@\n line 5\n-line 6\n+line six\n line 7\n*** End Patch"
        )
        (event,) = codex.to_events(payload, root=tmp_path)
        assert event.tool == "MultiEdit"
        from agentguard.evidence import extractors

        outcome = extractors.resolve_edit(event, tmp_path)
        assert outcome.after == "line 1\nline two\nline 3\nline 4\nline 5\nline six\nline 7\n"

    def test_update_outside_the_workspace_is_never_read(self, tmp_path):
        outside = tmp_path / "outside.txt"
        outside.write_text("secret\n")
        root = tmp_path / "repo"
        root.mkdir()
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "apply_patch",
            "cwd": str(root),
            "tool_input": {
                "command": (
                    f"*** Begin Patch\n*** Update File: {outside}\n@@\n-secret\n+public\n*** End Patch"
                )
            },
        }
        (event,) = codex.to_events(payload, root=root)
        # Described literally from the hunk: nothing was read from outside the repository.
        assert event.arguments["old_string"] == "secret\n"
        assert event.arguments["new_string"] == "public\n"

    def test_a_patch_codex_would_reject_stays_opaque(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "apply_patch"}
        payload["tool_input"] = {"command": "nope"}
        (event,) = codex.to_events(payload)
        assert event.tool == "apply_patch"
        assert event.arg("file_path") is None


# -- decision -> output ------------------------------------------------------------


def bash_event():
    return codex.to_event(load("PreToolUse.Bash.denied"))


RISK = Finding(
    category=ChallengeCategory.RISK,
    verdict=Verdict.REQUIRES_HUMAN,
    failure_mode=FailureMode.NOT_A_FAILURE,
    severity=Severity.HIGH,
    subject="git push --force",
    summary="Irreversible command: force push",
)
GUARD = Finding(
    category=ChallengeCategory.RISK,
    verdict=Verdict.SUPPORTED_WITH_RISK,
    failure_mode=FailureMode.NOT_A_FAILURE,
    severity=Severity.MEDIUM,
    subject="modified command",
    summary="AgentGuard narrowed this command: guarded `OUT` against being unset",
    detail="`rm -rf $OUT` deletes `/` if `OUT` is empty. The rewrite refuses to run.",
)


class TestOutputs:
    def test_allow_is_silent_everywhere(self):
        for hook in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SessionEnd"):
            assert codex.from_decision(bash_event(), Decision.allow(), hook) == {}

    def test_agentguard_never_emits_allow_in_this_release(self):
        """No `allow` at all by default: rewrites are switched off (IMPROVEMENTS.md A5)."""
        assert render.ENABLE_REWRITES is False
        for action in DecisionAction:
            for tool in ("Bash", "Write", "Delete"):
                event = bash_event().model_copy(update={"tool": tool})
                decision = Decision(action=action, reason="r", updated_arguments={"command": "ls"})
                for hook in ("PreToolUse", "PostToolUse", "Stop", "UserPromptSubmit", "SessionStart"):
                    out = codex.from_decision(event, decision, hook)
                    assert out.get("hookSpecificOutput", {}).get("permissionDecision") != "allow"

    def test_even_with_rewrites_on_allow_only_carries_a_bash_rewrite(self):
        for action in DecisionAction:
            for tool in ("Bash", "Write", "Delete"):
                event = bash_event().model_copy(update={"tool": tool})
                decision = Decision(action=action, reason="r", updated_arguments={"command": "ls"})
                out = render.render(event, decision, "PreToolUse", rewrites=True)
                if out.get("hookSpecificOutput", {}).get("permissionDecision") == "allow":
                    assert action is DecisionAction.MODIFY and tool == "Bash"
                    assert out["hookSpecificOutput"]["updatedInput"] == {"command": "ls"}

    def test_never_ask_or_defer(self):
        for action in DecisionAction:
            for rewrites in (False, True):
                decision = Decision(action=action, reason="r", findings=[RISK])
                out = render.render(bash_event(), decision, "PreToolUse", rewrites=rewrites)
                assert out.get("hookSpecificOutput", {}).get("permissionDecision") not in ("ask", "defer")

    def test_challenge_denies_with_the_evidence(self):
        decision = Decision(action=DecisionAction.CHALLENGE, reason="`get_active_users` does not exist.")
        out = codex.from_decision(bash_event(), decision, "PreToolUse")
        assert out == {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "`get_active_users` does not exist.",
            }
        }

    def test_an_irreversible_review_needs_sign_off(self):
        decision = Decision(
            action=DecisionAction.REQUEST_REVIEW, reason="Irreversible command: force push", findings=[RISK]
        )
        out = codex.from_decision(bash_event(), decision, "PreToolUse")
        spec = out["hookSpecificOutput"]
        assert spec["permissionDecision"] == "deny"
        assert spec["permissionDecisionReason"].startswith(render.SIGN_OFF)
        assert "ask the user to confirm, then re-run" in spec["permissionDecisionReason"].lower()
        assert "force push" in out["systemMessage"]

    def test_any_other_review_is_context_not_a_block(self):
        decision = Decision(action=DecisionAction.REQUEST_REVIEW, reason="Worth a second look.")
        for hook in ("PreToolUse", "PostToolUse", "UserPromptSubmit"):
            out = codex.from_decision(bash_event(), decision, hook)
            expected = {"hookEventName": hook, "additionalContext": "Worth a second look."}
            assert out == {"hookSpecificOutput": expected}
        assert codex.from_decision(bash_event(), decision, "Stop") == {}  # recorded only

    def test_modify_is_a_challenge_carrying_the_guarded_form(self):
        decision = Decision(
            action=DecisionAction.MODIFY,
            reason="AgentGuard narrowed this command: guarded `OUT` against being unset",
            additional_context="narrowed",
            updated_arguments={"command": '[ -n "$OUT" ] && rm -rf "$OUT"'},
            findings=[GUARD],
        )
        spec = codex.from_decision(bash_event(), decision, "PreToolUse")["hookSpecificOutput"]
        assert spec["permissionDecision"] == "deny"
        reason = spec["permissionDecisionReason"]
        assert "deletes `/` if `OUT` is empty" in reason
        assert '    [ -n "$OUT" ] && rm -rf "$OUT"' in reason
        assert "narrowed" not in reason  # nothing was narrowed; the agent decides

    def test_the_rewrite_switch_restores_allow_plus_updated_input(self):
        decision = Decision(
            action=DecisionAction.MODIFY,
            reason="narrowed",
            additional_context="AgentGuard narrowed this command.",
            updated_arguments={"command": '[ -n "$OUT" ] && rm -rf "$OUT"'},
        )
        spec = render.render(bash_event(), decision, "PreToolUse", rewrites=True)["hookSpecificOutput"]
        assert spec["permissionDecision"] == "allow"
        assert spec["updatedInput"] == {"command": '[ -n "$OUT" ] && rm -rf "$OUT"'}
        assert spec["additionalContext"] == "AgentGuard narrowed this command."

    def test_modify_that_codex_cannot_carry_becomes_an_objection(self):
        event = bash_event().model_copy(update={"tool": "Write"})
        decision = Decision(action=DecisionAction.MODIFY, reason="use the helper", updated_arguments={"x": 1})
        spec = render.render(event, decision, "PreToolUse", rewrites=True)["hookSpecificOutput"]
        assert spec["permissionDecision"] == "deny"
        assert "use the helper" in spec["permissionDecisionReason"]

    def test_stop_block_is_the_completion_gate_and_carries_nothing_else(self):
        decision = Decision(
            action=DecisionAction.BLOCK, reason="Run the tests.", additional_context="ignored on Stop"
        )
        assert codex.from_decision(bash_event(), decision, "Stop") == {
            "decision": "block",
            "reason": "Run the tests.",
        }

    def test_context_rides_on_prompt_and_session_start(self):
        decision = Decision(additional_context="Complexity 3/100.")
        for hook in ("UserPromptSubmit", "SessionStart", "PostToolUse", "PreToolUse"):
            out = codex.from_decision(bash_event(), decision, hook)
            expected = {"hookEventName": hook, "additionalContext": "Complexity 3/100."}
            assert out == {"hookSpecificOutput": expected}


class TestCombine:
    def _event(self, path):
        return bash_event().model_copy(update={"tool": "Write", "arguments": {"file_path": path}})

    def test_strictest_wins_and_every_concern_is_listed(self):
        results = [
            (self._event("/workspace/a.py"), Decision()),
            (
                self._event("/workspace/b.py"),
                Decision(action=DecisionAction.REQUEST_REVIEW, reason="b needs a human"),
            ),
            (self._event("/workspace/c.py"), Decision(action=DecisionAction.CHALLENGE, reason="c is wrong")),
        ]
        event, decision = codex.combine(results)
        assert decision.action is DecisionAction.CHALLENGE
        assert event.arg("file_path") == "/workspace/c.py"
        assert "2 need attention" in decision.reason
        assert "[b.py]\nb needs a human" in decision.reason
        assert "[c.py]\nc is wrong" in decision.reason

    def test_all_quiet_stays_quiet(self):
        results = [(self._event("/workspace/a.py"), Decision()), (self._event("/workspace/b.py"), Decision())]
        _, decision = codex.combine(results)
        assert decision.action is DecisionAction.ALLOW
        assert codex.from_decision(results[0][0], decision, "PreToolUse") == {}

    def test_block_outranks_everything(self):
        results = [
            (self._event("/workspace/a.py"), Decision(action=DecisionAction.CHALLENGE, reason="a")),
            (self._event("/workspace/b.py"), Decision(action=DecisionAction.BLOCK, reason="b")),
        ]
        assert codex.combine(results)[1].action is DecisionAction.BLOCK


# -- through a real Guard ------------------------------------------------------------


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", dest)
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=dest,
        check=True,
    )
    return dest


@pytest.fixture
def guard(repo):
    g = Guard(Settings())
    g.workspace(repo).index.ready(timeout=30)
    yield g
    g.close()


def payload(repo: Path, hook: str, session: str = "sess-codex", **fields) -> dict:
    return {
        "session_id": session,
        "turn_id": "turn-1",
        "transcript_path": None,
        "cwd": str(repo),
        "hook_event_name": hook,
        "model": "gpt-test",
        "permission_mode": "default",
        **fields,
    }


def patch_payload(repo: Path, hook: str, text: str, **fields) -> dict:
    return payload(
        repo, hook, tool_name="apply_patch", tool_input={"command": text}, tool_use_id="call-1", **fields
    )


def handle(guard, data: dict) -> dict:
    out = codex.handle_payload(guard, data)
    schema = f"{data['hook_event_name']}"
    from tests.test_codex_contract import schema_name

    assert validate(out, schema_name(schema, "output")) == []
    return out


class TestThroughTheGuard:
    def test_a_hallucinated_method_in_one_file_of_a_patch_is_challenged(self, guard, repo):
        handle(guard, payload(repo, "UserPromptSubmit", prompt="Add an active-users report endpoint"))
        text = (
            "*** Begin Patch\n"
            "*** Add File: src/shop/api/report.py\n"
            "+from shop.repositories.user import UserRepository\n"
            "+\n"
            "+\n"
            "+def active_report(session):\n"
            "+    repo = UserRepository(session)\n"
            "+    return repo.get_active_users()\n"
            "*** Update File: src/shop/api/users.py\n"
            "@@\n"
            ' """Users endpoint — SPEC §33\'s "/users endpoint exists"."""\n'
            "+# reviewed\n"
            "*** End Patch"
        )
        out = handle(guard, patch_payload(repo, "PreToolUse", text))
        spec = out["hookSpecificOutput"]
        assert spec["permissionDecision"] == "deny"
        reason = spec["permissionDecisionReason"]
        assert "get_active_users" in reason
        assert "[src/shop/api/report.py]" in reason
        assert "users.py" not in reason.split("]")[0]  # the clean file raised nothing
        # Both files were evaluated and recorded separately.
        decisions = guard.workspace(repo).store.recent_decisions(5)
        assert sum(1 for row in decisions if row["tool"] in ("Write", "Edit")) >= 2

    def test_a_hallucination_inside_an_update_hunk_is_challenged(self, guard, repo):
        handle(guard, payload(repo, "UserPromptSubmit", prompt="List only active users"))
        text = (
            "*** Begin Patch\n*** Update File: src/shop/api/users.py\n"
            "@@ def list_users(session, page: int = 1):\n"
            "     repo = UserRepository(session)\n"
            "-    return repo.list_all()\n"
            "+    return repo.get_active_users()\n"
            "*** End Patch"
        )
        out = handle(guard, patch_payload(repo, "PreToolUse", text))
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "get_active_users" in out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_ordinary_work_is_silent(self, guard, repo):
        handle(guard, payload(repo, "UserPromptSubmit", prompt="Show me the users module"))
        bash = {"tool_name": "Bash", "tool_input": {"command": "ls src/shop"}, "tool_use_id": "c1"}
        assert handle(guard, payload(repo, "PreToolUse", **bash)) == {}
        assert handle(guard, payload(repo, "PostToolUse", tool_response="api\nmodels.py\n", **bash)) == {}
        assert handle(guard, payload(repo, "SessionStart", source="startup")) == {}

    def test_force_push_needs_sign_off_and_is_not_asked_twice(self, guard, repo):
        handle(guard, payload(repo, "UserPromptSubmit", prompt="Publish the branch"))
        bash = {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}}
        first = handle(guard, payload(repo, "PreToolUse", **bash))
        assert first["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert first["hookSpecificOutput"]["permissionDecisionReason"].startswith(render.SIGN_OFF)
        assert "systemMessage" in first
        # Today's core raises a concern once per task (IMPROVEMENTS.md A1 will change that):
        # a re-run after the developer confirms goes through.
        assert handle(guard, payload(repo, "PreToolUse", **bash)) == {}

    def test_an_unguarded_variable_delete_is_challenged_with_the_guarded_form(self, guard, repo):
        handle(guard, payload(repo, "UserPromptSubmit", prompt="Clean the build output"))
        bash = {"tool_name": "Bash", "tool_input": {"command": "rm -rf $BUILD_DIR"}}
        spec = handle(guard, payload(repo, "PreToolUse", **bash))["hookSpecificOutput"]
        assert spec["permissionDecision"] == "deny"
        assert '[ -n "$BUILD_DIR" ] && rm -rf "$BUILD_DIR"' in spec["permissionDecisionReason"]
        command = '[ -n "$BUILD_DIR" ] && rm -rf "$BUILD_DIR"'
        guarded = {"tool_name": "Bash", "tool_input": {"command": command}}
        assert handle(guard, payload(repo, "PreToolUse", **guarded)) == {}

    def test_completion_gate_holds_an_unverified_done_until_tests_run(self, guard, repo):
        prompt = "Raise the default page size in paginate to 25"
        handle(guard, payload(repo, "UserPromptSubmit", prompt=prompt))
        text = (
            "*** Begin Patch\n*** Update File: src/shop/utils/pagination.py\n"
            "@@\n-def paginate(query, page: int = 1, per_page: int = 20):\n"
            "+def paginate(query, page: int = 1, per_page: int = 25):\n*** End Patch"
        )
        assert handle(guard, patch_payload(repo, "PreToolUse", text)) == {}
        source = repo / "src/shop/utils/pagination.py"
        source.write_text(source.read_text().replace("per_page: int = 20", "per_page: int = 25"))
        success = "Exit code: 0\nWall time: 0 seconds\nOutput:\nSuccess. Updated the following files:\nM x\n"
        assert handle(guard, patch_payload(repo, "PostToolUse", text, tool_response=success)) == {}

        stop = payload(repo, "Stop", stop_hook_active=False, last_assistant_message="Done. All tests pass.")
        held = handle(guard, stop)
        assert held["decision"] == "block"
        assert "tests/test_pagination.py" in held["reason"]

        bash = {"tool_name": "Bash", "tool_input": {"command": "pytest -q tests/test_pagination.py"}}
        handle(guard, payload(repo, "PostToolUse", tool_response="1 passed in 0.01s\n", **bash))
        after = payload(repo, "Stop", stop_hook_active=True, last_assistant_message="Done.")
        assert handle(guard, after) == {}

    def test_patch_post_tool_use_records_every_file_it_touched(self, guard, repo):
        handle(guard, payload(repo, "UserPromptSubmit", prompt="Tidy the utils package"))
        text = (
            "*** Begin Patch\n*** Add File: src/shop/utils/extra.py\n+X = 1\n"
            "*** Delete File: src/shop/utils/__init__.py\n"
            "*** Update File: src/shop/utils/pagination.py\n*** Move to: src/shop/utils/paging.py\n"
            "@@\n-def page_metadata(total: int, page: int, per_page: int) -> dict:\n"
            "+def page_meta(total: int, page: int, per_page: int) -> dict:\n*** End Patch"
        )
        handle(guard, patch_payload(repo, "PostToolUse", text, tool_response="Success."))
        ws = guard.workspace(repo)
        state = ws.task_state(None, "sess-codex")
        assert state.touched_files >= {
            "src/shop/utils/extra.py",
            "src/shop/utils/__init__.py",
            "src/shop/utils/pagination.py",
            "src/shop/utils/paging.py",
        }

    def test_a_disabled_guard_answers_nothing(self, repo, monkeypatch):
        monkeypatch.setenv("AGENTGUARD_DISABLE", "1")
        g = Guard(Settings.load())
        try:
            text = "*** Begin Patch\n*** Add File: x.py\n+import nothing_here\n*** End Patch"
            assert codex.handle_payload(g, patch_payload(repo, "PreToolUse", text)) == {}
            assert g._workspaces == {}
        finally:
            g.close()
