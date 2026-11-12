"""Task content is what git tracks: a fixture file a .gitignore excludes is caught.

The candidate screen once halted on a clean checkout: `dist/` in the repository's .gitignore had
kept a task's built files out of every commit, while the registration hashed the working tree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from truthstone.bench.codex import suite


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    task = repo / "tasks" / "t1" / "overlay"
    (task / "src").mkdir(parents=True)
    (task / "src" / "a.py").write_text("x = 1\n")
    (task / "dist").mkdir()
    (task / "dist" / "a.js").write_text("export const x = 1;\n")
    (task / "src" / "__pycache__").mkdir()
    (task / "src" / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\0")
    (repo / ".gitignore").write_text("dist/\n__pycache__/\n")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "fixtures")
    return repo


def test_a_fixture_file_the_gitignore_excludes_is_detected(tmp_path):
    repo = _repo(tmp_path)
    found = suite.uncommitted_content([repo / "tasks" / "t1"])
    assert found["ignored"] == ["tasks/t1/overlay/dist/a.js"]  # the cache is not reported
    assert found["untracked"] == []
    (repo / "tasks" / "t1" / "overlay" / "src" / "b.py").write_text("y = 2\n")
    assert suite.uncommitted_content([repo / "tasks" / "t1"])["untracked"] == ["tasks/t1/overlay/src/b.py"]


def test_a_root_outside_git_is_a_scratch_suite_and_is_skipped(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "x.txt").write_text("x\n")
    assert suite.uncommitted_content([scratch]) == {"ignored": [], "untracked": []}


@pytest.mark.parametrize(
    "name",
    [
        "golden-dev",
        "golden-heldout",
        "golden-heldout2",
        "golden-heldout3",
        "golden-rehearsal",
        "golden-candidates",
        "golden-dev-keeptests",  # G40
        "golden-probe1",
        "golden-probe2",
        "golden-probe3",
    ],
)
def test_no_golden_task_needs_content_git_ignores(name):
    """Every registered golden task, its base and protocol: nothing a clean checkout would lack
    because of a .gitignore (untracked drafts are allowed here; registration refuses them)."""
    tasks = suite.load_suite(suite=name)
    assert suite.uncommitted_content(suite.task_roots(tasks))["ignored"] == []


def test_registration_refuses_task_content_git_does_not_track(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    tasks_dir = repo / "tasks" / "t1"

    class _Task:
        root = tasks_dir
        base_root = tasks_dir
        protocol_root = tasks_dir

    with pytest.raises(suite.SuiteError, match=r"ignored by \.gitignore"):
        suite.assert_committed([_Task()])
    (repo / ".gitignore").write_text("__pycache__/\n")  # the negation's effect: dist/ is content
    with pytest.raises(suite.SuiteError, match="not committed"):
        suite.assert_committed([_Task()])
    suite.assert_committed([_Task()], allow_untracked=True)  # drafting
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "dist")
    suite.assert_committed([_Task()])
