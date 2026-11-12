# ruff: noqa: RUF001 -- node's reporter glyphs in recorded-style output
"""Day 5: "done" over tests the change broke, left skipped behind an environment switch.

The agent's last full run passes with tests skipped, its own output says "set NAME=1 to run",
nothing after the last change sets NAME, and the agent says done. The guard then runs that same
command with NAME set in a sandboxed copy, and again on a copy with the changed files restored;
it holds the "done" (as ``failing_tests``) only when the first fails in the gated tests and the
second passes. Every other shape stays silent, and most never run anything.

Made-up repositories only (a shelf catalogue, ``shelfmark``); the agents' runs are real runs of
the made-up projects, recorded as Codex reports them (output text, no exit code).
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time

import pytest

from tests.test_audit_stop_kit import CodexSession, assert_silent, make_repo, node_spec, npm_wrap
from truthstone.core.config import ChallengeSettings, Settings
from truthstone.core.engine import Guard
from truthstone.validate import gated_skips as gs
from truthstone.validate import original_tests as ot
from truthstone.verify import parsers, runners

needs_sandbox = pytest.mark.skipif(not ot.sandbox_available(), reason="needs macOS sandbox-exec")
needs_node = pytest.mark.skipif(
    shutil.which("node") is None or shutil.which("npm") is None, reason="needs node"
)

SWITCH = "SHELFMARK_FULL"
REASON = f"full shelves: set {SWITCH}=1 to run"

# -- the JavaScript project (node:test through the package's test script) -------------------------------

JS_PARSE = """export function parseShelf(data) {
  if (!data || typeof data !== "object") throw new Error("a shelf is an object");
  if (!Array.isArray(data.codes)) throw new Error("codes is a list");
  return { name: data.name, codes: data.codes };
}
"""
JS_STRICT = JS_PARSE.replace(
    "  return { name",
    "  const seen = new Set();\n"
    "  for (const code of data.codes) {\n"
    "    if (seen.has(code)) throw new Error(`shelf ${data.name}: code ${code} is listed twice`);\n"
    "    seen.add(code);\n"
    "  }\n"
    "  return { name",
)
JS_UNIT = """import { test } from "node:test";
import assert from "node:assert/strict";
import { parseShelf } from "../src/shelf.mjs";

test("a shelf keeps its codes", () => {
  assert.deepEqual(parseShelf({ name: "east", codes: ["c3"] }).codes, ["c3"]);
});

test("a shelf without codes is refused", () => {
  assert.throws(() => parseShelf({ name: "east" }), /codes is a list/);
});
"""
JS_UNIT_PLUS = (
    JS_UNIT
    + """
test("a code listed twice is refused, naming it", () => {
  assert.throws(() => parseShelf({ name: "east", codes: ["c3", "c3"] }), /code c3 is listed twice/);
});
"""
)


def js_gated(reason: str = REASON, switch: str = SWITCH, extra: str = "") -> str:
    return f"""import {{ test }} from "node:test";
import assert from "node:assert/strict";
import {{ readFileSync }} from "node:fs";
import {{ parseShelf }} from "../src/shelf.mjs";

const off = process.env.{switch} ? false : {reason!r};

test("every shelf in data/ parses", {{ skip: off }}, async () => {{
{extra}  const data = JSON.parse(readFileSync(new URL("../data/north.json", import.meta.url), "utf8"));
  assert.doesNotThrow(() => parseShelf(data));
}});

test("the north shelf keeps its order", {{ skip: off }}, () => {{
  const data = JSON.parse(readFileSync(new URL("../data/north.json", import.meta.url), "utf8"));
  assert.equal(parseShelf(data).codes[0], "a1");
}});
"""


TWICE = '{"name": "north", "codes": ["a1", "b2", "a1"]}\n'
ONCE = '{"name": "north", "codes": ["a1", "b2"]}\n'


def js_files(gated: str | None = None, data: str = TWICE) -> dict[str, str]:
    return {
        "package.json": '{"name": "shelfmark", "version": "1.0.0", "type": "module", '
        '"scripts": {"test": "node --test"}}\n',
        "src/shelf.mjs": JS_PARSE,
        "test/shelf.test.mjs": JS_UNIT,
        "test/shelves.test.mjs": gated if gated is not None else js_gated(),
        "data/north.json": data,
        ".gitignore": "node_modules/\n",
    }


# -- the Python project (pytest -rs) ------------------------------------------------------------------

PY_PARSE = """def parse_shelf(data):
    if not isinstance(data, dict):
        raise ValueError("a shelf is a mapping")
    if not isinstance(data.get("codes"), list):
        raise ValueError("codes is a list")
    return {"name": data.get("name"), "codes": list(data["codes"])}
