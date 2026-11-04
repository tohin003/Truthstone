# ruff: noqa: E501, RUF001 -- recorded-style session data (long lines, node's reporter glyphs)
"""Shared helpers for the T2 Stop audit (``tests/test_audit_stop_*.py``); holds no tests.

``CodexSession`` drives the real Guard through the Codex adapter the way codex-cli 0.166.0
does: edits arrive as ``apply_patch`` (PreToolUse, the file written, PostToolUse), and a
Bash PostToolUse carries only the output text, never an exit code.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from tests.stop_session import StopSession, make_repo, pytest_output  # noqa: F401 - re-exported
from truthstone.adapters.codex import translate as codex
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import DecisionAction


def _hunks(old: str, new: str) -> list[str]:
    """Codex-style update hunks (``@@`` + context/-/+ lines) turning ``old`` into ``new``."""
    a, b = old.splitlines(), new.splitlines()
    out: list[str] = []
    for group in difflib.SequenceMatcher(None, a, b).get_grouped_opcodes(3):
        out.append("@@")
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                out.extend(" " + line for line in a[i1:i2])
                continue
            out.extend("-" + line for line in a[i1:i2])
            out.extend("+" + line for line in b[j1:j2])
    return out


class CodexSession:
    """A Codex-shaped session (apply_patch edits, exit-code-less Bash results)."""

    def __init__(self, repo: Path, profile: str = "minimal") -> None:
        self.repo = repo
        self.guard = Guard(Settings(profile=profile))
        self.guard.workspace(repo).index.ready(timeout=30)
        self.decisions: list = []
        self.outputs: list[dict] = []
        self._calls = 0

    def _payload(self, hook: str, **fields) -> dict:
        return {
            "session_id": "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0000",
            "turn_id": "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0001",
            "transcript_path": None,
            "cwd": str(self.repo),
            "hook_event_name": hook,
            "model": "gpt-6.1-sol",
            "permission_mode": "bypassPermissions",
            **fields,
        }

    def send(self, payload: dict) -> dict:
        out, _results, decision = codex.dispatch(self.guard, payload)
        if decision is not None:
            self.decisions.append(decision)
        self.outputs.append(out)
        return out

    def prompt(self, text: str) -> dict:
        return self.send(self._payload("UserPromptSubmit", prompt=text))

    def _patch(self, body: str, apply, summary: str) -> dict:
        self._calls += 1
        call = f"call_{self._calls:03d}"
        tool_input = {"command": body}
        pre = self.send(self._payload("PreToolUse", tool_name="apply_patch", tool_input=tool_input, tool_use_id=call))
        apply()
        response = (
            "Exit code: 0\nWall time: 0.1 seconds\nOutput:\n"
            f"Success. Updated the following files:\n{summary}\n"
        )
        self.send(
            self._payload(
                "PostToolUse", tool_name="apply_patch", tool_input=tool_input, tool_response=response, tool_use_id=call
            )
        )
        return pre

    def write(self, path: str, text: str) -> dict:
        full = self.repo / path
        if full.exists():
            old = full.read_text()
            body = "\n".join(["*** Begin Patch", f"*** Update File: {path}", *_hunks(old, text), "*** End Patch"])

            def apply() -> None:
                full.write_text(text)

            return self._patch(body, apply, f"M {path}")
        lines = [f"+{line}" for line in text.splitlines()]
        body = "\n".join(["*** Begin Patch", f"*** Add File: {path}", *lines, "*** End Patch"])

        def create() -> None:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(text)

        return self._patch(body, create, f"A {path}")

    def replace(self, path: str, old: str, new: str) -> dict:
        text = (self.repo / path).read_text()
        assert old in text, f"{old!r} not in {path}"
        return self.write(path, text.replace(old, new))

    def move(self, path: str, new_path: str, text: str) -> dict:
        """``*** Update File`` + ``*** Move to``: a rename with an edit, as Codex writes it."""
        old_full, new_full = self.repo / path, self.repo / new_path
        body = "\n".join(
            [
                "*** Begin Patch",
                f"*** Update File: {path}",
                f"*** Move to: {new_path}",
                *_hunks(old_full.read_text(), text),
                "*** End Patch",
            ]
        )

        def apply() -> None:
            new_full.parent.mkdir(parents=True, exist_ok=True)
            new_full.write_text(text)
            old_full.unlink()

        return self._patch(body, apply, f"M {new_path}")

    def delete(self, path: str) -> dict:
        full = self.repo / path
        body = "\n".join(["*** Begin Patch", f"*** Delete File: {path}", "*** End Patch"])
        return self._patch(body, full.unlink, f"D {path}")

    def run(self, command: str, output: str) -> dict:
        """A Bash call as Codex reports it: the output text only, no exit code."""
        self._calls += 1
        call = f"call_{self._calls:03d}"
        tool_input = {"command": command}
        self.send(self._payload("PreToolUse", tool_name="Bash", tool_input=tool_input, tool_use_id=call))
        return self.send(
            self._payload("PostToolUse", tool_name="Bash", tool_input=tool_input, tool_response=output, tool_use_id=call)
        )

    def stop(self, message: str) -> dict:
        return self.send(self._payload("Stop", stop_hook_active=False, last_assistant_message=message))

    @property
    def last(self):
        return self.decisions[-1]

    def close(self) -> None:
        self.guard.close()


def assert_silent(session, out: dict) -> None:
    """The Stop reaches the agent as nothing: ALLOW after the profile, and no block."""
    decision = session.last
    said = (decision.reason or "")[:400]
    reason = out.get("reason", "") or ""
    concerns = [line.strip() for line in reason.splitlines() if re.match(r"^\s*(?:\d+\. |This change|The latest|The final message|Nothing in|  - )", line)]
    assert out.get("decision") != "block", "blocked: " + " | ".join(concerns)[:1500]
    assert decision.action is DecisionAction.ALLOW, f"{decision.action}: {said}"
    assert not out.get("reason"), out


def withheld(session) -> list[str]:
    """What the profile recorded but kept from the agent (for the report)."""
    return [f.subject for f in session.last.findings if f.subject.startswith("withheld:")]


def node_spec(passed: int, failed: int = 0, failing: list[tuple[str, str]] | None = None) -> str:
    """node --test output (spec reporter), the default of Node 22+."""
    lines = []
    for n in range(passed):
        lines.append(f"✔ case {n + 1} (0.4{n}ms)")
    for _path, title in failing or []:
        lines.append(f"✖ {title} (1.2ms)")
    total = passed + failed
    lines += [
        f"ℹ tests {total}",
        "ℹ suites 0",
        f"ℹ pass {passed}",
        f"ℹ fail {failed}",
        "ℹ cancelled 0",
        "ℹ skipped 0",
        "ℹ todo 0",
        "ℹ duration_ms 61.2041",
    ]
    if failing:
        lines += ["", "✖ failing tests:", ""]
        for path, title in failing:
            lines += [
                f"test at {path}:12:3",
                f"✖ {title} (1.2ms)",
                "  AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:",
                "",
                "  1 !== 2",
                "",
            ]
    return "\n".join(lines) + "\n"


def npm_wrap(name: str, script: str, body: str) -> str:
    return f"\n> {name}@1.0.0 test\n> {script}\n\n{body}"
