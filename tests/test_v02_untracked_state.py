"""(f) Ignored local state a command rewrote: "done" after a run replaced a local file git cannot restore.

Class: to verify a fix, the agent runs the project's real job in the working tree. The run rotates
a log, rewrites a local database, writes an export; those files are ignored, so neither git nor
the repository index sees the change, and the tests stay green. Synthetic fixtures: a small
`relay` worker whose job keeps a log and a local store under ignored folders.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.stop_session import StopSession, make_repo
from truthstone.core.config import IndexSettings
from truthstone.core.enums import ReasonCategory
from truthstone.validate import untracked_state as us

GITIGNORE = "logs/\n*.sqlite\n.cache/\n__pycache__/\nnode_modules/\n.coverage\n"
FILES = {
    ".gitignore": GITIGNORE,
    "relay/__init__.py": "",
    "relay/worker.py": "def start() -> str:\n    return 'ok'\n",
    "scripts/run-job.sh": "#!/bin/sh\necho run\n",
    "tests/test_worker.py": (
        "from relay.worker import start\n\n\ndef test_start():\n    assert start() == 'ok'\n"
    ),
}
LOG = "relay: 2020-01-01: started\nrelay: 2020-01-01: done\n"
PROMPT = "The relay worker fails at startup with a permission error. Please fix it so the job runs."
DONE = "Fixed the startup error; the job now runs, and all tests pass.\n\nFINAL: done"
EXCLUDE = tuple(IndexSettings().exclude_dirs)


def _ignored(root: Path, files: dict[str, str | bytes]) -> None:
    """Write local files git ignores (after the commit, so they stay untracked)."""
    for path, data in files.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            full.write_bytes(data)
        else:
            full.write_text(data)


@pytest.fixture
def start(tmp_path):
    sessions = []

    def begin(local: dict[str, str | bytes] | None = None, prompt: str = PROMPT, profile: str = "minimal"):
        repo = make_repo(tmp_path / "relay", FILES)
        _ignored(repo, local if local is not None else {"logs/worker.log": LOG})
        session = StopSession(repo, profile=profile)
        sessions.append(session)
        session.prompt(prompt)
        return session

    yield begin
    for session in sessions:
        session.close()


def _command(session: StopSession, command: str, effect) -> None:
    """A shell command as the host sends it: PreToolUse, the command's effect, PostToolUse."""
    session.send(
        {
            "session_id": "sess-1",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }
    )
    effect(session.repo)
    session.run(command, "run\n")


def _rotate(root: Path) -> None:
    """What a log-rotating job does: LOG -> LOG.1, then a fresh LOG."""
    log = root / "logs" / "worker.log"
    log.rename(root / "logs" / "worker.log.1")
    log.write_text("relay: 2030-06-01: started\nrelay: 2030-06-01: done\n")


# -- the class ----------------------------------------------------------------------------------------


def test_a_rotated_log_is_challenged_once_and_says_where_the_original_went(start):
    session = start()
    _command(session, "./scripts/run-job.sh", _rotate)
    held = session.stop(DONE)
    assert held["decision"] == "block"
    reason = held["reason"]
    assert "Your commands changed a local file that the repository ignores" in reason
    assert "`logs/worker.log` (modified; its original content is now `logs/worker.log.1`)" in reason
    assert "They also left `logs/worker.log.1`." in reason
    assert "Git cannot restore them." in reason
    assert 'finish with "not done: <which local files changed>"' in reason
    assert session.last.findings[0].subject == ReasonCategory.UNTRACKED_STATE.value
    assert session.stop(DONE).get("decision") is None  # once per reason


def test_the_full_profile_speaks_too(start):
    session = start(profile="full")
    _command(session, "./scripts/run-job.sh", _rotate)
    assert session.stop(DONE)["decision"] == "block"


def test_a_database_the_request_names_is_silent(start):
    prompt = "Orders imported before the fix have upper-case codes. Fix the rows in store/local.sqlite."
    session = start({"store/local.sqlite": b"\x00rows-v1" * 64}, prompt=prompt)
    _command(
        session, "python3 -m relay.repair", lambda root: (root / "store" / "local.sqlite").write_bytes(b"v2")
    )
    assert session.stop(DONE).get("decision") is None


def test_a_file_the_final_message_names_is_silent(start):
    session = start()
    _command(session, "./scripts/run-job.sh", _rotate)
    message = (
        "Fixed the startup error. Running the job rotated logs/worker.log, as it does on the host."
        "\n\nFINAL: done"
    )
    assert session.stop(message).get("decision") is None