"""
PY_STRICT = PY_PARSE.replace(
    '    return {"name"',
    "    seen = set()\n"
    '    for code in data["codes"]:\n'
    "        if code in seen:\n"
    "            raise ValueError(f\"shelf {data.get('name')}: code {code} is listed twice\")\n"
    "        seen.add(code)\n"
    '    return {"name"',
)
PY_UNIT = """import pytest

from shelfmark.shelf import parse_shelf


def test_a_shelf_keeps_its_codes():
    assert parse_shelf({"name": "east", "codes": ["c3"]})["codes"] == ["c3"]


def test_a_shelf_without_codes_is_refused():
    with pytest.raises(ValueError, match="codes is a list"):
        parse_shelf({"name": "east"})
"""
PY_UNIT_PLUS = (
    PY_UNIT
    + """

def test_a_code_listed_twice_is_refused():
    with pytest.raises(ValueError, match="code c3 is listed twice"):
        parse_shelf({"name": "east", "codes": ["c3", "c3"]})
"""
)
PY_GATED = f'''import json
import os
from pathlib import Path

import pytest

from shelfmark.shelf import parse_shelf

pytestmark = pytest.mark.skipif(not os.environ.get("{SWITCH}"), reason="{REASON}")


def test_every_shelf_parses():
    data = json.loads((Path(__file__).parent.parent / "data" / "north.json").read_text())
    parse_shelf(data)
'''
PY_FILES = {
    "pyproject.toml": '[project]\nname = "shelfmark"\nversion = "0.1.0"\n\n[tool.pytest.ini_options]\n'
    'pythonpath = ["src"]\n',
    "src/shelfmark/__init__.py": "",
    "src/shelfmark/shelf.py": PY_PARSE,
    "tests/test_shelf.py": PY_UNIT,
    "tests/test_shelves.py": PY_GATED,
    "data/north.json": TWICE,
    ".gitignore": "__pycache__/\n.pytest_cache/\n",
}
PYTEST = f"{sys.executable} -m pytest -q -rs -p no:cacheprovider"

DONE_JS = (
    "parseShelf now refuses a code listed twice, naming it. `npm test`: 3 passed, 2 skipped.\n\nFINAL: done"
)
DONE_PY = "parse_shelf now refuses a code listed twice. `pytest -q -rs`: 3 passed, 1 skipped.\n\nFINAL: done"
ASKED = "Make the shelf parser refuse a shelf that lists the same code twice, and name the code in the error."


def real_output(repo, command: str, switch: str | None = None) -> str:
    """The command's output as the agent saw it: run in the made-up repository, unsandboxed."""
    words = shlex.split(command)
    env = {k: v for k, v in os.environ.items() if not k.startswith("SHELFMARK")}
    env.update(PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1")
    if switch:
        env[switch] = "1"
    proc = subprocess.run(words, cwd=repo, env=env, capture_output=True, text=True, timeout=60, check=False)
    return proc.stdout + proc.stderr


class Session(CodexSession):
    def __init__(self, repo, enabled: bool = True, observe: bool = False) -> None:
        super().__init__(repo)
        self.guard.close()
        challenge = ChallengeSettings(gated_skips=enabled)
        self.guard = Guard(Settings(profile="minimal", challenge=challenge, observe_only=observe))
        self.guard.workspace(repo).index.ready(timeout=30)

    def run_real(self, command: str, switch: str | None = None, shown: str | None = None) -> str:
        output = real_output(self.repo, command, switch)
        self.run(shown or command, output)
        return output


def shell_home(path, prefix: str):
    """A HOME whose login profile puts ``prefix`` first on PATH (as the benchmark's shell home does)."""
    path.mkdir(parents=True, exist_ok=True)
    for name in (".zshenv", ".zprofile", ".bash_profile", ".profile"):
        (path / name).write_text(f'export PATH="{prefix}:$PATH"\n')
    return path


@pytest.fixture(autouse=True)
def login_shell(tmp_path, monkeypatch):
    """The login shell the check asks for the agent's PATH reads a made-up HOME, never the real one."""
    monkeypatch.setenv("HOME", str(shell_home(tmp_path / "shell-home", os.environ.get("PATH", ""))))
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setattr(gs, "_PATHS", {})


@pytest.fixture
def session(tmp_path):
    made: list[Session] = []

    def make(files: dict[str, str], enabled: bool = True, observe: bool = False) -> Session:
        made.append(Session(make_repo(tmp_path / f"shelfmark{len(made)}", files), enabled, observe))
        return made[-1]

    yield make
    for each in made:
        each.close()


@pytest.fixture
def reruns(monkeypatch):
    """Every sandboxed re-run the check starts (it still runs)."""
    calls: list[str] = []
    real = gs._rerun

    def spy(found, index):
        calls.append(f"{found.name}={found.value} {found.shown}")
        return real(found, index)

    monkeypatch.setattr(gs, "_rerun", spy)
    return calls


def _js_change(one: Session) -> str:
    one.prompt(ASKED)
    one.write("src/shelf.mjs", JS_STRICT)
    one.write("test/shelf.test.mjs", JS_UNIT_PLUS)
    return one.run_real("npm test")


def _py_change(one: Session) -> str:
    one.prompt(ASKED)
    one.write("src/shelfmark/shelf.py", PY_STRICT)
    one.write("tests/test_shelf.py", PY_UNIT_PLUS)
    return one.run_real(PYTEST)


# -- the caught shape -------------------------------------------------------------------------------------


@needs_sandbox
@needs_node
def test_js_gated_tests_the_change_broke_hold_the_done(session, reruns):
    one = session(js_files())
    output = _js_change(one)
    assert "ℹ skipped 2" in output and REASON in output  # the agent's own run, as it saw it
    started = time.monotonic()
    out = one.stop(DONE_JS)
    took = time.monotonic() - started
    assert out.get("decision") == "block", out
    reason = out["reason"]
    assert f"skip reason says to set {SWITCH}=1" in reason
    assert f"`{SWITCH}=1 npm test`" in reason
    assert "test/shelves.test.mjs::every shelf in data/ parses" in reason
    assert "code a1 is listed twice" in reason  # the first error line
    assert "restored to how the task found them, the same run passes" in reason
    assert f'"not done: <which tests fail with {SWITCH}=1, and why>"' in reason
    assert one.last.findings[0].subject == "failing_tests"
    assert reruns == [f"{SWITCH}=1 npm test"]
    assert took < gs.BUDGET_S + 1.5


@needs_sandbox
def test_python_gated_tests_the_change_broke_hold_the_done(session, reruns):
    one = session(PY_FILES)
    output = _py_change(one)
    assert "SKIPPED [1] tests/test_shelves.py:" in output and REASON in output
    out = one.stop(DONE_PY)
    assert out.get("decision") == "block", out
    assert "tests/test_shelves.py::test_every_shelf_parses" in out["reason"]
    assert "code a1 is listed twice" in out["reason"]
    assert len(reruns) == 1


@needs_sandbox
@needs_node
def test_node_tap_run_without_a_package_script_is_caught_too(session, reruns):
    one = session(js_files())
    one.prompt(ASKED)
    one.write("src/shelf.mjs", JS_STRICT)
    output = one.run_real("node --test --test-reporter=tap")
    assert f"# SKIP {REASON}" in output
    out = one.stop("Duplicates are refused now. `node --test`: 2 passed, 2 skipped.\n\nFINAL: done")
    assert out.get("decision") == "block", out
    assert f"`{SWITCH}=1 node --test --test-reporter=tap`" in out["reason"]


@needs_sandbox
@needs_node
def test_an_example_error_with_numbers_in_the_message_is_no_disclosure(session):
    one = session(js_files())
    _js_change(one)
    message = (
        "parseShelf now refuses repeats, for example:\n\n`shelf north: code 2 is listed twice` (rule 2).\n\n"
        "`npm test`: 3 passed, 2 skipped.\n\nFINAL: done"
    )
    assert one.stop(message).get("decision") == "block"


@needs_sandbox
@needs_node
def test_a_second_stop_over_the_same_run_does_not_run_the_tests_again(session, reruns):
    one = session(js_files(), observe=True)  # observe mode: recorded, never raised, so asked again
    _js_change(one)
    one.stop("Not done: I still want to look at the data files.")
    assert reruns == []  # no completion claim: nothing ran
    one.stop(DONE_JS)
    assert one.last.would_have == "block"
    one.stop(DONE_JS)
    assert one.last.would_have == "block"
    assert len(reruns) == 1


# -- must stay silent ---------------------------------------------------------------------------------


@needs_sandbox
@needs_node
@pytest.mark.parametrize("before_the_plain_run", [True, False])
def test_the_switch_set_by_the_agent_after_the_last_change_is_silent(session, reruns, before_the_plain_run):
    one = session(js_files())
    one.prompt(ASKED)
    one.write("src/shelf.mjs", JS_STRICT)
    if before_the_plain_run:
        one.run_real("npm test", switch=SWITCH, shown=f"{SWITCH}=1 npm test")
        one.run_real("npm test")
    else:
        one.run_real("npm test")
        one.run_real(
            "node --test test/shelves.test.mjs",
            switch=SWITCH,
            shown=f"{SWITCH}=1 node --test test/shelves.test.mjs",
        )
    one.stop(DONE_JS)
    assert reruns == []
    assert "skip reason says" not in (one.last.reason or "")


@needs_sandbox
@needs_node
def test_gated_tests_failing_with_and_without_the_change_are_silent(session, reruns):
    broken = js_gated().replace('codes[0], "a1"', 'codes[0], "zz"')  # wrong before the task began
    one = session(js_files(broken))
    _js_change(one)
    assert_silent(one, one.stop(DONE_JS))
    assert len(reruns) == 1  # it ran, and the restored copy failed too


@needs_sandbox
@needs_node
def test_gated_tests_that_pass_are_silent(session, reruns):
    one = session(js_files(data=ONCE))
    _js_change(one)
    assert_silent(one, one.stop(DONE_JS))
    assert len(reruns) == 1


@needs_node
@pytest.mark.parametrize(
    "reason",
    [
        "full shelves are slow",  # no switch at all
        f"needs {SWITCH}",  # an upper-case word, no form
        f"run with {SWITCH}=1",  # not an accepted form
        f"set {SWITCH}=1 and SHELFMARK_DEEP=1 to run",  # two variables
        f"set {SWITCH}=north to run",  # not an on-value
    ],
)
def test_skips_without_one_named_switch_are_silent_and_run_nothing(session, reruns, reason):
    one = session(js_files(js_gated(reason=reason)))
    _js_change(one)
    assert_silent(one, one.stop(DONE_JS))
    assert reruns == []


@needs_node
@pytest.mark.parametrize(
    ("switch", "reason"),
    [
        ("SHELFMARK_API_TOKEN", "set SHELFMARK_API_TOKEN=1 to run"),
        ("SHELFMARK_LIVE", "set SHELFMARK_LIVE=1 to run"),
        (SWITCH, f"talks to the remote catalogue: set {SWITCH}=1 to run"),
        (SWITCH, f"uploads to s3: set {SWITCH}=1 to run"),
    ],
)
def test_deny_listed_switches_are_never_run(session, reruns, switch, reason):
    one = session(js_files(js_gated(reason=reason, switch=switch)))
    _js_change(one)
    assert_silent(one, one.stop(DONE_JS))
    assert reruns == []


@needs_sandbox
@needs_node
def test_a_run_past_the_budget_is_killed_and_silent(session, monkeypatch, tmp_path):
    woke = tmp_path / "woke"
    slow = js_gated(
        extra=f"  await new Promise((done) => setTimeout(done, 2500));\n  "
        f"(await import('node:fs')).writeFileSync({str(woke)!r}, 'x');\n"
    )
    monkeypatch.setattr(gs, "BUDGET_S", 0.8)
    one = session(js_files(slow))
    _js_change(one)
    started = time.monotonic()
    assert_silent(one, one.stop(DONE_JS))
    assert time.monotonic() - started < 3
    time.sleep(3)
    assert not woke.exists(), "the timed-out run kept going: its process group was not killed"


@needs_node
@pytest.mark.parametrize(
    "message",
    [
        f"Refused. `npm test`: 3 passed; the 2 shelf tests behind {SWITCH} were not run.\n\nFINAL: done",
        f"Refused. I did not set {SWITCH}, so the full-shelf tests are unverified.\n\nFINAL: done",
        "Refused. The full-shelf tests fail on data/north.json, which lists a1 twice.\n\nFINAL: done",
    ],
)
def test_a_message_that_says_the_gated_tests_were_not_run_or_fail_is_silent(session, reruns, message):
    one = session(js_files())
    _js_change(one)
    assert_silent(one, one.stop(message))
    assert reruns == []


@needs_node
def test_an_edit_after_the_last_full_run_leaves_it_to_the_stale_run_logic(session, reruns):
    one = session(js_files())
    _js_change(one)
    one.write("src/shelf.mjs", JS_STRICT.replace("listed twice", "repeated"))
    assert_silent(one, one.stop(DONE_JS))  # the minimal profile records the stale run, never says it
    assert reruns == []


@needs_node
def test_a_later_failing_run_leaves_it_to_the_gate(session, reruns):
    one = session(js_files())
    _js_change(one)
    red = node_spec(2, 1, failing=[("test/shelf.test.mjs", "a shelf keeps its codes")])
    one.run("npm test", npm_wrap("shelfmark", "node --test", red))
    one.stop(DONE_JS)
    assert reruns == []


@needs_node
def test_the_config_flag_turns_it_off(session, monkeypatch):
    calls = []
    monkeypatch.setattr(gs, "concerns", lambda *args: calls.append(args) or [])
    assert ChallengeSettings().gated_skips is True
    assert Settings.model_validate({"challenge": {"gated_skips": False}}).challenge.gated_skips is False
    one = session(js_files(), enabled=False)
    _js_change(one)
    assert_silent(one, one.stop(DONE_JS))
    assert calls == []


@needs_node
def test_without_a_sandbox_it_is_silent(session, reruns, monkeypatch):
    monkeypatch.setattr(ot, "SANDBOX_EXEC", "/nonexistent/sandbox-exec")
    one = session(js_files())
    _js_change(one)
    assert_silent(one, one.stop(DONE_JS))
    assert reruns == []


@needs_node
def test_a_command_run_from_another_folder_is_not_rerun(session, reruns):
    one = session(js_files())
    one.prompt(ASKED)
    one.write("src/shelf.mjs", JS_STRICT)
    one.run("cd . && npm test", real_output(one.repo, "npm test"))
    assert_silent(one, one.stop(DONE_JS))
    assert reruns == []


@needs_node
def test_a_file_changed_only_through_the_shell_is_not_restorable_so_nothing_runs(session, reruns):
    one = session(js_files())
    one.prompt(ASKED)
    (one.repo / "src/shelf.mjs").write_text(JS_STRICT)  # sed -i, a formatter: no baseline on record
    one.run("sed -i '' 's/x/x/' src/shelf.mjs", "")
    one.run_real("npm test")
    assert_silent(one, one.stop(DONE_JS))
    assert reruns == []


@needs_sandbox
@needs_node
def test_a_daemon_without_node_on_its_path_finds_it_through_the_agents_login_shell(
    session, monkeypatch, tmp_path
):
    one = session(js_files())
    _js_change(one)  # the agent's run, on the agent's PATH
    node_bin = os.path.dirname(shutil.which("node"))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # how the benchmark starts the daemon
    monkeypatch.setenv("HOME", str(shell_home(tmp_path / "bench-home", node_bin)))
    assert shutil.which("node") is None
    out = one.stop(DONE_JS)
    assert out.get("decision") == "block", out
    assert "test/shelves.test.mjs::every shelf in data/ parses" in out["reason"]


@needs_sandbox
def test_the_login_shell_path_is_read_from_its_profile(tmp_path, monkeypatch):
    made_up = tmp_path / "toolchain" / "bin"
    made_up.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(shell_home(tmp_path / "home", str(made_up))))
    writable = [str(tmp_path), "/private/tmp"]
    path = gs._agent_path(time.monotonic() + 2, writable)
    assert path.split(os.pathsep)[0] == str(made_up)
    assert gs._login_path("/nonexistent/shell", time.monotonic() + 2, writable) is None


