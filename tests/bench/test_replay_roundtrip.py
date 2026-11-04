"""WP1(b): a scripted cell, recorded by the real logging hook, replays to its live decisions.

A scripted session drives a real golden task through hook events (session, prompt, a test
run, an edit, another test run, Stop). At each event the real recorder runs, as the host
would run it, and a deterministic stand-in engine decides on the *live* repository. Replay
then rebuilds every event's tree from the trace alone and runs the same engine: the
decisions must be identical, which is what makes the corpus usable for any later build.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from truthstone.bench import replay
from truthstone.bench.codex import guards, naming, scripted, suite

PYTHON = os.path.abspath(os.environ.get("CODEX_BENCH_PYTHON", ".venv/bin/python"))
RECORDER = Path(guards.__file__).with_name("hook_recorder.py")
SKIP = {".git", "__pycache__", ".pytest_cache", "node_modules"}


def _state(repo: Path) -> str:
    """What a stand-in engine 'sees' of the repository: every file a commit would hold."""
    digest = hashlib.sha256()
    for path in sorted(p for p in repo.rglob("*") if p.is_file()):
        rel = path.relative_to(repo)
        if SKIP & set(rel.parts) or path.suffix == ".pyc":
            continue
        digest.update(rel.as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


class Gate:
    """A deterministic stand-in engine: it holds Stop unless the tree is the last green one.
    Stateful, like the real one, so replay must feed it every event in order."""

    def __init__(self) -> None:
        self.green: str | None = None

    def __call__(self, event: replay.ReplayEvent, repo: Path) -> dict | None:
        state = _state(repo)
        if event.event == "PostToolUse" and event.tool == "Bash":
            output = str((event.payload.get("tool_response") or {}).get("output", ""))
            if " passed" in output and " failed" not in output:
                self.green = state
            return {"event_type": "post_tool_use", "action": "allow", "would_have": "", "reason": state[:16]}
        if event.event == "PreToolUse":
            return {"event_type": "pre_tool_use", "action": "allow", "would_have": "", "reason": state[:16]}
        if event.event == "Stop":
            held = self.green != state
            return {
                "event_type": "stop",
                "action": "block" if held else "allow",
                "would_have": "",
                "reason": f"stale {state[:16]}" if held else "",
            }
        return None


def _hook(trace: Path, payload: dict) -> None:
    proc = subprocess.run(
        [sys.executable, "-I", "-S", str(RECORDER), payload["hook_event_name"]],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", naming.ENV_RECORD_DIR: str(trace)},
        timeout=60,
    )
    assert proc.returncode == 0 and proc.stdout == ""  # silent, never a decision


def _pytest(repo: Path) -> dict:
    proc = subprocess.run(
        [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=300,
        env={"PATH": f"{Path(PYTHON).parent}:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return {"output": proc.stdout[-4000:], "exit_code": proc.returncode}


@pytest.fixture
def recorded_cell(tmp_path: Path) -> tuple[Path, list[dict], Path]:
    task = suite.load_suite(suite="golden-dev", only=["textkit-slug-boundary"])[0]
    made = suite.materialize(task, tmp_path / "w", tmp_path / "pristine", python=PYTHON)
    repo, trace, cell = made.repo, tmp_path / "trace", tmp_path / "cell"
    gate, live = Gate(), []
    base = {"session_id": "scripted", "cwd": str(repo), "transcript_path": None}

    def event(name: str, **fields) -> None:
        payload = {**base, "hook_event_name": name, **fields}
        _hook(trace, payload)  # the logging hook runs first, as on the host
        decision = gate(replay.ReplayEvent(len(live), name, 0.0, payload), repo)  # the live engine
        if decision is not None:
            live.append({**decision, "ts": len(live)})

    test = {"command": "python -m pytest -q"}
    event("SessionStart", source="startup")
    event("UserPromptSubmit", prompt=task.prompt("canonical"))
    event("PreToolUse", tool_name="Bash", tool_input=test)
    event("PostToolUse", tool_name="Bash", tool_input=test, tool_response=_pytest(repo))
    edit = {"file_path": "src/textkit/slug.py"}
    event("PreToolUse", tool_name="Edit", tool_input=edit)
    message = scripted.run_solution(task, "honest", repo, PYTHON)
    event("PostToolUse", tool_name="Edit", tool_input=edit, tool_response={"success": True})
    event("Stop", stop_hook_active=False, last_assistant_message=message)  # edited after the run: held
    event("PreToolUse", tool_name="Bash", tool_input=test)
    event("PostToolUse", tool_name="Bash", tool_input=test, tool_response=_pytest(repo))
    event("Stop", stop_hook_active=True, last_assistant_message=message)
    # what the orchestrator keeps of a cell
    shutil.copytree(trace, cell / replay.TRACE)
    (cell / "evidence.json").write_text(json.dumps({"decisions": live}))
    return cell, live, repo


def test_a_scripted_cell_replays_to_the_decisions_recorded_live(recorded_cell, tmp_path):
    cell, live, _repo = recorded_cell
    assert [d["action"] for d in live if d["event_type"] == "stop"] == ["block", "allow"]
    replayed = replay.replay(cell, Gate(), tmp_path / "replay")
    result = replay.compare(replay.live_decisions(cell), replayed, keys=("event_type", "action", "reason"))
    assert result["identical"], result


def test_the_trace_alone_rebuilds_every_event_and_keeps_tool_responses(recorded_cell, tmp_path):
    cell, _live, repo = recorded_cell
    corpus = replay.load(cell)
    assert corpus.replayable, corpus.problems
    names = [e.event for e in corpus.events]
    assert names[:3] == ["SessionStart", "UserPromptSubmit", "PreToolUse"] and names[-1] == "Stop"
    runs = [e for e in corpus.events if e.event == "PostToolUse" and e.tool == "Bash"]
    assert "failed" in runs[0].payload["tool_response"]["output"]  # the bug, before the fix
    assert " passed" in runs[-1].payload["tool_response"]["output"]
    trees = [e.tree for e in corpus.events]
    assert len(set(trees[:5])) == 1 and trees[5] != trees[0]  # the edit changed the tree
    final = replay.checkout(cell, corpus.events[-1].tree, tmp_path / "final")
    assert _state(final) == _state(repo)
    # and the repository itself was left alone: no index or object written into it
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True)
    assert "src/textkit/" in status.stdout  # the agent's change, uncommitted, as it left it
    assert not (repo / ".git" / "tree.index").exists()


def test_a_cell_recorded_before_wp1_is_not_replayable(tmp_path):
    cell = tmp_path / "old"
    (cell / replay.TRACE).mkdir(parents=True)
    (cell / replay.TRACE / "hooks.jsonl").write_text(json.dumps({"event": "Stop", "ts": 1}) + "\n")
    corpus = replay.load(cell)
    assert not corpus.replayable and any("payload" in p for p in corpus.problems)
    with pytest.raises(ValueError, match="cannot be replayed"):
        replay.replay(cell, Gate(), tmp_path / "r")
