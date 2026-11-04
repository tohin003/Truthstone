"""Audit (robustness): Stop-time work stays bounded on large changes.

A formatter run over the whole tree (`npx prettier --write .`, `ruff format .`) is a shell
command, so its files reach the task without a baseline (G5). Stop compared none of them, yet
read every one; and nothing bounded how many files with a baseline it would read.
"""

from __future__ import annotations

from pathlib import Path

from truthstone.core.taskstate import TaskState
from truthstone.intent.models import TaskSpec
from truthstone.verify import arbiter, baseline


class _Index:
    def __init__(self, root: Path) -> None:
        self.root = root


def _state(root: Path, files: list[str], with_baseline: bool) -> TaskState:
    state = TaskState(task_id="t", spec=TaskSpec(prompt="Format the code."))
    for n, path in enumerate(files):
        (root / path).write_text(f"before {n}\n")
        if with_baseline:
            state.file_baselines[path] = baseline.capture(root, path, n)
        (root / path).write_text(f"after {n}\n")
        state.touch(path)
    return state


def test_files_changed_without_a_baseline_are_never_read(tmp_path, monkeypatch):
    reads: list[str] = []
    real = baseline.current_text

    def counting(root, path):
        reads.append(path)
        return real(root, path)

    monkeypatch.setattr(baseline, "current_text", counting)
    state = _state(tmp_path, [f"f{n}.ts" for n in range(50)], with_baseline=False)
    token = arbiter._TEXTS.set(None)
    try:
        assert arbiter.changed_texts(state, _Index(tmp_path)) == {}
    finally:
        arbiter._TEXTS.reset(token)
    assert reads == []


def test_at_most_a_bounded_number_of_files_are_compared(tmp_path, monkeypatch):
    monkeypatch.setattr(arbiter, "MAX_COMPARED_FILES", 10)
    state = _state(tmp_path, [f"f{n:02}.md" for n in range(25)], with_baseline=True)
    token = arbiter._TEXTS.set(None)
    try:
        texts = arbiter.changed_texts(state, _Index(tmp_path))
    finally:
        arbiter._TEXTS.reset(token)
    assert len(texts) == 10
    assert all(old.startswith("before") and new.startswith("after") for old, new in texts.values())