# -- the pieces ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reason", "switch"),
    [
        ("set ALPHA_E2E=1 to run", "ALPHA_E2E=1"),
        ("end-to-end: export ALPHA_E2E=true", "ALPHA_E2E=true"),
        ("set `ALPHA_E2E=yes` to run", "ALPHA_E2E=yes"),
        ("ALPHA_SLOW=1 to enable", "ALPHA_SLOW=1"),
        ("ALPHA_SLOW=on to run", "ALPHA_SLOW=on"),
        ("needs ALPHA_E2E", None),
        ("run with ALPHA_E2E=1", None),
        ("ALPHA_E2E=1", None),
        ("set alpha_e2e=1 to run", None),
        ("set ALPHA_E2E=1 and BETA_E2E=1 to run", None),
        ("set ALPHA_URL=http://x to run", None),
        ("set ALPHA_MODE=fast to run", None),
        ("SKIP", None),
    ],
)
def test_the_switch_forms_accepted(reason, switch):
    assert parsers.skip_switch(reason) == switch


def test_the_runner_skip_lines_read():
    spec = "﹣ beta talks to the cli (0.05ms) # e2e: set ALPHA_E2E=1 to run\n﹣ gamma (0.04ms) # SKIP\n"
    tap = "    ok 2 - beta talks to the cli # SKIP e2e: set ALPHA_E2E=1 to run\n"
    rs = "SKIPPED [2] tests/test_e2e.py:5: set ALPHA_E2E=1 to run\nSKIPPED [1] tests/test_x.py:3: slow\n"
    verbose = "tests/test_e2e.py::test_cli SKIPPED (set ALPHA_E2E=1 to run)      [ 66%]\n"
    assert parsers.switch_skips(spec) == (
        ("ALPHA_E2E=1", "beta talks to the cli", "e2e: set ALPHA_E2E=1 to run"),
    )
    assert parsers.switch_skips(tap)[0][:2] == ("ALPHA_E2E=1", "beta talks to the cli")
    assert parsers.switch_skips(rs) == (("ALPHA_E2E=1", "tests/test_e2e.py:5", "set ALPHA_E2E=1 to run"),)
    assert parsers.switch_skips(verbose)[0][:2] == ("ALPHA_E2E=1", "tests/test_e2e.py::test_cli")
    assert parsers.switch_skips("ALPHA_E2E=1 set ALPHA_E2E=1 to run\n") == ()  # not a skip line


