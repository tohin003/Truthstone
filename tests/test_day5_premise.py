"""Day 5: false premises worded as "<program> reads `x` from <config place>: set it ...".

Three existing checks fit this shape and each one stopped at a precondition that was too narrow. On
made-up repositories and names:

* **B, prompt time** (``intent/premise_switch.py``, C1 v4.3): a present-tense reading verb before the name
  in its own clause is a capability marker beside a condition, "with" and "has a `x` option"; "set/put
  ... there" is a back-reference. Every other v4.3 guard stays: the subject is the project's own, a named
  tool silences it, future/creation/absence words silence it, a back-reference is required, and the name
  resolves nowhere.
* **C, rule D** (``intent/dead_switch.py``): for a section the request names, a sibling key read by quoted
  key in a reader that quotes the section's name (the section copied into a dict) is ownership evidence.
  Day 5 also lets rule D take a key into the project's own section of its manifest: package.json's
  top-level object named after the project, pyproject's ``[tool.<project>]`` (a dotted `<section>.<key>`
  or a named section), with every other D condition.
* **S, Stop** (``validate/config_reads.py``): "reads/takes/loads" say the switch works today, unless
  negated ("nothing reads `x`") or said of another program the configuration runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.stop_session import StopSession, make_repo
from truthstone.adapters.codex import render, translate
from truthstone.core.config import NotesSettings, Settings
from truthstone.core.engine import Guard
from truthstone.intent import dead_switch, premise, premise_switch
from truthstone.validate import config_reads


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


def _build(root: Path, files: dict[str, str]) -> tuple[Path, list[str]]:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root, sorted(files)


# -- B: the prompt-time check ------------------------------------------------------------------------

_PY_CONFIG = (
    '"""parcelwren settings: [send] in parcelwren.toml."""\n'
    "import tomllib\n\n\n"
    "def load(path='parcelwren.toml'):\n"
    "    with open(path, 'rb') as fh:\n"
    "        table = tomllib.load(fh).get('send', {})\n"
    "    return table.get('batch_size', 100), table.get('sender', 'ops')\n"
)
PARCELWREN = {
    "pyproject.toml": '[project]\nname = "parcelwren"\nversion = "0.3.0"\n',
    "parcelwren.toml": '[send]\nbatch_size = 100\nsender = "ops"\n',
    "src/parcelwren/__init__.py": "",
    "src/parcelwren/config.py": _PY_CONFIG,
    "src/parcelwren/cli.py": (
        "import argparse\n\nfrom parcelwren.config import load\n\n\n"
        "def main():\n    parser = argparse.ArgumentParser(prog='parcelwren')\n"
        "    parser.add_argument('--queue')\n    return parser.parse_args(), load()\n"
    ),
    "tests/test_loading.py": "from parcelwren.config import load\n\n\ndef test_load():\n    assert load()\n",
    "README.md": "# parcelwren\n\nSends parcels notices. Settings live in parcelwren.toml under [send].\n",
}
TALLYHO_PKG = {
    "name": "tallyho",
    "version": "1.2.0",
    "type": "module",
    "scripts": {"test": "node --test", "check": "node scripts/check.ts"},
    "tallyho": {"sources": ["data/eu.json"], "currency": "EUR"},
}
TALLYHO = {
    "package.json": json.dumps(TALLYHO_PKG, indent=2) + "\n",
    "scripts/check.ts": (
        'import { readFileSync } from "node:fs";\n'
        'const manifest = JSON.parse(readFileSync("package.json", "utf8"));\n'
        "for (const source of manifest.tallyho?.sources ?? []) console.log(source);\n"
    ),
    "src/cli.ts": (
        'import { parseArgs } from "node:util";\n'
        "export function main(argv: string[]) {\n"
        '  const { values } = parseArgs({ args: argv, options: { region: { type: "string" } } });\n'
        "  return values.region;\n}\n"
    ),
    "README.md": "# tallyho\n",
}

READS_FROM = (
    "Resends are too few. parcelwren reads `resend_limit` from the [send] section of parcelwren.toml and "
    "resends that often: set it to 5 in parcelwren.toml."
)
TAKES_FROM = "parcelwren takes `resend_limit` from parcelwren.toml: set it to 5."
CLI_THERE = (
    "Shipments default to the wrong region. The CLI reads defaults for --region from "
    "`tallyho.defaultRegion` in package.json: set region eu there."
)


def _check(tmp_path: Path, files: dict[str, str], prompt: str, name: str = "parcelwren") -> list[str]:
    root, listed = _build(tmp_path / name, files)
    return [a.name for a in premise.check(prompt, root, listed).missing]


@pytest.mark.parametrize(
    "prompt, files, name, noted",
    [
        (READS_FROM, PARCELWREN, "parcelwren", ["resend_limit"]),
        (TAKES_FROM, PARCELWREN, "parcelwren", ["resend_limit"]),
        (CLI_THERE, TALLYHO, "tallyho", ["tallyho.defaultRegion"]),
    ],
    ids=["reads-set-it", "takes-set-it", "cli-reads-set-there"],
)
def test_b_a_reading_verb_and_a_back_reference_assert_the_name(tmp_path, prompt, files, name, noted):
    assert _check(tmp_path, files, prompt, name) == noted


@pytest.mark.parametrize(
    "prompt",
    [
        # a named tool reads it: the tool's own setting
        "nginx reads `client_max_body_size` from deploy/nginx.conf: set it to 20m.",
        "mkdocs reads `site_url` from mkdocs.yml: set it to https://docs.example.org there.",
        # the name is read today
        "parcelwren reads `batch_size` from the [send] section of parcelwren.toml: set it to 200.",
        # the request builds it
        "Make parcelwren read `resend_limit` from parcelwren.toml and resend that often; set it to 5.",
        "parcelwren should read `resend_limit` from parcelwren.toml: set it to 5 and implement the resends.",
        "New: parcelwren reads `resend_limit` from parcelwren.toml. Set it to 5.",
        "Add a `resend_limit` setting: parcelwren reads it from parcelwren.toml and resends that often. "
        "Set it to 5.",
        # future
        "parcelwren will read `resend_limit` from parcelwren.toml: set it to 5.",
        # no back-reference
        "parcelwren reads `resend_limit` from parcelwren.toml.",
        # the reading verb is more than 80 characters before the name
        "parcelwren reads, for every batch it hands to the regional sorting offices and the overnight "
        "couriers, "
        "`resend_limit` from parcelwren.toml: set it to 5.",
        # not the project's own subject
        "The mail relay reads `resend_limit` from parcelwren.toml: set it to 5.",
        # "there" without a capability marker
        "The CLI prints defaults for `tallyho.defaultRegion` in package.json: set region eu there.",
    ],
    ids=[
        "tool-nginx",
        "tool-mkdocs",
        "name-is-read",
        "make-read",
        "should-read",
        "new",
        "add-a-setting",
        "future",
        "no-back-reference",
        "verb-too-far",
        "not-the-project",
        "there-without-capability",
    ],
)
def test_b_what_stays_silent(tmp_path, prompt, monkeypatch):
    """Rule B's boundaries, B on its own. Day 6: the relied-switch rule (C7) is switched off here; with it
    on, "verb-too-far" and "there-without-capability" are noted (``test_day6_premise.py``)."""
    monkeypatch.setattr(premise_switch, "RELIED_SPEAKS", False)
    files = {**PARCELWREN, **TALLYHO, "package.json": TALLYHO["package.json"]}
    assert _check(tmp_path, files, prompt) == []


def test_b_known_misses_stay_unreached(tmp_path, monkeypatch):
    """Documented limits of rule B: "uses/honours" wordings, the name as the subject, imperative-first
    requests that only presuppose the setting. Day 6: C7 notes all three (``test_day6_premise.py``); this
    pins rule B alone."""
    monkeypatch.setattr(premise_switch, "RELIED_SPEAKS", False)
    for prompt in (
        "parcelwren uses `resend_limit` from parcelwren.toml to cap resends: set it to 5.",
        "`resend_limit` in parcelwren.toml caps how often parcelwren resends: set it to 5.",
        "Raise `resend_limit` in parcelwren.toml to 5.",
    ):
        assert _check(tmp_path / str(abs(hash(prompt))), PARCELWREN, prompt) == []


def test_b_the_note_and_the_first_edit_hold_through_the_engine(tmp_path):
    root, _files = _build(tmp_path / "parcelwren", PARCELWREN)
    guard = Guard(Settings())
    try:
        guard.workspace(root).index.ready(timeout=30)
        out, _r, _d = translate.dispatch(guard, _prompt(root, READS_FROM))
        assert out["hookSpecificOutput"]["additionalContext"].startswith("`resend_limit` appears nowhere")
        held = translate.dispatch(
            guard, _patch(root, _update(root / "parcelwren.toml", 'sender = "ops"', "resend_limit = 5"))
        )[0]
        assert held["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "`resend_limit`" in held["hookSpecificOutput"]["permissionDecisionReason"]
    finally:
        guard.close()


# -- C: rule D, a named section read from a copy of it -----------------------------------------------

_SLUGGER_CLI = (
    'import configparser\n\nSECTION = "slugger"\n\n\n'
    "def read_prefs(path='slugger.ini'):\n"
    "    parser = configparser.ConfigParser()\n"
    "    parser.read(path)\n"
    "    defaults = dict(parser[SECTION]) if parser.has_section(SECTION) else {}\n"
    "    return defaults.get('style', 'lower'), defaults.get('joiner', '-')\n"
)
SLUGGER = {
    "pyproject.toml": '[project]\nname = "slugger"\n',
    "slugger.ini": "[slugger]\nstyle = lower\njoiner = -\n",
    "src/slugger/__init__.py": "",
    "src/slugger/cli.py": _SLUGGER_CLI,
    "README.md": "# slugger\n",
}
SLUG_CAP = (
    "Slugs are too long. slugger reads `slug_cap` from the [slugger] section of slugger.ini and trims slugs "
    "to "
    "it: set it to 60 in slugger.ini."
)
SET_CAP = [("slugger.ini", ["slug_cap = 60"])]


def _dead(tmp_path, files, prompt, edits, name="slugger"):
    root, listed = _build(tmp_path / name, files)
    return dead_switch.dead_switches(prompt, root, listed, edits)


def test_c_a_sibling_read_from_a_copy_of_the_named_section_owns_it(tmp_path):
    assert _dead(tmp_path, SLUGGER, SLUG_CAP, SET_CAP) == [("slug_cap", "slugger.ini")]


@pytest.mark.parametrize(
    "cli",
    [
        # the reader never quotes the section's name: it opens whichever section is there
        _SLUGGER_CLI.replace('SECTION = "slugger"', "SECTION = None").replace(
            "dict(parser[SECTION]) if parser.has_section(SECTION) else {}",
            "dict(parser[parser.sections()[0]])",
        ),
        # the siblings read by quoted key are generic attribute names only
        _SLUGGER_CLI.replace("'style'", "'name'").replace("'joiner'", "'version'"),
        # the requested key is read
        _SLUGGER_CLI + "\n\ndef cap(path='slugger.ini'):\n    return read_prefs(path), 'slug_cap'\n",
    ],
    ids=["section-name-not-quoted", "generic-siblings", "key-is-read"],
)
def test_c_what_stays_silent(tmp_path, cli):
    files = dict(SLUGGER, **{"src/slugger/cli.py": cli})
    if "'name'" in cli:
        files["slugger.ini"] = "[slugger]\nname = lower\nversion = 1\n"
    assert _dead(tmp_path, files, SLUG_CAP, SET_CAP) == []


def test_c_a_sibling_read_by_key_in_a_file_that_does_not_open_the_section_does_not_count(tmp_path):
    files = dict(SLUGGER)
    files["src/slugger/cli.py"] = (
        "import configparser\n\n\ndef read_prefs(path='slugger.ini'):\n"
        "    parser = configparser.ConfigParser()\n    parser.read(path)\n"
        "    return dict(parser[parser.sections()[0]])\n"
    )
    files["src/slugger/text.py"] = "def style(defaults):\n    return defaults.get('style', 'lower')\n"
    assert _dead(tmp_path, files, SLUG_CAP, SET_CAP) == []


# -- day 5: rule D in the project's own section of its manifest ---------------------------------------

PKG_ADD = [("package.json", ['    "defaultRegion": "eu",'])]


@pytest.mark.parametrize(
    "prompt, name",
    [
        ("Set `tallyho.defaultRegion` to eu in package.json.", "tallyho.defaultRegion"),
        ("Set `defaultRegion` to eu in the `tallyho` block of package.json.", "defaultRegion"),
        (
            "Shipments go to the wrong region; set `defaultRegion` to eu in the tallyho section of "
            "package.json.",
            "defaultRegion",
        ),
    ],
    ids=["dotted", "named-block", "named-section"],
)
def test_d_a_key_in_the_projects_own_package_json_section_is_held(tmp_path, prompt, name):
    assert _dead(tmp_path, TALLYHO, prompt, PKG_ADD, "tallyho") == [(name, "package.json")]


RELWREN = {
    "pyproject.toml": (
        '[project]\nname = "relwren"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n\n'
        '[tool.relwren]\ndirectory = "changes"\ntitle_format = "## {version}"\n'
    ),
    "src/relwren/__init__.py": "",
    "src/relwren/config.py": (
        "import tomllib\nfrom pathlib import Path\n\n\n"
        "def load(pyproject=Path('pyproject.toml')):\n"
        "    table = tomllib.loads(pyproject.read_text()).get('tool', {}).get('relwren', {})\n"
        "    return table.get('directory', 'changes'), table.get('title_format', '## {version}')\n"
    ),
    "README.md": "# relwren\n",
}
LINKS = 'Set `issue_link = "https://tracker.example/{n}"` under `[tool.relwren]` in pyproject.toml.'


def test_d_a_key_in_the_projects_own_pyproject_table_is_held(tmp_path):
    edits = [("pyproject.toml", ['issue_link = "https://tracker.example/{n}"'])]
    assert _dead(tmp_path, RELWREN, LINKS, edits, "relwren") == [("issue_link", "pyproject.toml")]


def test_d_a_table_named_after_the_projects_own_package_counts(tmp_path):
    files = {
        "pyproject.toml": (
            '[project]\nname = "quarter-reports"\n\n[tool.repwren]\ntitle = "Ops"\noutput_dir = "site"\n'
        ),
        "repwren/__init__.py": "",
        "repwren/settings.py": (
            "import tomllib\n\n\ndef load(path='pyproject.toml'):\n"
            "    with open(path, 'rb') as fh:\n"
            "        table = tomllib.load(fh).get('tool', {}).get('repwren', {})\n"
            "    return table.get('title'), table.get('output_dir')\n"
        ),
    }
    prompt = "Set `toc_depth = 2` under `[tool.repwren]` in pyproject.toml."
    edits = [("pyproject.toml", ["toc_depth = 2"])]
    assert _dead(tmp_path, files, prompt, edits, "reports") == [("toc_depth", "pyproject.toml")]


@pytest.mark.parametrize(
    "prompt, files, edits",
    [
        # a tool's section, not the project's
        (
            "Set `testTimeout` to 9000 in the `jest` block of package.json.",
            {"package.json": json.dumps({**TALLYHO_PKG, "jest": {"verbose": True}}, indent=2)},
            [("package.json", ['    "testTimeout": 9000,'])],
        ),
        (
            "Set `jest.testTimeout` to 9000 in package.json.",
            {"package.json": json.dumps({**TALLYHO_PKG, "jest": {"verbose": True}}, indent=2)},
            [("package.json", ['    "testTimeout": 9000,'])],
        ),
        (
            "Set `xfail_strict = true` under `[tool.pytest.ini_options]` in pyproject.toml.",
            {"pyproject.toml": '[project]\nname = "tallyho"\n\n[tool.pytest.ini_options]\naddopts = "-q"\n'},
            [("pyproject.toml", ["xfail_strict = true"])],
        ),
        # the request names no section, and a line does not show its section
        ("Set `defaultRegion` to eu in package.json.", {}, PKG_ADD),
        # the section is handed whole to a library: no sibling is read by name
        (
            "Set `tallyho.defaultRegion` to eu in package.json.",
            {
                "scripts/check.ts": 'import { readFileSync } from "node:fs";\n'
                'import { configure } from "rc-lite";\n'
                'configure(JSON.parse(readFileSync("package.json", "utf8")).tallyho);\n'
            },
            PKG_ADD,
        ),
        # the key is read
        (
            "Set `tallyho.defaultRegion` to eu in package.json.",
            {"src/region.ts": "export const pick = (s: { defaultRegion?: string }) => s.defaultRegion;\n"},
            PKG_ADD,
        ),
        # the request builds it
        ("Add a new `tallyho.defaultRegion` setting to package.json and read it in the CLI.", {}, PKG_ADD),
        # the same patch adds its reader
        (
            "Set `tallyho.defaultRegion` to eu in package.json.",
            {},
            [*PKG_ADD, ("src/region.ts", ["export const region = (s: any) => s.defaultRegion;"])],
        ),
        # a nested manifest is not the one the project's identity is read from
        (
            "Set `tallyho.defaultRegion` to eu in packages/web/package.json.",
            {"packages/web/package.json": json.dumps(TALLYHO_PKG, indent=2)},
            [("packages/web/package.json", ['    "defaultRegion": "eu",'])],
        ),
        # a dotted name in a plain config file stays outside rule D (unchanged)
        (
            "Set `send.resend_limit` to 5 in tallyho.toml.",
            {
                "tallyho.toml": "[send]\nbatch_size = 1\n",
                "scripts/send.ts": 'const t = load("tallyho.toml");\nconsole.log(t.send.batch_size);\n',
            },
            [("tallyho.toml", ["resend_limit = 5"])],
        ),
    ],
    ids=[
        "jest-block",
        "jest-dotted",
        "pytest-table",
        "no-section-named",
        "handed-to-a-library",
        "key-is-read",
        "request-builds-it",
        "patch-adds-reader",
        "nested-manifest",
        "dotted-in-config-file",
    ],
)
def test_d_manifest_what_stays_silent(tmp_path, prompt, files, edits):
    assert _dead(tmp_path, {**TALLYHO, **files}, prompt, edits, "tallyho") == []


def test_d_manifest_hold_through_the_engine(tmp_path, monkeypatch):
    """A Codex patch to package.json; the prompt-time check is silent on this imperative wording, so rule D
    holds the first edit and names the dotted setting. Day 6: rule D on its own; with the relied-switch rule
    (C7) on, the prompt-time note names the setting and the premise hold takes this edit
    (``test_day6_premise.py``)."""
    monkeypatch.setattr(premise_switch, "RELIED_SPEAKS", False)
    root, _files = _build(tmp_path / "tallyho", TALLYHO)
    prompt = "Set `tallyho.defaultRegion` to eu in package.json."
    # Day 8: the feasibility reminder off, so this pins the premise rules' own prompt-time output.
    guard = Guard(Settings(notes=NotesSettings(feasibility=False)))
    try:
        guard.workspace(root).index.ready(timeout=30)
        assert translate.dispatch(guard, _prompt(root, prompt))[0] == {}
        out = translate.dispatch(
            guard, _patch(root, _update(root / "package.json", '"tallyho": {', '    "defaultRegion": "eu",'))
        )[0]
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert out["hookSpecificOutput"]["permissionDecisionReason"] == dead_switch.HOLD.format(
            name="tallyho.defaultRegion", where="`package.json`"
        ) + f"\n\n{render.CLOSING}"
    finally:
        guard.close()


# -- S: the Stop backstop's works-today words ----------------------------------------------------------


@pytest.mark.parametrize(
    "request_text, external, claimed",
    [
        ("parcelwren reads `resend_limit` from parcelwren.toml: set it to 5.", frozenset(), True),
        ("The worker takes `resend_limit` from parcelwren.toml; set it to 5.", frozenset(), True),
        ("The daemon loads `resend_limit` at start-up. Set it to 5 in parcelwren.toml.", frozenset(), True),
        (
            "nginx reads `client_max_body_size` from deploy/nginx.conf: set it to 20m.",
            frozenset({"nginx"}),
            False,
        ),
        ("Nothing in our code reads `resend_limit` yet; set it to 5 in parcelwren.toml.", frozenset(), False),
        ("No code reads `resend_limit`; set it in parcelwren.toml.", frozenset(), False),
        ("Set `resend_limit` to 5 in parcelwren.toml.", frozenset(), False),
    ],
    ids=["reads", "takes", "loads", "another-program", "nothing-reads", "no-code-reads", "plain-set"],
)
def test_s_reading_verbs_say_the_switch_works_today(request_text, external, claimed):
    assert (
        config_reads.claimed_to_work(
            request_text, "resend_limit" if "resend" in request_text else "client_max_body_size", external
        )
        is claimed
    )


BEACON_CI = """name: ci
on:
  push:
