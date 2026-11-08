"""Rule D, a dead switch set (C1-D, day 4): ``intent/dead_switch.py`` and its place in the engine.

The frozen prototype ``premise_proto_d.py`` (SHA-256 bb9dc337…) is the specification. One test per
condition of RULES-C1-D §2, on synthetic repositories and made-up names (ARCHITECTURE-v0.2 §6.2): what
is held, what stays silent, the Codex multi-file patch, and the engine's wiring (after an allowed
decision, mutating non-delete edits only, once per task, never a name the prompt-time note named, the
premise hold's record, silence on any failure).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from truthstone.adapters.codex import translate
from truthstone.bench.codex.premise import names_absence
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import EventType
from truthstone.core.events import AgentEvent
from truthstone.intent import dead_switch


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


BASE = {
    "pyproject.toml": '[project]\nname = "otterlog"\nversion = "0.1.0"\n',
    "src/otterlog/__init__.py": "",
    "src/otterlog/app.py": "import os\n\nLEVEL = os.environ.get('OTTERLOG_LEVEL', 'info')\n",
    "scripts/report.js": "const args = process.argv.slice(2);\nconsole.log(args.includes('--since'));\n",
    "scripts/nightly.sh": "#!/bin/sh\nnode scripts/report.js\n",
    "README.md": "# otterlog\n",
}


def _repo(tmp_path: Path, extra: dict[str, str] | None = None) -> tuple[Path, list[str]]:
    files = {**BASE, **(extra or {})}
    root = tmp_path / "otterlog"
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root, sorted(files)


def _dead(prompt: str, root: Path, files: list[str], edits, **kw) -> list[tuple[str, str]]:
    return dead_switch.dead_switches(prompt, root, files, edits, **kw)


QUIET = "Set `OTTERLOG_QUIET=1` for the staging deploy so the startup banner stays quiet."
TOTALS = "Pass `--totals` to the nightly report so the summary has a totals row."


# -- held: a request-named switch written into a place, where nothing reads it ------------------------


@pytest.mark.parametrize(
    "place, lines",
    [
        ("docker-compose.yml", ["      OTTERLOG_QUIET: '1'"]),
        (".env", ["OTTERLOG_QUIET=1"]),
        ("package.json", ['    "start": "OTTERLOG_QUIET=1 node scripts/report.js",']),
        ("deploy/k8s/app.yaml", ["        - name: OTTERLOG_QUIET", '          value: "1"']),
        ("Dockerfile", ["ENV OTTERLOG_QUIET=1"]),
        ("scripts/deploy.sh", ["export OTTERLOG_QUIET=1"]),
        ("deploy/otterlog.service", ["Environment=OTTERLOG_QUIET=1"]),
    ],
)
def test_a_project_env_switch_set_in_a_place_nothing_reads_is_held(tmp_path, place, lines):
    root, files = _repo(tmp_path)
    assert _dead(QUIET, root, files, [(place, lines)]) == [("OTTERLOG_QUIET", place)]


@pytest.mark.parametrize(
    "extra, place, line",
    [
        ({}, "scripts/nightly.sh", "node scripts/report.js --totals"),  # a repository file the line runs
        ({}, "Makefile", "\tpython -m otterlog.report --totals"),  # -m <own package>
        (
            {
                "pyproject.toml": (
                    '[project]\nname = "otterlog"\n\n[project.scripts]\notterlog = "otterlog.cli:main"\n'
                )
            },
            "Procfile",
            "worker: otterlog report --totals",  # the project's own command
        ),
        (
            {"package.json": '{"name": "otterlog-web", "scripts": {"report": "node scripts/report.js"}}\n'},
            "Procfile",
            "web: npm run report --totals",  # an npm script whose command is one of those
        ),
    ],
    ids=["repository-file", "own-package", "own-command", "npm-script"],
)
def test_a_flag_passed_to_a_program_the_repository_owns_is_held(tmp_path, extra, place, line):
    root, files = _repo(tmp_path, extra)
    assert _dead(TOTALS, root, files, [(place, [line])]) == [("--totals", place)]


@pytest.mark.parametrize(
    "extra, prompt, place, line",
    [
        (
            {
                "config/otterlog.toml": 'level = "info"\n',
                "src/otterlog/settings.py": (
                    "import tomllib\n\nCONFIG = tomllib.load(open('config/otterlog.toml', 'rb'))\n"
                ),
            },
            "Set `archive_days = 30` in config/otterlog.toml so old runs are archived.",
            "config/otterlog.toml",
            "archive_days = 30",
        ),
        (
            {
                "data/rate-tiers/2026.json": '{"base": 100}\n',
                "src/otterlog/rates.py": "from pathlib import Path\n\nTIERS = Path('data/rate-tiers')\n",
            },
            'Set `"surcharge_cap": 200` in data/rate-tiers/2026.json.',
            "data/rate-tiers/2026.json",
            '  "surcharge_cap": 200,',
        ),
        (
            {
                "pyproject.toml": '[project]\nname = "otterlog"\n\n[tool.otterlog]\nlevel = "info"\n',
                "src/otterlog/settings.py": (
                    "import tomllib\nfrom pathlib import Path\n\n"
                    "TOOL = tomllib.loads(Path('pyproject.toml').read_text())['tool']['otterlog']\n"
                ),
            },
            "Set `max_rows = 500` under `[tool.otterlog]` in pyproject.toml.",
            "pyproject.toml",
            "max_rows = 500",
        ),
    ],
    ids=["config-file-code-reads", "data-directory", "tool-section"],
)
def test_a_key_set_in_a_config_file_the_project_reads_is_held(tmp_path, extra, prompt, place, line):
    root, files = _repo(tmp_path, extra)
    key = prompt.split("`")[1].split("=")[0].split(":")[0].strip().strip('"')
    assert _dead(prompt, root, files, [(place, [line])]) == [(key, place)]


# -- silent -----------------------------------------------------------------------------------------


def test_a_switch_code_reads_is_not_held(tmp_path):
    root, files = _repo(
        tmp_path, {"src/otterlog/banner.py": "import os\n\nQUIET = os.environ.get('OTTERLOG_QUIET')\n"}
    )
    assert _dead(QUIET, root, files, [(".env", ["OTTERLOG_QUIET=1"])]) == []
    root2, files2 = _repo(
        tmp_path / "flag", {"scripts/report.js": "console.log(process.argv.includes('--totals'));\n"}
    )
    assert _dead(TOTALS, root2, files2, [("scripts/nightly.sh", ["node scripts/report.js --totals"])]) == []


def test_a_reader_the_same_patch_adds_means_it_is_being_built(tmp_path):
    root, files = _repo(tmp_path)
    edits = [
        (".env", ["OTTERLOG_QUIET=1"]),
        ("src/otterlog/banner.py", ['QUIET = os.environ.get("OTTERLOG_QUIET")']),
    ]
    assert _dead(QUIET, root, files, edits) == []
    assert _dead(QUIET, root, files, edits[:1]) == [("OTTERLOG_QUIET", ".env")]


@pytest.mark.parametrize(
    "prompt, place, line",
    [
        (
            "Set `strictChecks: true` in tsconfig.json.",
            "tsconfig.json",
            '  "strictChecks": true,',
        ),  # a tool's file
        ("Set `LOG_FORMAT=json` in .env.", ".env", "LOG_FORMAT=json"),  # not the project's prefix
        (TOTALS, "scripts/ci.sh", "pytest -q --totals"),  # another program's flag
        (
            TOTALS,
            "Dockerfile",
            "COPY scripts/report.js /app/report.js --totals",
        ),  # an instruction that runs nothing
        (
            "Add a new `OTTERLOG_QUIET` variable and set it to 1 in .env.",
            ".env",
            "OTTERLOG_QUIET=1",
        ),  # creation
        (
            "`OTTERLOG_QUIET` doesn't exist yet: set it to 1 in .env and read it in the app.",
            ".env",
            "OTTERLOG_QUIET=1",
        ),  # absence wording
        (QUIET, "README.md", "OTTERLOG_QUIET=1"),  # not a place
    ],
    ids=[
        "tool-owned-file",
        "unprefixed-env",
        "external-program",
        "dockerfile-copy",
        "creation",
        "absence",
        "doc",
    ],
)
def test_what_is_not_a_dead_switch(tmp_path, prompt, place, line):
    root, files = _repo(tmp_path)
    assert _dead(prompt, root, files, [(place, [line])]) == []


def test_a_program_that_forwards_its_arguments_is_not_the_flags_owner(tmp_path):
    forwarding = "import argparse\n\nargs, rest = argparse.ArgumentParser().parse_known_args()\n"
    root, files = _repo(tmp_path, {"scripts/report.py": forwarding})
    assert _dead(TOTALS, root, files, [("scripts/nightly.sh", ["python scripts/report.py --totals"])]) == []


def test_a_dependencys_env_name_is_not_the_projects(tmp_path):
    pyproject = '[project]\nname = "otterlog"\ndependencies = ["otterlog-client>=1"]\n'
    root, files = _repo(tmp_path, {"pyproject.toml": pyproject})
    assert _dead(QUIET, root, files, [(".env", ["OTTERLOG_QUIET=1"])]) == []


def test_a_name_already_noted_or_another_file_is_not_held(tmp_path):
    root, files = _repo(tmp_path)
    edits = [(".env", ["OTTERLOG_QUIET=1"])]
    assert _dead(QUIET, root, files, edits, skip={"OTTERLOG_QUIET"}) == []
    assert _dead(QUIET, root, files, edits, this_file="README.md") == []
    assert _dead(QUIET, root, files, edits, this_file=".env") == [("OTTERLOG_QUIET", ".env")]


def test_the_hold_text_names_the_absence(tmp_path):
    text = dead_switch.HOLD.format(name="OTTERLOG_QUIET", where="`.env`")
    assert names_absence(text, ["OTTERLOG_QUIET"])
    assert "`OTTERLOG_QUIET` doesn't exist in this codebase; nothing reads it" in text


def test_the_edits_lines_of_a_file_tool(tmp_path):
    root, _files = _repo(tmp_path)

    def event(tool: str, **arguments) -> AgentEvent:
        return AgentEvent(event=EventType.PRE_TOOL_USE, workspace=str(root), tool=tool, arguments=arguments)

    path = str(root / ".env")
    assert dead_switch.edited_lines(event("Write", file_path=path, content="A=1\nB=2\n"), root) == [
        (".env", ["A=1", "B=2"])
    ]
    assert dead_switch.edited_lines(
        event("Edit", file_path=path, old_string="A=1\n", new_string="A=1\nC=3\n"), root
    ) == [(".env", ["C=3"])]
    edits = [{"old_string": "A=1", "new_string": "A=2"}, {"old_string": "B=2", "new_string": "B=2\nD=4"}]
    assert dead_switch.edited_lines(event("MultiEdit", file_path=path, edits=edits), root) == [
        (".env", ["A=2", "D=4"])
    ]
    assert dead_switch.edited_lines(event("Write", file_path="/elsewhere/x.env", content="A=1"), root) == []


# -- through the engine ------------------------------------------------------------------------------


def _prompt(repo: Path, text: str, session: str = "s") -> dict:
    return {
        "session_id": session,
        "turn_id": "t",
        "cwd": str(repo),
        "hook_event_name": "UserPromptSubmit",
        "prompt": text,
    }


def _patch(repo: Path, body: str, session: str = "s") -> dict:
    return {
        "session_id": session,
        "turn_id": "t",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": f"*** Begin Patch\n{body}*** End Patch\n"},
    }


def _add(path: str, *lines: str) -> str:
    return f"*** Add File: {path}\n" + "".join(f"+{line}\n" for line in lines)


def _denied(output: dict) -> str:
    specific = output.get("hookSpecificOutput") or {}
    return (
        specific.get("permissionDecisionReason", "") if specific.get("permissionDecision") == "deny" else ""
    )


@pytest.fixture
def engine(tmp_path):
    root, _files = _repo(tmp_path)
    guard = Guard(Settings())
    guard.workspace(root).index.ready(timeout=30)
    yield root, guard, lambda payload: translate.dispatch(guard, payload)
    guard.close()


def test_the_edit_is_held_once_with_the_premise_holds_record(engine):
    root, _guard, send = engine
    assert send(_prompt(root, QUIET))[0] == {}
    output, _results, decision = send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))
    assert _denied(output) == dead_switch.HOLD.format(name="OTTERLOG_QUIET", where="`.env`")
    assert [f.subject for f in decision.findings] == ["false_premise"]
    assert (
        decision.findings[0].summary
        == "the first edit after a premise note, held once so the user hears first"
    )
    assert send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0] == {}  # re-issued: proceeds
    assert send(_patch(root, _add("deploy/.env", "OTTERLOG_QUIET=1")))[0] == {}  # once per task


def test_a_new_task_can_be_held_again(engine):
    root, _guard, send = engine
    send(_prompt(root, QUIET))
    assert _denied(send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0])
    send(_prompt(root, "Set `OTTERLOG_COLOR=0` in .env for the CI logs."))
    assert "OTTERLOG_COLOR" in _denied(send(_patch(root, _add(".env", "OTTERLOG_COLOR=0")))[0])


def test_a_codex_patch_is_read_whole_a_sibling_reader_counts(engine):
    root, _guard, send = engine
    send(_prompt(root, QUIET))
    reader = _add("src/otterlog/banner.py", "import os", 'QUIET = os.environ.get("OTTERLOG_QUIET")')
    assert send(_patch(root, _add(".env", "OTTERLOG_QUIET=1") + reader))[0] == {}
    unrelated = _add("src/otterlog/greet.py", "def greet():", "    return 'hi'")
    output, results, _decision = send(_patch(root, _add(".env", "OTTERLOG_QUIET=1") + unrelated))
    assert "nothing in this repository reads `OTTERLOG_QUIET`" in _denied(output)
    assert [event.tool for event, _d in results] == ["Write", "Write"]


def test_a_name_the_prompts_note_already_named_is_not_held_again(engine):
    root, _guard, send = engine
    ask = "otterlog already stays quiet when OTTERLOG_QUIET=1 is set; turn that on in .env."
    assert send(_prompt(root, ask))[0]["hookSpecificOutput"]["additionalContext"].startswith(
        "`OTTERLOG_QUIET`"
    )
    first = _denied(send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0])
    assert first.startswith(
        "Truthstone: before editing: the request assumes `OTTERLOG_QUIET`"
    )  # the prompt's hold
    assert send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0] == {}  # not held again by rule D


def test_a_delete_is_not_held(engine):
    root, _guard, send = engine
    (root / ".env").write_text("OTTERLOG_QUIET=1\n")
    send(_prompt(root, QUIET))
    assert "OTTERLOG_QUIET" not in _denied(send(_patch(root, f"*** Delete File: {root / '.env'}\n"))[0])
    assert _denied(send(_patch(root, _add("deploy/.env", "OTTERLOG_QUIET=1")))[0])  # the task's first hold


def test_a_rule_that_fails_says_nothing(engine, monkeypatch):
    root, _guard, send = engine
    send(_prompt(root, QUIET))

    def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(dead_switch, "dead_switches", broken)
    assert send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0] == {}


@pytest.mark.parametrize("profile", ["minimal", "full"])
def test_it_speaks_wherever_the_premise_hold_speaks(tmp_path, profile):
    root, _files = _repo(tmp_path)
    guard = Guard(Settings(profile=profile))
    try:
        guard.workspace(root).index.ready(timeout=30)
        translate.dispatch(guard, _prompt(root, QUIET))
        assert _denied(translate.dispatch(guard, _patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0])
    finally:
        guard.close()


def test_observe_mode_withholds_it(tmp_path):
    root, _files = _repo(tmp_path)
    guard = Guard(Settings(observe_only=True))
    try:
        guard.workspace(root).index.ready(timeout=30)
        translate.dispatch(guard, _prompt(root, QUIET))
        output = translate.dispatch(guard, _patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0]
        assert output == {}
    finally:
        guard.close()


def test_a_file_tools_write_is_held(tmp_path):
    root, _files = _repo(tmp_path)
    guard = Guard(Settings())
    try:
        guard.workspace(root).index.ready(timeout=30)
        prompt = AgentEvent(
            event=EventType.USER_PROMPT, workspace=str(root), session_id="c", prompt_text=QUIET
        )
        guard.handle(prompt)
        write = AgentEvent(
            event=EventType.PRE_TOOL_USE,
            workspace=str(root),
            session_id="c",
            tool="Write",
            arguments={"file_path": str(root / ".env"), "content": "OTTERLOG_QUIET=1\n"},
        )
        decision = guard.handle(write)
        assert decision.action.value == "challenge"
        assert decision.reason == dead_switch.HOLD.format(name="OTTERLOG_QUIET", where="`.env`")
    finally:
        guard.close()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Ported exactly as premise_proto_d.install() wraps _on_pre_tool_use: when the guard defers the "
        "advice (the daemon's defer_bookkeeping under the minimal profile), the event is recorded by the "
        "worker with the advice's decision, so the hold the host saw is not in the store (reported)."
    ),
)
def test_a_hold_is_recorded_when_the_guard_defers_its_bookkeeping(tmp_path):
    """The design's intent (C1-D, "Record and texts"): the hold is the premise hold's record, which T4b and
    the bench's attestation read from the store."""
    root, _files = _repo(tmp_path)
    guard = Guard(Settings(), defer_bookkeeping=True)
    try:
        ws = guard.workspace(root)
        ws.index.ready(timeout=30)
        translate.dispatch(guard, _prompt(root, QUIET))
        assert _denied(translate.dispatch(guard, _patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0])
        with ws.event_lock:
            ws.drain()
        rows = ws.store.db.query(
            "SELECT d.action FROM decisions d JOIN events e ON e.id = d.event_id "
            "WHERE d.project_id = ? AND e.type = 'pre_tool_use'",
            (ws.store.project_id,),
        )
        assert [row[0] for row in rows] == ["challenge"]
    finally:
        guard.close()