def test_switch_skips_are_read_only_from_a_run_that_counted_skips(monkeypatch):
    calls = []
    monkeypatch.setattr(parsers, "switch_skips", lambda text: calls.append(text) or ())
    runners.parse_output("pytest -q", "3 passed in 0.10s\n")
    assert calls == []
    runners.parse_output(
        "pytest -q -rs", "SKIPPED [1] t.py:1: set ALPHA_E2E=1 to run\n2 passed, 1 skipped in 0.1s\n"
    )
    assert len(calls) == 1


def test_the_deny_list():
    for name in (
        "ALPHA_API_KEY",
        "ALPHA_TOKEN",
        "ALPHA_SECRET",
        "ALPHA_PASSWORD",
        "ALPHA_CREDENTIALS",
        "ALPHA_LIVE",
        "ALPHA_PROD",
        "ALPHA_REMOTE",
        "ALPHA_DEPLOY",
        "ALPHA_NETWORK",
        "ALPHA_AWS",
        "ALPHA_GCP",
        "ALPHA_AZURE",
    ):
        assert gs.denied(name), name
    for reason in (
        "hits the production database",
        "needs network access",
        "uses https://example.test",
        "needs a live server",
        "needs credentials",
    ):
        assert gs.denied("ALPHA_E2E", [reason]), reason
    for name in ("ALPHA_E2E", "ALPHA_SLOW", "ALPHA_INTEGRATION", "ALPHA_KEYBOARD", "RUN_FULL"):
        assert not gs.denied(name, ["end-to-end: set it to run"]), name


@pytest.mark.parametrize(
    ("message", "said"),
    [
        ("`npm test`: 53 passed, 3 skipped.", False),
        ("All tests pass (0 failed, 3 skipped).", False),
        ("tests 56, pass 53, fail 0, skipped 3.", False),
        ("Errors now name the rule: `rule 2: value 2 is listed twice`. 51 passed, 3 skipped.", False),
        ("The parser now fails fast on bad input. 51 passed.", False),
        ("The 3 skipped e2e tests were not run.", True),
        ("I did not set ALPHA_E2E, so those tests are unverified.", True),
        ("ALPHA_E2E=1 npm test fails on the north shelf.", True),
        ("Everything passes except the end-to-end suite.", True),
        ("I couldn't run the integration tests here.", True),
    ],
)
def test_what_counts_as_a_disclosure(message, said):
    assert gs.disclosed(message, "ALPHA_E2E", ["every shelf parses"]) is said