jobs:
  nightly:
    runs-on: ubuntu-latest
    env:
      BEACON_REGION: eu
    steps:
      - run: python scripts/nightly.py
"""


def test_s_a_config_only_change_to_a_switch_the_request_says_is_read_is_blocked_at_stop(tmp_path):
    repo = make_repo(
        tmp_path / "beacon",
        {
            ".github/workflows/ci.yml": BEACON_CI,
            "beacon/__init__.py": "",
            "beacon/client.py": (
                'import os\n\n\ndef region():\n    return os.environ.get("BEACON_REGION", "us")\n'
            ),
            "scripts/nightly.py": "from beacon.client import region\nprint(region())\n",
        },
    )
    session = StopSession(repo)
    try:
        session.prompt(
            "beacon reads `BEACON_SAMPLE_RATE` for its request sampling. The nightly job samples too "
            "much: halve the sampling in .github/workflows/ci.yml."
        )
        session.replace(
            ".github/workflows/ci.yml",
            "      BEACON_REGION: eu\n",
            '      BEACON_REGION: eu\n      BEACON_SAMPLE_RATE: "0.5"\n',
        )
        held = session.stop(
            "Set `BEACON_SAMPLE_RATE` for the nightly job. The workflow YAML is valid.\n\nFINAL: done"
        )
        assert held["decision"] == "block"
        assert "Nothing in this repository reads `BEACON_SAMPLE_RATE`" in held["reason"]
    finally:
        session.close()


# -- helpers: Codex-shaped payloads ----------------------------------------------------------------------


def _prompt(repo: Path, text: str) -> dict:
    return {
        "session_id": "s",
        "turn_id": "t",
        "cwd": str(repo),
        "hook_event_name": "UserPromptSubmit",
        "prompt": text,
    }


def _update(path: Path, context: str, line: str) -> str:
    return f"*** Update File: {path}\n@@\n {context}\n+{line}\n"


def _patch(repo: Path, body: str) -> dict:
    return {
        "session_id": "s",
        "turn_id": "t",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": f"*** Begin Patch\n{body}*** End Patch\n"},
    }
