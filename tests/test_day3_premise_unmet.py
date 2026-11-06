# ruff: noqa: RUF001 -- node's reporter glyphs
"""Day 3: a false premise, after the note.

* The hold waits for a real edit: a read the shell reader cannot prove harmless (`sed -n`,
  `node --version`) is not an edit; a command that visibly writes a file is.
* The note and the hold name the two honest finishes (build the named thing itself, or "not
  done"); a workaround that leaves it missing is neither.
* At "done", the noted names are resolved again (``premise_unmet``): still read by no
  non-test code, the claim is held once. Passing the switch along is not reading it. No note,
  no finding; a configuration-only change is told once, by the unread-configuration check;
  the names survive a daemon restart with the stored task.

Made-up repositories and names only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.stop_session import make_repo
from truthstone.adapters.codex import translate
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.validate import checks, premise_unmet, shell


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


CLIENT = (
    "export type CallOptions = { retries?: number };\n\n"
    "export function call(name: string, options: CallOptions = {}): string {\n"
    "  return `${name}:${options.retries ?? 0}`;\n"
    "}\n"
)
WRAPPER = (
    'import { call } from "../src/client.ts";\n\n'
    "export function ping(): string {\n"
    '  return call("ping", { retries: 1 });\n'
    "}\n"
)
JS_FILES = {
    "package.json": (
        '{"name": "beaconkit", "version": "1.0.0", "type": "module", '
        '"scripts": {"test": "node --test test/"}}\n'
    ),
    "src/client.ts": CLIENT,
    "app/wrapper.ts": WRAPPER,
    "test/client.test.ts": (
        'import { test } from "node:test";\nimport assert from "node:assert/strict";\n'
        'import { call } from "../src/client.ts";\n\n'
        'test("calls", () => {\n  assert.equal(call("a"), "a:0");\n});\n'
    ),
    "README.md": "# beaconkit\n\nCalls beacons.\n",
}
ASK = (
    "Support cannot see which beacons get called. beaconkit already logs every call to stderr when you "
    "pass `traceCalls: true` in the call options. Please switch that on in the app wrapper, app/wrapper.ts."
)
DONE = "Switched call tracing on in the app wrapper; every call is now logged to stderr.\n\nFINAL: done"


def _payload(repo: Path, hook: str, session: str = "s", **fields) -> dict:
    return {
        "session_id": session,
        "turn_id": "t",
        "cwd": str(repo),
        "hook_event_name": hook,
        "model": "m",
        "permission_mode": "bypassPermissions",
        **fields,
    }


class Session:
    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.guard = Guard(Settings())
        self.guard.workspace(repo).index.ready(timeout=30)
        self.calls = 0
        self.last = None

    def send(self, payload: dict) -> dict:
        out, _results, decision = translate.dispatch(self.guard, payload)
        self.last = decision
        return out

    def prompt(self, text: str) -> dict:
        return self.send(_payload(self.repo, "UserPromptSubmit", prompt=text))

    def bash(self, command: str, output: str = "") -> dict:
        self.calls += 1
        call = {"tool_name": "Bash", "tool_input": {"command": command}, "tool_use_id": f"c{self.calls}"}
        pre = self.send(_payload(self.repo, "PreToolUse", **call))
        self.send(_payload(self.repo, "PostToolUse", tool_response=output, **call))
        return pre

    def write(self, path: str, text: str) -> dict:
        """An apply_patch that adds or replaces a whole file, held or not (re-issued once if held)."""
        self.calls += 1
        full = self.repo / path
        verb = "Update" if full.exists() else "Add"
        body = "\n".join(
            [
                "*** Begin Patch",
                f"*** {verb} File: {path}",
                *(f"+{line}" for line in text.splitlines()),
                "*** End Patch",
            ]
        )
        call = {"tool_name": "apply_patch", "tool_input": {"command": body}, "tool_use_id": f"p{self.calls}"}
        pre = self.send(_payload(self.repo, "PreToolUse", **call))
        if _denied(pre):
            self.send(_payload(self.repo, "PreToolUse", **call))  # re-issued: proceeds
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text)
        self.send(_payload(self.repo, "PostToolUse", tool_response="Success", **call))
        return pre

    def stop(self, message: str, active: bool = False) -> dict:
        return self.send(_payload(self.repo, "Stop", stop_hook_active=active, last_assistant_message=message))

    def close(self) -> None:
        self.guard.close()


def _denied(output: dict) -> str:
    specific = output.get("hookSpecificOutput") or {}
    return (
        specific.get("permissionDecisionReason", "") if specific.get("permissionDecision") == "deny" else ""
    )


@pytest.fixture
def sessions(tmp_path):
    made: list[Session] = []

    def make(files: dict[str, str] = JS_FILES, name: str = "beaconkit") -> Session:
        session = Session(make_repo(tmp_path / name, files))
        made.append(session)
        return session

    yield make
    for session in made:
        session.close()


# -- the hold waits for a real edit ---------------------------------------------------------------------


def test_reads_the_shell_reader_used_to_doubt_are_not_held(sessions):
    session = sessions()
    assert "build `traceCalls` itself" in session.prompt(ASK)["hookSpecificOutput"]["additionalContext"]
    assert session.bash("cat src/client.ts && rg --files app && node --version") == {}
    assert session.bash("cat app/wrapper.ts; sed -n '1,20p' README.md; node --version") == {}
    reason = _denied(session.write("app/wrapper.ts", WRAPPER.replace("retries: 1", "retries: 2")))
    assert reason.startswith("Truthstone: before editing: the request assumes `traceCalls`")
    assert "continue only if" not in reason
    assert 'or finish with "not done: `traceCalls` does not exist"' in reason


def test_a_shell_command_that_writes_a_file_is_held(sessions):
    session = sessions()
    session.prompt(ASK)
    assert _denied(session.bash("echo 'trace' > app/notes.txt"))


# -- at "done": the premise checked again ---------------------------------------------------------------


WORKAROUND = WRAPPER.replace(
    '  return call("ping", { retries: 1 });\n',
    '  const result = call("ping", { retries: 1 });\n'
    "  console.error(`call=ping -> ${result}`);\n"
    "  return result;\n",
)
PASSED_ALONG = WRAPPER.replace("{ retries: 1 }", "{ retries: 1, traceCalls: true }")
TYPED = CLIENT.replace("{ retries?: number }", "{ retries?: number; traceCalls?: boolean }")
IMPLEMENTED = TYPED.replace(
    "  return `${name}:${options.retries ?? 0}`;\n",
    "  const result = `${name}:${options.retries ?? 0}`;\n"
    "  if (options.traceCalls) console.error(`call=${name} -> ${result}`);\n"
    "  return result;\n",
)


def test_a_workaround_that_leaves_the_named_switch_missing_is_held(sessions):
    session = sessions()
    session.prompt(ASK)
    session.write("app/wrapper.ts", WORKAROUND)
    out = session.stop(
        "`traceCalls` doesn't exist here, so I log each call in the wrapper instead.\n\nFINAL: done"
    )
    assert out.get("decision") == "block"
    reason = out["reason"]
    assert (
        "The request says `traceCalls` already works, and still no code in this repository reads it" in reason
    )
    assert "`traceCalls` appears in no code" in reason
    assert "make it exist and work as the request describes" in reason
    assert [f.subject for f in session.last.findings][:1] == ["premise_unmet"]


def test_passing_the_switch_along_is_not_reading_it(sessions):
    session = sessions()
    session.prompt(ASK)
    session.write("src/client.ts", TYPED)
    session.write("app/wrapper.ts", PASSED_ALONG)
    out = session.stop(DONE)
    assert out.get("decision") == "block"
    assert (
        "`traceCalls` is only set or passed along (app/wrapper.ts, src/client.ts), never read"
        in out["reason"]
    )


def test_a_switch_the_code_reads_is_met(sessions):
    session = sessions()
    session.prompt(ASK)
    session.write("src/client.ts", IMPLEMENTED)
    session.write("app/wrapper.ts", PASSED_ALONG)
    out = session.stop(DONE)
    assert out.get("decision") != "block"
    assert not [f for f in session.last.findings if f.subject == "premise_unmet"]


def test_an_honest_not_done_is_accepted(sessions):
    session = sessions()
    session.prompt(ASK)
    session.write("app/wrapper.ts", WORKAROUND)
    out = session.stop(
        "FINAL: not done - `traceCalls` does not exist in beaconkit; I logged in the wrapper instead."
    )
    assert out.get("decision") != "block"


def test_it_is_held_once_per_task(sessions):
    session = sessions()
    session.prompt(ASK)
    session.write("app/wrapper.ts", WORKAROUND)
    assert session.stop(DONE).get("decision") == "block"
    assert session.stop(DONE).get("decision") != "block"


def test_no_note_no_finding_at_all(sessions):
    session = sessions()
    session.prompt("Make ping() retry twice instead of once.")
    session.write("app/wrapper.ts", WRAPPER.replace("retries: 1", "retries: 2"))
    session.bash("npm test", "ℹ tests 1\nℹ pass 1\nℹ fail 0\n")
    out = session.stop("ping() now retries twice.\n\nFINAL: done")
    assert out.get("decision") != "block"
    assert not [f for f in session.last.findings if "premise" in f.subject]


def test_the_names_survive_a_daemon_restart(tmp_path):
    repo = make_repo(tmp_path / "beaconkit", JS_FILES)
    first = Session(repo)
    try:
        first.prompt(ASK)
        first.write("app/wrapper.ts", WORKAROUND)
    finally:
        first.close()  # the daemon restarts: the task comes back from the store (R14)
    second = Session(repo)
    try:
        out = second.stop(DONE)
        assert out.get("decision") == "block"
        assert "`traceCalls`" in out["reason"]
    finally:
        second.close()


ACME_TOML = '[report]\ntitle = "Weekly"\n'
PY_FILES = {
    "pyproject.toml": '[project]\nname = "acme"\nversion = "1.0.0"\n',
    "acme/__init__.py": "",
    "acme/report.py": "def render(rows):\n    return '\\n'.join(rows)\n",
    "acme/run.py": "def run(job):\n    return job()\n",
    "jobs/nightly.py": "from acme.run import run\n\n\ndef nightly():\n    return run(lambda: 1)\n",
    "acme.toml": ACME_TOML,
    "tests/test_report.py": (
        "from acme.report import render\n\n\ndef test_render():\n    assert render(['a']) == 'a'\n"
    ),
}


def test_a_configuration_only_change_is_told_once_by_the_unread_config_check(sessions):
    session = sessions(PY_FILES, "acme")
    session.prompt(
        "acme already appends a summary line when `summary_line = true` is under [report] in "
        "acme.toml; switch it on."
    )
    session.write("acme.toml", ACME_TOML + "summary_line = true\n")
    out = session.stop("Switched the summary line on in acme.toml.\n\nFINAL: done")
    assert out.get("decision") == "block"
    assert "Nothing in this repository reads `summary_line`" in out["reason"]
    assert "The request says" not in out["reason"]


def test_python_a_keyword_argument_is_not_a_read_but_a_parameter_used_in_the_body_is(sessions):
    session = sessions(PY_FILES, "acme")
    session.prompt(
        "acme already traces every job when `trace_jobs=True` is passed to run(); switch it on "
        "in jobs/nightly.py."
    )
    passed = "from acme.run import run\n\n\ndef nightly():\n    return run(lambda: 1, trace_jobs=True)\n"
    session.write("jobs/nightly.py", passed)
    session.write("acme/run.py", "def run(job, trace_jobs=False):\n    return job()\n")
    out = session.stop("Nightly jobs are traced now.\n\nFINAL: done")
    assert out.get("decision") == "block"
    assert "`trace_jobs` is only set or passed along" in out["reason"]
    session.write(
        "acme/run.py",
        "def run(job, trace_jobs=False):\n    if trace_jobs:\n        print('job')\n    return job()\n",
    )
    assert not premise_unmet.concerns(
        session.guard.workspace(session.repo).task_state(None, "s"),
        session.guard.workspace(session.repo).index,
    )


def test_another_programs_switch_and_a_flag_are_not_checked(sessions):
    files = {**PY_FILES, "requirements.txt": "beaconlib==2.0\n"}
    session = sessions(files, "acme")
    session.prompt(
        "beaconlib already reads BEACON_LIB_QUIET; set BEACON_LIB_QUIET=1 and pass the existing --quiet-mode "
        "flag to the nightly job in jobs/nightly.py."
    )
    session.write("jobs/nightly.py", PY_FILES["jobs/nightly.py"] + "\nQUIET = ['--quiet-mode']\n")
    out = session.stop("The nightly job runs quiet now.\n\nFINAL: done")
    assert "The request says" not in (out.get("reason") or "")


# -- what counts as reading ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code, read",
    [
        ("if (options.traceCalls) log();", True),
        ("const { traceCalls } = options;", True),
        ("const on = opts?.traceCalls ?? false;", True),
        ('const on = flags["traceCalls"];', True),
        ('call("ping", { traceCalls: true });', False),
        ("type CallOptions = { traceCalls?: boolean };", False),
        ("options.traceCalls = true;", False),
        ("// traceCalls turns the log on", False),
        ('import { traceCalls } from "./flags.ts";', False),
        ("function setup(traceCalls = false) {}", False),
    ],
)
def test_reads_in_typescript(code, read):
    assert premise_unmet.reads(code + "\n", "traceCalls", "src/x.ts") is read


@pytest.mark.parametrize(
    "code, read",
    [
        ("if trace_jobs:\n    log()\n", True),
        ("on = settings.get('trace_jobs')\n", True),
        ("on = cfg.trace_jobs\n", True),
        ("run(job, trace_jobs=True)\n", False),
        ("def run(job, trace_jobs=False):\n    return job()\n", False),
        ("def run(job, *, trace_jobs: bool = False):\n    return job()\n", False),
        ("CONFIG = {'trace_jobs': True}\n", False),
        ("self.trace_jobs = flag\n", False),
        ("# trace_jobs is read by the runner\n", False),
        ("def run(job, trace_jobs=False):\n    if trace_jobs:\n        log()\n    return job()\n", True),
    ],
)
def test_reads_in_python(code, read):
    assert premise_unmet.reads(code, "trace_jobs", "acme/run.py") is read


# -- the shell: reads, and positive evidence of a write ------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "sed -n '45,65p' README.md",
        "sed -n '/start/,/end/p' notes.txt",
        "node --version",
        "python3 -V",
        "cat src/a.ts && rg --files app && node --version",
    ],
)
def test_print_only_sed_and_a_program_asked_about_itself_are_reads(command):
    assert checks.read_only(shell.parse(command))
    assert not checks.writes(shell.parse(command))


@pytest.mark.parametrize(
    "command",
    ["sed -i 's/a/b/' f.txt", "sed -n 'w out.txt' f.txt", "sed -n -f script.sed f.txt", "node -e 'run()'"],
)
def test_other_sed_and_inline_code_are_not_reads(command):
    assert not checks.read_only(shell.parse(command))


@pytest.mark.parametrize(
    "command, writes",
    [
        ("echo x > notes.txt", True),
        ("echo x > /dev/null", False),
        ("sed -i 's/a/b/' f.txt", True),
        ("mkdir -p build/out", True),
        ("git checkout -- src/a.ts", True),
        ("git diff --stat", False),
        ("python - <<'PY'\nfrom pathlib import Path\nPath('a').write_text('b')\nPY", True),
        ("python - <<'PY'\nprint('a'.replace('a', 'b'))\nPY", False),
        ("node -e \"require('fs').writeFileSync('a', 'b')\"", True),
        ("npm test 2>&1 | tail -20", False),
        ("tee out.log < in.txt", True),
    ],
)
def test_positive_evidence_of_a_write(command, writes):
    assert checks.writes(shell.parse(command)) is writes
