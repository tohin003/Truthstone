"""A local clone must not take over its origin's project root (product regression, for core).

Found by a golden benchmark screen cell (an agent committed in a clone): a project's identity is its git
remote, else its path. A repository without a remote is identified by its path; a clone made from
it has that path as its `origin`, so it got the same identity, and registering the clone ran
`ON CONFLICT(id) DO UPDATE SET root=excluded.root`: the original's project row then named the clone.
Every event was still recorded under the right id, so nothing was unguarded, but anything that finds a
project by the checkout it is run from (reports, the benchmark's evidence reader) lost the
original's history.

Fixed both ways: a remote that is a path on this machine is not a project's identity (the clone is
its own project), and a recorded root is kept while it still exists — it moves only when the
project did, and that move is reported (R9: `/health`, `truthstone doctor`, the hooks' notices).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from truthstone.core.store import Database, ProjectIdentity, ProjectStore, is_local_remote, project_identity
from truthstone.daemon import degraded


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "a.py").write_text("x = 1\n")
    _git("-C", str(path), "init", "-q")
    _git("-C", str(path), "add", ".")
    _git("-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return path


def _root(db: Database, project_id: str) -> str:
    (root,) = db._conn.execute("SELECT root FROM projects WHERE id = ?", (project_id,)).fetchone()
    return root


@pytest.fixture(autouse=True)
def _clean_registry():
    degraded.clear("project_root_moved")
    yield
    degraded.clear("project_root_moved")


def test_a_local_clone_does_not_take_over_its_origins_project_root(tmp_path):
    origin = _repo(tmp_path / "work" / "repo")
    db = Database(tmp_path / "truthstone.db")
    original = ProjectStore(db, project_identity(origin))
    clone = tmp_path / "elsewhere" / "repo-release"
    _git("clone", "-q", str(origin), str(clone))
    cloned = ProjectStore(db, project_identity(clone))
    assert cloned.project_id != original.project_id  # a local path is not an identity
    assert _root(db, original.project_id) == str(origin.resolve())
    assert _root(db, cloned.project_id) == str(clone.resolve())


@pytest.mark.parametrize(
    "remote, local",
    [
        ("/Users/me/work/repo", True),
        ("../repo", True),
        ("repo.git", True),
        ("file:///srv/git/repo.git", True),
        ("C:\\work\\repo", True),
        ("git@github.com:org/repo.git", False),
        ("github.com:org/repo.git", False),
        ("https://github.com/org/repo.git", False),
        ("ssh://git@example.com:2222/org/repo.git", False),
        ("", False),
    ],
)
def test_which_remotes_are_paths_on_this_machine(remote, local):
    assert is_local_remote(remote) is local


def _identity(root: Path, remote: str = "github.com:org/shared.git") -> ProjectIdentity:
    return ProjectIdentity(id="shared0000000000", root=str(root), name=root.name, git_remote=remote)


def test_a_second_checkout_of_the_same_project_keeps_the_first_root(tmp_path):
    first, second = tmp_path / "a" / "shared", tmp_path / "b" / "shared"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    db = Database(tmp_path / "truthstone.db")
    ProjectStore(db, _identity(first))
    ProjectStore(db, _identity(second))
    assert _root(db, "shared0000000000") == str(first)
    assert not any(r.code == "project_root_moved" for r in degraded.reasons())


def test_a_project_that_moved_follows_and_the_move_is_reported(tmp_path):
    old, new = tmp_path / "old" / "shared", tmp_path / "new" / "shared"
    old.mkdir(parents=True)
    db = Database(tmp_path / "truthstone.db")
    ProjectStore(db, _identity(old))
    shutil.move(str(old), str(new))
    ProjectStore(db, _identity(new))
    assert _root(db, "shared0000000000") == str(new)
    (reason,) = [r for r in degraded.reasons() if r.code == "project_root_moved"]
    assert str(new) in reason.message and reason.detail["previous"] == str(old)
