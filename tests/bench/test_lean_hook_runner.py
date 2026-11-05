"""T6 times the shipped path: the hook timer's runner takes the plugin launcher's lean path."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from truthstone.bench.codex import guards


def _runtime_stub(tmp_path: Path) -> Path:
    stub = tmp_path / "runtime"
    stub.write_text("#!/bin/sh\necho runtime:$1\n")
    stub.chmod(0o755)
    return stub


def _run(hook: Path, event: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([str(hook), event], input=b"{}", capture_output=True, env=env, timeout=30)


def test_hot_events_take_the_lean_forwarder_and_the_rest_the_runtime(tmp_path: Path):
    data = tmp_path / "plugin-data"
    (data / "lean").mkdir(parents=True)
    (data / "lean" / "forward.py").write_text(
        "def run(args, stdin, stdout):\n    stdout.write(b'lean:' + ' '.join(args).encode())\n    return 2\n"
    )
    hook = guards.write_lean_hook(tmp_path, Path(sys.executable), _runtime_stub(tmp_path))
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PLUGIN_DATA": str(data)}
    hot = _run(hook, "pre-tool-use", env)
    assert hot.returncode == 0 and hot.stdout == b"lean:--timeout 4"  # always exits 0, like the launcher
    assert _run(hook, "session-end", env).stdout == b"lean:--timeout 2"
    assert _run(hook, "session-start", env).stdout.strip() == b"runtime:session-start"
    assert _run(hook, "user-prompt-submit", env).stdout.strip() == b"runtime:user-prompt-submit"


def test_without_the_lean_forwarder_everything_goes_to_the_runtime(tmp_path: Path):
    hook = guards.write_lean_hook(tmp_path, Path(sys.executable), _runtime_stub(tmp_path))
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PLUGIN_DATA": str(tmp_path / "empty")}
    assert _run(hook, "pre-tool-use", env).stdout.strip() == b"runtime:pre-tool-use"
    env.pop("PLUGIN_DATA")
    assert _run(hook, "stop", env).stdout.strip() == b"runtime:stop"


def test_the_runner_is_rewritten_only_when_it_changes(tmp_path: Path):
    runtime = _runtime_stub(tmp_path)
    first = guards.write_lean_hook(tmp_path, Path(sys.executable), runtime)
    mtime = first.stat().st_mtime_ns
    assert guards.write_lean_hook(tmp_path, Path(sys.executable), runtime).stat().st_mtime_ns == mtime
    assert os.access(first, os.X_OK)
    assert first.read_text().startswith(f"#!{sys.executable} -IS\n")


def test_a_developer_only_notice_is_not_the_agents():
    assert guards.developer_only('{"systemMessage": "Truthstone is observe-only"}')
    mixed = '{"systemMessage": "x", "hookSpecificOutput": {"additionalContext": "y"}}'
    assert not guards.developer_only(mixed)
    assert not guards.developer_only('{"decision": "block", "reason": "r"}')
    assert not guards.developer_only("plain text is context on SessionStart")


def test_g20_a_codex_apply_patch_denial_reads_past_its_file_line():
    from truthstone.bench.codex import transcript

    patch = "blocked by PreToolUse hook: [src/x.py]\nTruthstone: before editing: the request assumes `y`."
    shell = "blocked by PreToolUse hook: Truthstone: `git clean -fdx` needs the developer's sign-off."
    assert transcript._HOOK_DENIAL.search(patch).group(1).startswith("Truthstone: before editing")
    assert transcript._HOOK_DENIAL.search(shell).group(1).startswith("Truthstone: `git clean")
