"""A cell's guard evidence is found by its sessions even when the project's root has moved.

In the candidate screen two cells were voided as "no hook evidence" although the guard had
recorded every event: the agent cloned the cell's repository into /private/tmp (Codex's sandbox
makes `.git` read-only, so it committed in a clone), the clone's `origin` is the cell's path, so the
clone has the same project identity, and the project's recorded root moved to the clone. A lookup
by root found nothing; the host's session ids, which the logging hook records, find everything.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from truthstone.bench.codex import guards
from truthstone.core.store import Database, ProjectStore, project_identity


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


def test_evidence_follows_the_session_when_a_clone_takes_over_the_project_root(tmp_path):
    repo = tmp_path / "cell" / "w"
    repo.mkdir(parents=True)
    (repo / "a.py").write_text("x = 1\n")
    _git("-C", str(repo), "init", "-q")
    _git("-C", str(repo), "add", ".")
    _git("-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    db_path = tmp_path / "guard" / "truthstone.db"
    db_path.parent.mkdir()
    db = Database(db_path)
    store = ProjectStore(db, project_identity(repo))
    store.open_session("thread-1", "codex", str(repo), {"observe_only": True})
    db.write(
        "INSERT INTO events(id, project_id, session_id, task_id, type, agent, tool, arguments, ts) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        ("e1", store.project_id, "thread-1", None, "session_start", "codex", None, "{}", 1.0),
    )
    clone = tmp_path / "tmp" / "w-release"
    _git("clone", "-q", str(repo), str(clone))
    ProjectStore(db, project_identity(clone))  # the agent works in its clone: same identity
    (root,) = db._conn.execute("SELECT root FROM projects WHERE id = ?", (store.project_id,)).fetchone()
    assert Path(root) == clone.resolve()  # the product's behaviour today: the root moved

    lost = guards.read_guard_db(db_path, repo)
    assert lost.events == {}  # what voided the two cells

    trace = tmp_path / "hooks"
    trace.mkdir()
    (trace / "hooks.jsonl").write_text(json.dumps({"event": "SessionStart", "session_id": "thread-1"}) + "\n")
    evidence = guards.read_recorder(trace, guards.HookEvidence())
    found = guards.read_guard_db(db_path, repo, evidence, evidence.recorder_sessions)
    assert found.events == {"session_start": 1} and found.sessions[0]["observe_only"] is True
