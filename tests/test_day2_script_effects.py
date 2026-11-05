"""Day 2, M10: running a repository script that moves or deletes files git ignores.

Class: the agent fixes a job and runs the real job by hand to check it; the job rotates its
log (or deletes a database, or truncates an export) in the working copy, and those files are
ignored data nothing restores. Synthetic repositories only: a small `relay` service.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from truthstone.adapters.codex import translate as codex
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.validate import script_effects

JOB = """#!/bin/sh
# The hourly job: rotate the log, then sync.
set -eu
log="var/log/relay.log"
db="${RELAY_DB:-data/relay.db}"
mkdir -p var/log
./scripts/rotate.sh "$log"
echo "relay: syncing into $db" >>"$log"
"""
ROTATE = """#!/bin/sh
set -eu
log="$1"
keep=5
if [ ! -f "$log" ]; then
    exit 0
fi
i=$keep
while [ "$i" -gt 1 ]; do
    previous=$((i - 1))
    if [ -f "$log.$previous" ]; then
        mv "$log.$previous" "$log.$i"
    fi
    i=$previous
done
mv "$log" "$log.1"
"""


def _repo(tmp_path: Path, files: dict[str, str], ignore: str = "var/\n*.db\nbuild/\n") -> Path:
    root = tmp_path / "relay"
    for path, text in {".gitignore": ignore, **files}.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    return root


def _ignored(root: Path):
    def ignored(rel: str) -> bool:
        out = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", rel], check=False)
        return out.returncode == 0

    return ignored


class _Event:
    tool = "Bash"

    def __init__(self, command: str) -> None:
        self.command = command

    def arg(self, name: str):
        return self.command if name == "command" else None


def _check(root: Path, command: str):
    return script_effects.check(_Event(command), root, _ignored(root))


@pytest.fixture
def relay(tmp_path):
    root = _repo(
        tmp_path,
        {
            "scripts/job.sh": JOB,
            "scripts/rotate.sh": ROTATE,
            "var/log/relay.log": "relay: 2026-11-01: done\n",
        },
    )
    return root


@pytest.mark.parametrize(
    "command", ["./scripts/job.sh", "scripts/job.sh", "sh scripts/job.sh", "bash ./scripts/job.sh"]
)
def test_running_a_job_that_rotates_an_ignored_log_needs_sign_off(relay, command):
    (finding,) = _check(relay, command)
    assert finding.subject == "script-destroys-ignored-files"
    assert "var/log/relay.log" in finding.summary and "scripts/rotate.sh" in finding.detail


def test_the_script_called_directly_with_the_log_needs_sign_off(relay):
    assert _check(relay, "./scripts/rotate.sh var/log/relay.log")
    assert not _check(relay, "./scripts/rotate.sh var/log/other.log")  # nothing there to lose


def test_a_tracked_file_comes_back_with_git(tmp_path):
    root = _repo(
        tmp_path,
        {"scripts/job.sh": JOB, "scripts/rotate.sh": ROTATE, "var/log/relay.log": "x\n"},
        ignore="*.db\n",
    )
    assert not _check(root, "./scripts/job.sh")


def test_appending_to_a_log_is_not_destroying_it(tmp_path):
    root = _repo(
        tmp_path,
        {
            "scripts/job.sh": '#!/bin/sh\nlog="var/log/relay.log"\necho done >>"$log"\n',
            "var/log/relay.log": "x\n",
        },
    )
    assert not _check(root, "./scripts/job.sh")


def test_truncating_an_ignored_file_needs_sign_off(tmp_path):
    root = _repo(
        tmp_path,
        {"scripts/reset.sh": '#!/bin/sh\necho "" > var/log/relay.log\n', "var/log/relay.log": "history\n"},
    )
    assert _check(root, "sh scripts/reset.sh")


def test_cleaning_build_output_is_routine(tmp_path):
    root = _repo(
        tmp_path,
        {"scripts/clean.sh": "#!/bin/sh\nrm -f build/app.o build/app\n", "build/app.o": "obj"},
    )
    assert not _check(root, "./scripts/clean.sh")


def test_an_unresolvable_target_is_not_guessed(tmp_path):
    root = _repo(
        tmp_path,
        {
            "scripts/purge.sh": '#!/bin/sh\nfor f in "$@"; do rm "$f"; done\nrm "$(cat target)"\n',
            "var/a.db": "x",
        },
    )
    assert not _check(root, "./scripts/purge.sh var/a.db")


@pytest.mark.parametrize(
    "command",
    [
        "chmod +x scripts/job.sh",
        "cat scripts/job.sh",
        "sh -n scripts/job.sh",
        "bash -c 'echo hi'",
        "make test",
    ],
)
def test_commands_that_do_not_run_a_repository_script_are_silent(relay, command):
    assert not _check(relay, command)


def test_through_the_guard_it_is_a_sign_off(relay):
    guard = Guard(Settings(profile="minimal"))
    try:
        guard.workspace(relay).index.ready(timeout=30)
        base = {"session_id": "s-1", "turn_id": "t-1", "cwd": str(relay), "transcript_path": None}
        codex.handle_payload(
            guard, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "The job fails; fix it."}
        )
        out = codex.handle_payload(
            guard,
            {
                **base,
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "./scripts/job.sh"},
            },
        )
        assert out, "the sign-off reaches the agent"
        assert "var/log/relay.log" in str(out)
        quiet = codex.handle_payload(
            guard,
            {
                **base,
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "chmod +x scripts/job.sh"},
            },
        )
        assert quiet == {}
    finally:
        guard.close()
