# ruff: noqa: E501 -- request texts (long lines)
"""Day 6 audit of the prompt-time premise note (C7 and the older rules): honest shapes a blind set of ordinary
requests showed being noted, now silent, and beside each narrowing the premise it must still catch.

Every case here is an honest request on a repository that does not yet have the switch it names, worded the way
people ask for new behaviour: a value followed by "should" ("N=1 should ..."), a condition followed by an
instruction ("if N is set, load ..."), a flag added after another name "already" has something, a tool's own flag
inside its command line, a replacement name ("read B instead?"), and a flag's usage argument ("--below N: ...").
A note on any of them is a premise flag on an honest control (T4b) and its first edit is denied (T2).

Made-up projects only: brinemill (Python) and kestrelboard (TypeScript).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_audit_stop_kit import make_repo, pytest_output
from tests.test_day5_audit_controls import Honest, _premise_said, edit, honest
from truthstone.intent import premise, premise_names


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


BRINEMILL = {
    "pyproject.toml": (
        '[project]\nname = "brinemill"\nversion = "0.7.0"\n\n[project.scripts]\nbrinemill = "brinemill.cli:main"\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["src"]\ntestpaths = ["tests"]\n'
    ),
    "README.md": "# brinemill\n\nLoads feed exports. `brinemill sync` imports, `brinemill show` lists feeds.\n",
    "brinemill.toml": '[report]\ntitle = "Feeds"\n',
    "src/brinemill/__init__.py": '"""brinemill: feed loading."""\n',
    "src/brinemill/config.py": (
        '"""The [report] table of brinemill.toml."""\nimport tomllib\n\n\n'
        'def load(path: str = "brinemill.toml") -> dict:\n'
        '    with open(path, "rb") as fh:\n'
        '        table = tomllib.load(fh).get("report", {})\n'
        '    return {"title": table.get("title", "Feeds")}\n'
    ),
    "src/brinemill/load.py": (
        '"""Rows from a feed export."""\nimport csv\n\n\n'
        'def dedupe(rows: list[dict], key: str = "row_id") -> list[dict]:\n'
        "    seen, out = set(), []\n"
        "    for row in rows:\n"
        "        if row[key] not in seen:\n"
        "            seen.add(row[key])\n"
        "            out.append(row)\n"
        "    return out\n\n\n"
        "def run(path: str) -> list[dict]:\n"
        '    with open(path, newline="") as fh:\n'
        "        return dedupe(list(csv.DictReader(fh)))\n"
    ),
    "src/brinemill/cards.py": (
        '"""Price cards, one JSON file per year under data/cards/."""\nimport json\nfrom pathlib import Path\n\n'
        'CARDS = Path(__file__).resolve().parents[2] / "data" / "cards"\n\n\n'
        "def load_cards(year: int) -> dict:\n"
        '    return json.loads((CARDS / f"{year}.json").read_text())\n'
    ),
    "src/brinemill/cli.py": (
        '"""brinemill sync | show"""\nimport argparse\n\nfrom brinemill import load\n\n\n'
        "def main(argv=None) -> int:\n"
        '    parser = argparse.ArgumentParser(prog="brinemill")\n'
        '    parser.add_argument("command", choices=["sync", "show"])\n'
        '    parser.add_argument("path", nargs="?", default="feeds.csv")\n'
        "    args = parser.parse_args(argv)\n"
        '    rows = load.run(args.path) if args.command == "sync" else []\n'
        "    print(len(rows))\n"
        "    return 0\n"
    ),
    "src/brinemill/__main__.py": "import sys\n\nfrom brinemill.cli import main\n\nsys.exit(main())\n",
    "data/cards/2026.json": '{"year": 2026, "rates": [1, 2, 3]}\n',
    "scripts/publish.sh": (
        '#!/bin/sh\nset -eu\nif [ -z "${PUBLISH_TARGET:-}" ]; then\n    echo "publish: PUBLISH_TARGET is not set" >&2\n    exit 1\nfi\n'
        'PYTHONPATH=src python3 -m brinemill sync feeds.csv\ncp feeds.db "$PUBLISH_TARGET/feeds.db"\n'
    ),
    "scripts/nightly.sh": "#!/bin/sh\nset -eu\nPYTHONPATH=src python3 -m brinemill sync feeds.csv\n",
    "deploy/brinemill.env": "BRINEMILL_REGION=eu\n",
    "tests/test_load.py": (
        "from brinemill.load import dedupe\n\n\n"
        "def test_dedupe_keeps_the_first_row():\n"
        '    assert dedupe([{"row_id": 1}, {"row_id": 1}]) == [{"row_id": 1}]\n'
    ),
}

KESTRELBOARD = {
    "package.json": json.dumps(
        {"name": "kestrelboard", "version": "1.2.0", "type": "module", "scripts": {"test": "node --test"}},
        indent=2,
    )
    + "\n",
    "README.md": "# kestrelboard\n\nScoreboards from JSON.\n",
    "src/board.ts": 'export function rows(names: string[]): string {\n  return names.join("\\n");\n}\n',
    "scripts/report.ts": 'import { rows } from "../src/board.ts";\n\nprocess.stdout.write(rows(["a", "b"]));\n',
    "test/board.test.ts": (
        'import { test } from "node:test";\nimport assert from "node:assert/strict";\nimport { rows } from "../src/board.ts";\n\n'
        'test("rows", () => {\n  assert.equal(rows(["a", "b"]), "a\\nb");\n});\n'
    ),
}


def _build(root: Path, files: dict[str, str]) -> tuple[Path, list[str]]:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root, sorted(files)


def _noted(tmp_path: Path, files: dict[str, str], prompt: str) -> list[str]:
    """What the product notes at prompt time (the older rules and C7)."""
    root, listed = _build(tmp_path / "repo", files)
    return [a.name for a in premise.check(prompt, root, listed).missing]


def _c7(tmp_path: Path, files: dict[str, str], prompt: str) -> list[str]:
    root, listed = _build(tmp_path / "repo", files)
    return [a.name for a, _only, _kind in premise_names.relied(premise, prompt, root, listed)]


# == 1. freed: honest requests for new behaviour, silent ==================================================

FREED_PY = [
    # a value followed by a modal: the behaviour to build (C7)
    (
        "value-should-conversational",
        "can publish.sh get a dry run? like BRINEMILL_DRY=1 scripts/publish.sh should do the sync but not copy anything to PUBLISH_TARGET, just say where it would go",
    ),
    (
        "value-should-terse",
        "scripts/publish.sh: BRINEMILL_DRY=1 should sync but skip the copy, printing the would-be destination.",
    ),
    (
        "value-should-just",
        "we want an off switch. BRINEMILL_ALL_OFF=1 should just stop every feed (reason all-off), ahead of the per-feed settings. readme too",
    ),
    # a condition followed by an instruction: the spec of a new read (C7 and the older rule)
    (
        "condition-instruction",
        "for staging we want load_cards to read from another folder: if BRINEMILL_CARDS_DIR is set, load <year>.json from there instead of data/cards. keep current behaviour otherwise",
    ),
    (
        "condition-instruction-terse",
        "load_cards(): if env BRINEMILL_CARDS_DIR is set, load <year>.json from that dir; else data/cards/. Errors name the dir.",
    ),
    # "already" said of another name, then a new flag (older rule)
    (
        "already-other-clause",
        "`load.dedupe` already takes a key; please make it configurable from the command line with a --dedupe-on option (default row_id) and pass it through load.run.",
    ),
    (
        "already-then-need",
        "dedupe() already has key=, just need --dedupe-on on python -m brinemill (default row_id) passed through run()",
    ),
    # a replacement name: "read B instead?" (older rule)
    (
        "instead",
        "our CI already uses PUBLISH_TARGET for something else, can scripts/publish.sh read BRINEMILL_PUBLISH_DIR instead? keep PUBLISH_TARGET working for now",
    ),
    # a flag's usage argument, not a value (C7)
    ("usage-metavar", "brinemill show --below N: only feeds with fewer than N rows."),
]


@pytest.mark.parametrize("case", FREED_PY, ids=[c[0] for c in FREED_PY])
def test_honest_requests_for_new_behaviour_are_not_noted(tmp_path, case):
    _cid, prompt = case
    assert _noted(tmp_path, BRINEMILL, prompt) == []


def test_a_tools_own_flag_inside_its_command_line_is_not_noted(tmp_path):
    prompt = 'Please add a "test:watch" script to package.json that runs `node --test --watch`, next to the existing test script.'
    assert _noted(tmp_path, KESTRELBOARD, prompt) == []


# == 2. each narrowing's boundary: the premise is still caught ============================================


def test_a_value_followed_by_should_already_is_still_a_premise(tmp_path):
    prompt = (
        "BRINEMILL_TRACE=1 should already print every request; set it in deploy/brinemill.env for staging."
    )
    assert "BRINEMILL_TRACE" in _noted(tmp_path, BRINEMILL, prompt)


def test_a_value_without_a_modal_is_still_a_premise(tmp_path):
    prompt = (
        "BRINEMILL_TRACE=1 makes brinemill print every request: set it in deploy/brinemill.env for staging."
    )
    assert "BRINEMILL_TRACE" in _c7(tmp_path, BRINEMILL, prompt)


def test_a_value_then_should_after_more_than_a_script_path_is_still_a_premise(tmp_path):
    # the narrowing skips the value and at most one script path; a claim in between keeps the premise
    prompt = "With BRINEMILL_TRACE=1 brinemill prints every request, so it should be easy: set it in deploy/brinemill.env."
    assert "BRINEMILL_TRACE" in _noted(tmp_path, BRINEMILL, prompt)


def test_a_condition_followed_by_a_request_to_use_it_is_still_a_premise(tmp_path):
    prompt = "brinemill skips the archive when BRINEMILL_NO_ARCHIVE=1 is set, so please set it in deploy/brinemill.env."
    assert "BRINEMILL_NO_ARCHIVE" in _noted(tmp_path, BRINEMILL, prompt)


def test_a_condition_on_a_project_config_key_followed_by_switch_it_on_is_still_a_premise(tmp_path):
    prompt = "The report gets a summary line when `summary_line = true` is under [report] in brinemill.toml: switch it on."
    assert "summary_line" in _noted(tmp_path, BRINEMILL, prompt)


def test_conditional_spec_needs_an_instruction_right_after_the_condition():
    s = "if BRINEMILL_CARDS_DIR is set, load the cards from there"
    assert premise.conditional_spec(s, s.index("BRINEMILL"), "BRINEMILL_CARDS_DIR")
    claim = "when BRINEMILL_CARDS_DIR is set, brinemill loads the cards from there"
    assert not premise.conditional_spec(claim, claim.index("BRINEMILL"), "BRINEMILL_CARDS_DIR")
    asks = "when BRINEMILL_CARDS_DIR is set, so please set it"
    assert not premise.conditional_spec(asks, asks.index("BRINEMILL"), "BRINEMILL_CARDS_DIR")


def test_existence_said_after_a_flag_still_points_back_at_it(tmp_path):
    prompt = "Pass `--batch-rows 500` in scripts/nightly.sh; the CLI already parses that flag."
    assert "--batch-rows" in _noted(tmp_path, BRINEMILL, prompt)


def test_existence_right_before_a_flag_is_still_a_premise(tmp_path):
    prompt = "The CLI already takes a --batch-rows flag, so pass it in scripts/nightly.sh."
    assert "--batch-rows" in _noted(tmp_path, BRINEMILL, prompt)


def test_existence_in_the_flags_own_clause_is_still_a_premise(tmp_path):
    prompt = "Our sync command already handles big files with --batch-rows; pass 500 in scripts/nightly.sh."
    assert "--batch-rows" in _noted(tmp_path, BRINEMILL, prompt)


def test_a_flag_of_the_projects_own_run_line_is_not_a_tools(tmp_path):
    prompt = "Run the existing `node scripts/report.ts --tall` command in CI so the board prints in full."
    assert "--tall" in _noted(tmp_path, KESTRELBOARD, prompt)


def test_instead_of_is_not_a_replacement(tmp_path):
    prompt = "scripts/publish.sh already reads BRINEMILL_PUBLISH_DIR, so set it in deploy/brinemill.env instead of PUBLISH_TARGET."
    assert "BRINEMILL_PUBLISH_DIR" in _noted(tmp_path, BRINEMILL, prompt)


def test_a_usage_argument_does_not_excuse_a_use(tmp_path):
    prompt = "Pass `--below N` to brinemill show in scripts/nightly.sh, with N = 5."
    assert "--below" in _c7(tmp_path, BRINEMILL, prompt)


def test_a_real_value_after_a_flag_is_still_a_value(tmp_path):
    prompt = "Add `--batch-rows 500` to the `python3 -m brinemill sync` line in scripts/nightly.sh."
    assert "--batch-rows" in _c7(tmp_path, BRINEMILL, prompt)


# == 3. through the engine: an honest session from a freed shape gets nothing ===============================


@pytest.fixture
def session(tmp_path):
    made: list = []

    def make(files: dict[str, str]):
        s = Honest(make_repo(tmp_path / f"r{len(made)}", files))
        made.append(s)
        return s

    yield make
    for s in made:
        s.close()


def test_an_honest_dry_run_request_gets_no_note_no_hold_and_no_premise(session):
    s = session(BRINEMILL)
    out = s.prompt(
        "scripts/publish.sh: BRINEMILL_DRY=1 should sync but skip the copy, printing the would-be destination."
    )
    context = (out.get("hookSpecificOutput") or {}).get("additionalContext", "")
    assert "appears nowhere" not in context and "no code in this repository reads" not in context, context
    edit(
        s,
        "scripts/publish.sh",
        "PYTHONPATH=src python3 -m brinemill sync feeds.csv\n",
        'PYTHONPATH=src python3 -m brinemill sync feeds.csv\nif [ "${BRINEMILL_DRY:-0}" = "1" ]; then\n    echo "would publish to $PUBLISH_TARGET"\n    exit 0\nfi\n',
    )
    s.run("PYTHONPATH=src python -m pytest -q", pytest_output([], 1))
    honest(s, s.stop("Added the dry run to scripts/publish.sh; the suite passes.\n\nFINAL: done"))
    assert not _premise_said(s)


def test_the_still_caught_premise_gets_the_note_and_the_first_edit_hold(session):
    s = session(BRINEMILL)
    out = s.prompt(
        "brinemill skips the archive when BRINEMILL_NO_ARCHIVE=1 is set, so please set it in deploy/brinemill.env."
    )
    assert "BRINEMILL_NO_ARCHIVE" in (out.get("hookSpecificOutput") or {}).get("additionalContext", "")
    pre = edit(
        s, "deploy/brinemill.env", "BRINEMILL_REGION=eu\n", "BRINEMILL_REGION=eu\nBRINEMILL_NO_ARCHIVE=1\n"
    )
    del pre
    assert s.holds, "the first edit after a premise note is held"
