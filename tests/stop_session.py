"""A Claude-Code-shaped session over a synthetic repository, for the v0.2 Stop tests.

Unlike ``tests/test_gate_timeline.Session`` every edit sends its PreToolUse first, as the
host does, so the task captures each file as it found it (the baseline the Stop-time
integrity checks compare with).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.conftest import stop_event, user_prompt_submit
from truthstone.adapters.claude_code import translate as claude
from truthstone.core.config import Settings
from truthstone.core.engine import Guard


def make_repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for path, text in files.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"],
        check=True,
    )
    return root


class StopSession:
    def __init__(self, repo: Path, profile: str = "minimal") -> None:
        self.repo = repo
        self.guard = Guard(Settings(profile=profile))
        self.guard.workspace(repo).index.ready(timeout=30)
        self.decisions: list = []

    def send(self, payload: dict) -> dict:
        event = claude.to_event({**payload, "cwd": str(self.repo)})
        decision = self.guard.handle(event)
        self.decisions.append(decision)
        return claude.from_decision(event, decision, payload["hook_event_name"])

    def prompt(self, text: str) -> dict:
        return self.send(user_prompt_submit(text))

    def write(self, path: str, text: str) -> dict:
        """A Write: PreToolUse, the file written, PostToolUse."""
        full = self.repo / path
        tool_input = {"file_path": str(full), "content": text}
        pre = self.send(
            {
                "session_id": "sess-1",
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": tool_input,
            }
        )
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text)
        self.send(
            {
                "session_id": "sess-1",
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "tool_input": tool_input,
                "tool_response": {"filePath": str(full)},
            }
        )
        return pre

    def replace(self, path: str, old: str, new: str) -> dict:
        text = (self.repo / path).read_text()
        assert old in text, f"{old!r} not in {path}"
        return self.write(path, text.replace(old, new))

    def run(self, command: str, output: str, exit_code: int = 0) -> dict:
        if exit_code == 0:
            payload = {
                "hook_event_name": "PostToolUse",
                "tool_response": {"stdout": output, "stderr": "", "interrupted": False},
            }
        else:
            payload = {"hook_event_name": "PostToolUseFailure", "error": f"Exit code {exit_code}\n{output}"}
        return self.send(
            {**payload, "session_id": "sess-1", "tool_name": "Bash", "tool_input": {"command": command}}
        )

    def stop(self, message: str) -> dict:
        return self.send(stop_event(message))

    @property
    def last(self):
        return self.decisions[-1]

    def close(self) -> None:
        self.guard.close()


def pytest_output(failed: list[str], passed: int) -> str:
    """A pytest -q summary naming each failing node id."""
    lines = ["." * passed + "F" * len(failed)]
    lines += [f"FAILED {node} - AssertionError" for node in failed]
    tail = (f"{len(failed)} failed, " if failed else "") + f"{passed} passed in 0.05s"
    return "\n".join([*lines, tail]) + "\n"
