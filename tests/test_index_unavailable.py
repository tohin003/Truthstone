"""The index refuses trees it must not index, and says so (R12).

A session started in `~` used to index up to 200,000 files: on a synthetic 205k-file
home, SessionStart blocked for 5 s, the build took 24.6 s and 131 MB, and every post-Bash
sweep re-walked the tree for ~22 s. Now the home directory and the filesystem root are
refused outright, a non-git walk stops once it passes `scanner.NON_GIT_FILE_LIMIT`
files, and in every such case the index is "unavailable": it never reports itself
built, so every question resolves to "unknown", and it is never swept.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from agentguard.core.config import Settings
from agentguard.core.engine import Guard
from agentguard.core.enums import EventType
from agentguard.core.events import AgentEvent
from agentguard.repo import IndexDelta, RepoIndex, scanner


def _tree(root: Path, n_files: int) -> Path:
    for i in range(n_files):
        directory = root / "pkg" / f"d{i // 25}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n")
    return root


def _no_scan(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Make any scan fail the test (and record it), so a regression cannot walk a disk."""
    calls: list[Path] = []

    def refuse(root, settings=None):
        calls.append(root)
        raise AssertionError(f"scanned {root}")

    monkeypatch.setattr(scanner, "scan", refuse)
    return calls


def _assert_unknown(index: RepoIndex) -> None:
    """An unavailable index answers nothing and sweeps nothing."""
    assert index.is_built is False
    assert index.ready(timeout=5.0) is False
    assert index.files == {}
    assert index.has_symbol("f1") is False
    assert index.knows_type("anything") is False
    assert index.refresh() == {"added": 0, "modified": 0, "removed": 0}
    assert index.refresh_delta() == IndexDelta(swept=False)
    assert index.refresh_path("pkg/d0/m1.py") is False


def _event(kind: EventType, workspace: Path, **fields) -> AgentEvent:
    return AgentEvent(
        event=kind, agent="claude-code", workspace=str(workspace), session_id="s-home", **fields
    )


def test_home_directory_is_not_indexed(tmp_path, monkeypatch):
    home = _tree(tmp_path / "home", 40)
    monkeypatch.setenv("HOME", str(home))
    scans = _no_scan(monkeypatch)

    started = time.perf_counter()
    index = RepoIndex(home).build_async()
    assert index.ready(timeout=5.0) is False
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0, f"unavailability took {elapsed:.2f}s to establish"
    assert index.status == "unavailable: the workspace is the home directory"
    assert index._build_thread is None, "no background build is started at all"
    _assert_unknown(index)
    assert index.build().is_built is False, "an explicit build is refused too"
    assert index.summary()["status"] == index.status
    assert scans == []


def test_home_directory_is_refused_by_the_engine_without_a_sweep(tmp_path, monkeypatch):
    home = _tree(tmp_path / "home", 40)
    monkeypatch.setenv("HOME", str(home))
    scans = _no_scan(monkeypatch)

    guard = Guard(Settings())
    try:
        started = time.perf_counter()
        guard.handle(_event(EventType.SESSION_START, home))
        session_start_s = time.perf_counter() - started
        ws = guard.workspace(home)
        assert ws.index.status.startswith("unavailable: ")

        started = time.perf_counter()
        decision = guard.handle(
            _event(
                EventType.POST_TOOL_USE,
                home,
                tool="Bash",
                arguments={"command": "ls"},
                result={"stdout": "", "stderr": "", "interrupted": False},
            )
        )
        post_bash_s = time.perf_counter() - started
    finally:
        guard.close()

    # SessionStart no longer waits up to 5 s for a build; post-Bash re-walks nothing.
    assert session_start_s < 1.0, session_start_s
    assert post_bash_s < 1.0, post_bash_s
    assert decision.is_silent
    assert scans == []


def test_filesystem_root_is_not_indexed(monkeypatch):
    scans = _no_scan(monkeypatch)

    index = RepoIndex(Path("/").resolve()).build_async()

    assert index.status == "unavailable: the workspace is the filesystem root"
    _assert_unknown(index)
    assert scans == []


def test_a_project_under_home_is_still_indexed(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = _tree(home / "project", 10)
    monkeypatch.setenv("HOME", str(home))

    index = RepoIndex(project).build_async()

    assert index.ready(timeout=30) is True
    assert index.status == "ready"
    assert index.has_symbol("f1")


def test_huge_non_git_tree_becomes_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "NON_GIT_FILE_LIMIT", 50)
    huge = _tree(tmp_path / "huge", 120)

    index = RepoIndex(huge).build_async()

    assert index.ready(timeout=30) is False
    assert index.status == "unavailable: not a git repository and more than 50 files"
    _assert_unknown(index)
    # Not retried in the background: a refused tree stays refused for the session.
    first = index._build_thread
    index.build_async()
    assert index._build_thread is first, "no second walk is started"
    assert index.status.startswith("unavailable: ")


def test_a_tree_that_grows_past_the_limit_stops_answering(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "NON_GIT_FILE_LIMIT", 50)
    root = _tree(tmp_path / "growing", 40)
    index = RepoIndex(root).build()
    assert index.status == "ready"
    assert index.has_symbol("f1")

    _tree(root, 80)  # a generator dumps files into the tree
    delta = index.refresh_delta()

    assert delta.swept is False
    assert index.status.startswith("unavailable: ")
    _assert_unknown(index)


def test_git_repo_is_not_capped_by_the_non_git_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "NON_GIT_FILE_LIMIT", 50)
    repo = _tree(tmp_path / "repo", 120)
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", *args],
            cwd=repo,
            check=True,
            capture_output=True,
        )

    index = RepoIndex(repo).build_async()

    assert index.ready(timeout=30) is True
    assert index.status == "ready"
    assert len(index.files) == 120
    assert index.refresh_delta().swept is True


def test_status_moves_from_building_to_ready(tmp_path):
    index = RepoIndex(_tree(tmp_path / "small", 3))
    assert index.status == "building"
    index.build()
    assert index.status == "ready"


def test_a_failed_build_is_reported_not_silent(tmp_path, monkeypatch, caplog):
    def broken(root, settings=None):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(scanner, "scan", broken)
    index = RepoIndex(_tree(tmp_path / "small", 3)).build_async()

    assert index.ready(timeout=30) is False
    assert index.status == "unavailable: index build failed (RuntimeError)"
    assert index.is_built is False
    assert "not indexing" in caplog.text and "index build failed (RuntimeError)" in caplog.text
