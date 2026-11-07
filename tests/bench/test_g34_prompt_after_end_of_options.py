"""G34: the prompt reaches `codex exec` after `--`, the end of its options.

A request about a command-line flag can start with that flag ("--width rejects 0 ..."). Passed
as the bare last argument, `codex exec` parsed it as an unknown option and exited 2 before any
model call, in both arms, on every attempt. After `--` it is always the prompt.
"""

from __future__ import annotations

from pathlib import Path

from truthstone.bench.codex.agents import CodexExecAgent, CodexSettings


def _argv(prompt: str) -> list[str]:
    agent = CodexExecAgent("/usr/bin/codex", CodexSettings(model="m", effort="medium"))
    return agent.argv(prompt, Path("/r"), Path("/t"), Path("/t/last.txt"), extra=["-c", "x=1"])


def test_a_prompt_that_starts_with_a_flag_comes_after_the_end_of_options():
    argv = _argv("--width rejects 0; make it accept any positive number")
    assert argv[-2:] == ["--", "--width rejects 0; make it accept any positive number"]


def test_every_prompt_is_the_last_argument_after_the_marker_and_the_options_come_first():
    argv = _argv("Fix the parser.")
    assert argv[-1] == "Fix the parser." and argv[-2] == "--"
    assert argv.index("--") == len(argv) - 2  # nothing the harness passes follows the marker
    assert argv[argv.index("-c", 6) + 1 :].count("--") == 1
    assert argv[-4:-2] == ["-c", "x=1"]  # extra options still precede it
