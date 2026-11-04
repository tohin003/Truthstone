"""`doctor` is honest across hosts (H8).

Cursor and GitHub Copilot CLI read `.claude/settings*.json`. Their command hooks may run
Truthstone's shim while its HTTP tool hooks are never called, so the integration reads as
"installed" and guards nothing. Not verified live either way, so `doctor` says so as a
warning — never as a problem.
"""

from __future__ import annotations

import re
import stat

from tests.test_doctor import doctor_env, run_doctor  # noqa: F401 - fixture


def _problems(output: str) -> int:
    match = re.search(r"(\d+) problem\(s\) found", output)
    return int(match.group(1)) if match else 0


def test_doctor_notes_unverified_hosts(doctor_env, tmp_path, monkeypatch):  # noqa: F811 - fixture
    _, _, project = doctor_env
    user = tmp_path / "user"
    user.mkdir()
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("HOME", str(user))
    monkeypatch.setenv("PATH", f"{empty_bin}:/usr/bin:/bin")

    code_before, before = run_doctor()
    assert "other hosts" not in before and "Cursor" not in before and "Copilot" not in before

    (user / ".copilot").mkdir()
    (project / ".cursor").mkdir()
    tools = tmp_path / "bin"
    tools.mkdir()
    for name in ("cursor-agent", "copilot"):
        tool = tools / name
        tool.write_text("#!/bin/sh\nexit 0\n")
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tools}:/usr/bin:/bin")

    code_after, after = run_doctor()
    assert "other hosts" in after
    cursor = next(line for line in after.splitlines() if "Cursor found" in line)
    copilot = next(line for line in after.splitlines() if "GitHub Copilot CLI found" in line)
    assert "./.cursor" in cursor and "`cursor-agent` on PATH" in cursor
    assert "~/.copilot" in copilot and "`copilot` on PATH" in copilot
    for line in (cursor, copilot):
        assert line.lstrip().startswith("!"), "a warning"
        assert "only verified for Claude Code" in line and "is unverified" in line
    assert ".claude/settings*.json" in cursor
    assert (code_after, _problems(after)) == (code_before, _problems(before)), "never an error"
