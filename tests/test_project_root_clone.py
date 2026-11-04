"""A local clone must not take over its origin's project root (product regression, for core).

Found by a golden benchmark screen cell (an agent committed in a clone): a project's identity is its git
remote, else its path. A repository without a remote is identified by its path; a clone made from
it has that path as its `origin`, so it gets the same identity, and registering the clone runs
`ON CONFLICT(id) DO UPDATE SET root=excluded.root`: the original's project row now names the clone.
Every event is still recorded under the right id, so nothing is unguarded, but anything that finds a
project by the checkout it is run from (reports, the benchmark's evidence reader) loses the
original's history. Fix-agnostic: keep the first root, or keep a local-path remote out of identity.
Strict xfail until core fixes it; then drop the marker.
"""

from __future__ import annotations

import subprocess

import pytest

from truthstone.core.store import Database, ProjectStore, project_identity


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


@pytest.mark.xfail(strict=True, reason="core: a local clone shares its origin's identity and moves its root")
def test_a_local_clone_does_not_take_over_its_origins_project_root(tmp_path):
    origin = tmp_path / "work" / "repo"
    origin.mkdir(parents=True)
    (origin / "a.py").write_text("x = 1\n")
    _git("-C", str(origin), "init", "-q")
    _git("-C", str(origin), "add", ".")
    _git("-C", str(origin), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    db = Database(tmp_path / "truthstone.db")
    original = ProjectStore(db, project_identity(origin))
    clone = tmp_path / "elsewhere" / "repo-release"
    _git("clone", "-q", str(origin), str(clone))
    ProjectStore(db, project_identity(clone))
    (root,) = db._conn.execute("SELECT root FROM projects WHERE id = ?", (original.project_id,)).fetchone()
    assert root == str(origin.resolve())