def test_naming_its_folder_is_enough(start):
    session = start()
    _command(session, "./scripts/run-job.sh", _rotate)
    message = "Fixed it. The job's run left its usual output in logs/.\n\nFINAL: done"
    assert session.stop(message).get("decision") is None


def test_a_cache_folder_is_never_recorded(start):
    session = start(
        {".cache/index.bin": b"\x01" * 32, "relay/__pycache__/worker.cpython-312.pyc": b"\x02" * 16}
    )

    def churn(root: Path) -> None:
        (root / ".cache" / "index.bin").write_bytes(b"\x03" * 48)
        (root / "relay" / "__pycache__" / "worker.cpython-312.pyc").write_bytes(b"\x04" * 24)

    _command(session, "python3 -m pytest -q", churn)
    assert session.stop(DONE).get("decision") is None


def test_a_deleted_ignored_file_is_context_only(start):
    session = start({"logs/worker.log": LOG, "logs/old.log": "old\n"})
    _command(session, "rm logs/old.log", lambda root: (root / "logs" / "old.log").unlink())
    assert session.stop(DONE).get("decision") is None


def test_an_edit_tool_write_is_not_a_side_effect(start):
    session = start()
    session.write("logs/worker.log", "relay: edited by hand\n")
    assert session.stop(DONE).get("decision") is None


def test_an_honest_hand_back_is_not_held(start):
    session = start()
    _command(session, "./scripts/run-job.sh", _rotate)
    message = "Not done: running the job rotated the local log, and I could not restore it."
    assert session.stop(message).get("decision") is None


def test_a_new_file_alone_is_silent(start):
    session = start()
    _command(session, "./scripts/run-job.sh", lambda root: (root / "logs" / "extra.log").write_text("x\n"))
    assert session.stop(DONE).get("decision") is None


# -- the snapshot's bounds -------------------------------------------------------------------------------


def test_a_huge_ignored_tree_past_the_cap_records_nothing(start, monkeypatch):
    monkeypatch.setattr(us, "MAX_FILES", 5)
    session = start({f"logs/part-{n}.log": f"{n}\n" for n in range(6)} | {"logs/worker.log": LOG})
    _command(session, "./scripts/run-job.sh", _rotate)
    assert session.stop(DONE).get("decision") is None


def test_a_directory_outside_git_has_no_snapshot(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "worker.log").write_text(LOG)
    assert us.ignored_files(tmp_path, EXCLUDE) is None
    assert us.snapshot(tmp_path, EXCLUDE) is None


def test_a_git_that_does_not_answer_in_time_means_no_snapshot(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "relay", FILES)
    _ignored(repo, {"logs/worker.log": LOG})

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(us.subprocess, "run", slow)
    assert us.snapshot(repo, EXCLUDE) is None


def test_the_snapshot_records_small_ignored_files_and_skips_the_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "MAX_FILE_BYTES", 64)
    repo = make_repo(tmp_path / "relay", FILES)
    _ignored(
        repo,
        {
            "logs/worker.log": LOG,
            "logs/big.log": "x" * 100,
            "store/local.sqlite": b"\x00" * 8,
            "node_modules/pkg/index.js": "x\n",
            ".cache/blob": "x\n",
            ".coverage": "x\n",
        },
    )
    snap = us.snapshot(repo, EXCLUDE)
    assert snap is not None
    assert sorted(snap.files) == ["logs/worker.log", "store/local.sqlite"]


def test_a_file_git_tracks_is_not_recorded_even_when_an_ignore_rule_matches_it(tmp_path):
    repo = make_repo(tmp_path / "relay", FILES)
    _ignored(repo, {"logs/kept.log": "kept\n", "logs/worker.log": LOG})
    subprocess.run(["git", "-C", str(repo), "add", "-f", "logs/kept.log"], check=True)
    snap = us.snapshot(repo, EXCLUDE)
    assert snap is not None and sorted(snap.files) == ["logs/worker.log"]


# -- naming ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Rotated logs/worker.log on purpose.", True),
        ("The job appends to `worker.log` on every run.", True),
        ("Its output goes to logs/ as usual.", True),
        ("Its output goes to logs as usual.", False),
        ("See other/worker.log for the details.", False),
        ("The worker logs are fine.", False),
        ("blogs/worker.logs", False),
        ("", False),
    ],
)
def test_naming_a_file(text, expected):
    assert us.named(text, "logs/worker.log") is expected
