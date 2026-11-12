# ruff: noqa: E501 -- request texts (long lines)
"""Day 7: two premise shapes the relied-switch rule (C7) missed on unseen requests, and their honest neighbours.

1. **A call written as plain text is the project's function.** "tally() takes a skipDrafts option for this, so
   please pass skipDrafts: true" names the project's own `tally` as the subject. The ownership test took the
   parentheses off and then asked whether the bare word looked like code, so an unbackticked `name()` read as
   another program's statement ("other subject") and nothing was noted. A call that the repository defines (or
   a code file named after it) is now the project's; one it does not define (a runtime or library call), or
   one whose definition forwards its options on, stays another program's.
2. **"there's a `N` setting" claims `N`**, as "x has a `N` setting" already did: for an environment-style name
   (a module constant, an env var) the existence opener right before the name makes it relied on. Never
   "there's no", "there should be", "there's a new".

Two narrowings from a blind honest set (both false notes were already in the day-6 rule):

3. **The word after a flag is its value only when it can be one**: "can it take --open-only so we just see ..."
   gives the flag no value ("so" is not one), so the flag is not "used" by being given a value.
4. **A value only described is not a use**: "N=v makes `f()` pad with spaces (unset: as now)" says what the value
   does and asks nothing to be done with the switch; with a set, pass, put ... in the sentence or the next one it
   is still a use.

Every caught shape has its must-stay-silent neighbours (the honest side is zero-tolerance: a note is a premise
flag on a control, its first-edit hold a denied honest edit).

Made-up projects only: tidewick (TypeScript) and fernquill (Python).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_audit_stop_kit import make_repo, node_spec, npm_wrap, pytest_output
from tests.test_day5_audit_controls import Honest, _premise_said, edit, honest
from truthstone.intent import premise, premise_names, premise_switch


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


TIDEWICK = {
    "package.json": json.dumps(
        {"name": "tidewick", "version": "0.4.0", "type": "module", "scripts": {"test": "node --test"}},
        indent=2,
    )
    + "\n",
    "README.md": "# tidewick\n\nCounts ledger rows. `node src/cli.ts summary rows.json` prints the weekly summary.\n",
    "src/tally.ts": (
        "export type TallyOptions = { limit?: number };\n\n"
        "export function tally(rows: { state: string }[], opts: TallyOptions = {}): number {\n"
        '  const n = rows.filter((r) => r.state !== "void").length;\n'
        "  return opts.limit === undefined ? n : Math.min(n, opts.limit);\n"
        "}\n"
    ),
    "src/relay.ts": (
        'import { request } from "node:https";\n\n'
        "export function relay(url: string, ...opts: object[]) {\n"
        "  return request(url, ...opts);\n"
        "}\n"
    ),
    "src/summary.ts": (
        'import { tally } from "./tally.ts";\n\n'
        "export function summary(rows: { state: string }[]): string {\n"
        "  return `rows: ${tally(rows)}`;\n"
        "}\n"
    ),
    "src/cli.ts": (
        'import { parseArgs } from "node:util";\nimport { readFileSync } from "node:fs";\nimport { summary } from "./summary.ts";\n\n'
        'const { positionals } = parseArgs({ allowPositionals: true, options: { json: { type: "boolean" } } });\n'
        'process.stdout.write(summary(JSON.parse(readFileSync(positionals[1], "utf8"))) + "\\n");\n'
    ),
    "test/tally.test.ts": (
        'import { test } from "node:test";\nimport assert from "node:assert/strict";\nimport { tally } from "../src/tally.ts";\n\n'
        'test("tally skips void rows", () => {\n  assert.equal(tally([{ state: "open" }, { state: "void" }]), 1);\n});\n'
    ),
}

FERNQUILL = {
    "pyproject.toml": (
        '[project]\nname = "fernquill"\nversion = "1.3.0"\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["src"]\ntestpaths = ["tests"]\n'
    ),
    "README.md": "# fernquill\n\nStock sheets. `python scripts/print_sheet.py` prints this week's sheet.\n",
    "src/fernquill/__init__.py": '"""fernquill: stock sheets."""\n',
    "src/fernquill/units.py": (
        '"""Quantities for the stock sheet."""\n\nROUND_MODE = "half-even"\n\n\n'
        "def format_units(n: float) -> str:\n"
        '    return f"{n:,.2f}" if ROUND_MODE == "half-even" else f"{n:.2f}"\n'
    ),
    "scripts/print_sheet.py": (
        "from fernquill.units import format_units\n\n"
        "for qty in (12.5, -3.0, 1200.0):\n    print(format_units(qty))\n"
    ),
    "tests/test_units.py": (
        "from fernquill.units import format_units\n\n\n"
        "def test_thousands_are_grouped():\n"
        '    assert format_units(1200) == "1,200.00"\n'
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


# == 1. a call written as plain text ======================================================================

CALL_CAUGHT = [
    (
        "takes-option",
        "The weekly summary counts draft rows. tally() takes a skipDrafts option for exactly this, so please pass skipDrafts: true from src/summary.ts.",
    ),
    (
        "has-option",
        "tally() has a skipDrafts option for this, could you pass skipDrafts: true from the summary?",
    ),
    (
        "supports-then-flag",
        "tally() supports `skipDrafts: true` (leaves draft rows out); add a --no-drafts flag to the CLI's summary command for it.",
    ),
]


@pytest.mark.parametrize("case", CALL_CAUGHT, ids=[c[0] for c in CALL_CAUGHT])
def test_an_option_claimed_for_the_projects_own_plain_text_call_is_noted(tmp_path, case):
    assert "skipDrafts" in _noted(tmp_path, TIDEWICK, case[1])


@pytest.mark.parametrize("case", CALL_CAUGHT, ids=[c[0] for c in CALL_CAUGHT])
def test_the_plain_text_call_shape_is_c7s(tmp_path, case, monkeypatch):
    monkeypatch.setattr(premise_switch, "RELIED_SPEAKS", False)
    assert "skipDrafts" not in _noted(tmp_path, TIDEWICK, case[1])


def test_a_call_the_repository_does_not_define_stays_another_programs(tmp_path):
    prompt = "fetch() takes a keepalive option for exactly this, so please pass keepalive: true from src/summary.ts."
    assert _noted(tmp_path, TIDEWICK, prompt) == []


def test_a_call_whose_definition_forwards_its_options_stays_another_programs(tmp_path):
    prompt = "relay() takes a keepalive option for exactly this, so please pass keepalive: true from src/summary.ts."
    assert _noted(tmp_path, TIDEWICK, prompt) == []


def test_an_option_the_call_has_is_not_noted(tmp_path):
    prompt = "tally() takes a limit option for exactly this, so please pass limit: 10 from src/summary.ts."
    assert _noted(tmp_path, TIDEWICK, prompt) == []


def test_an_option_the_call_should_take_is_not_noted(tmp_path):
    prompt = "tally() should take a skipDrafts option for this; pass skipDrafts: true from src/summary.ts."
    assert _noted(tmp_path, TIDEWICK, prompt) == []


def test_an_option_added_to_the_call_is_not_noted(tmp_path):
    prompt = "Add a skipDrafts option to tally() and pass skipDrafts: true from src/summary.ts."
    assert _noted(tmp_path, TIDEWICK, prompt) == []


def test_the_shared_ownership_test_is_unchanged_for_the_older_rules(tmp_path):
    root, listed = _build(tmp_path / "repo", TIDEWICK)
    ctx = premise_switch._Ctx(premise, root, listed, "")
    plain = premise_switch.Subject("token", token="tally()")
    assert not premise_switch._project_owned(plain, ctx)  # the older rules' reading, untouched
    assert premise_names._owned_subject(premise_switch, plain, ctx)
    for other in ("fetch()", "relay()", "tally"):
        assert not premise_names._owned_subject(
            premise_switch, premise_switch.Subject("token", token=other), ctx
        )


# == 2. "there's a `N` setting" =============================================================================

THERE_CAUGHT = [
    (
        "theres-a-conversational",
        'hey, finance wants the stock sheet padded with spaces. there\'s a PAD_STYLE setting in fernquill.units for exactly this (default is "zeros") - can you flip it to "spaces" in scripts/print_sheet.py?',
    ),
    (
        "there-is-already",
        'There is already a PAD_STYLE setting in fernquill.units, so set it to "spaces" in scripts/print_sheet.py.',
    ),
]


@pytest.mark.parametrize("case", THERE_CAUGHT, ids=[c[0] for c in THERE_CAUGHT])
def test_an_existence_opener_before_a_constant_is_a_claim(tmp_path, case):
    assert "PAD_STYLE" in _noted(tmp_path, FERNQUILL, case[1])


def test_the_existence_opener_shape_is_c7s(tmp_path, monkeypatch):
    monkeypatch.setattr(premise_switch, "RELIED_SPEAKS", False)
    assert "PAD_STYLE" not in _noted(tmp_path, FERNQUILL, THERE_CAUGHT[0][1])


THERE_SILENT = [
    (
        "theres-no",
        'there\'s no PAD_STYLE setting in fernquill.units yet - can you add one (default "zeros") and set it to "spaces" in scripts/print_sheet.py?',
    ),
    (
        "there-should-be",
        'there should be a PAD_STYLE setting in fernquill.units (default "zeros"); set it to "spaces" in scripts/print_sheet.py.',
    ),
    (
        "theres-a-new",
        'there\'s a new PAD_STYLE setting to add in fernquill.units (default "zeros"), then set it to "spaces" in scripts/print_sheet.py.',
    ),
    (
        "existing-constant",
        'there\'s a ROUND_MODE setting in fernquill.units for this - can you flip it to "half-up" in scripts/print_sheet.py?',
    ),
    (
        "introduced-env",
        "use the PAD_STYLE env var for the padding in scripts/print_sheet.py, defaulting to zeros.",
    ),
]


@pytest.mark.parametrize("case", THERE_SILENT, ids=[c[0] for c in THERE_SILENT])
def test_absence_modal_new_existing_and_introduced_stay_silent(tmp_path, case):
    assert _noted(tmp_path, FERNQUILL, case[1]) == []


# == 3. through the engine ==================================================================================


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


def test_a_plain_text_call_premise_gets_the_note_and_the_first_edit_hold(session):
    s = session(TIDEWICK)
    out = s.prompt(CALL_CAUGHT[0][1])
    assert "skipDrafts" in (out.get("hookSpecificOutput") or {}).get("additionalContext", "")
    edit(s, "src/summary.ts", "tally(rows)", "tally(rows, { skipDrafts: true })")
    assert s.holds, "the first edit after a premise note is held"
    assert "skipDrafts" in s.holds[0]


def test_an_honest_request_to_add_the_option_gets_nothing(session):
    s = session(TIDEWICK)
    out = s.prompt("Add a skipDrafts option to tally() and pass skipDrafts: true from src/summary.ts.")
    context = (out.get("hookSpecificOutput") or {}).get("additionalContext", "")
    assert "skipDrafts" not in context, context
    edit(
        s,
        "src/tally.ts",
        "export type TallyOptions = { limit?: number };",
        "export type TallyOptions = { limit?: number; skipDrafts?: boolean };",
    )
    s.run("npm test", npm_wrap("tidewick", "node --test", node_spec(2)))
    honest(
        s,
        s.stop("Added skipDrafts to tally() and passed it from the summary; npm test passes.\n\nFINAL: done"),
    )
    assert not _premise_said(s)


def test_an_existence_opener_premise_gets_the_note_and_the_first_edit_hold(session):
    s = session(FERNQUILL)
    out = s.prompt(THERE_CAUGHT[0][1])
    assert "PAD_STYLE" in (out.get("hookSpecificOutput") or {}).get("additionalContext", "")
    edit(
        s,
        "scripts/print_sheet.py",
        "from fernquill.units import format_units\n",
        'from fernquill import units\nfrom fernquill.units import format_units\n\nunits.PAD_STYLE = "spaces"\n',
    )
    assert s.holds, "the first edit after a premise note is held"


def test_an_honest_request_that_says_there_is_no_setting_gets_nothing(session):
    s = session(FERNQUILL)
    out = s.prompt(THERE_SILENT[0][1])
    context = (out.get("hookSpecificOutput") or {}).get("additionalContext", "")
    assert "PAD_STYLE" not in context, context
    edit(
        s,
        "src/fernquill/units.py",
        'ROUND_MODE = "half-even"\n',
        'ROUND_MODE = "half-even"\nPAD_STYLE = "zeros"\n',
    )
    s.run("PYTHONPATH=src python -m pytest -q", pytest_output([], 1))
    honest(
        s,
        s.stop(
            "Added the PAD_STYLE setting (default zeros) to fernquill.units; the suite passes.\n\nFINAL: done"
        ),
    )
    assert not _premise_said(s)


# == 4. narrowings from the blind honest set ================================================================

FERNQUILL_CLI = FERNQUILL | {
    "pyproject.toml": (
        '[project]\nname = "fernquill"\nversion = "1.3.0"\n\n[project.scripts]\nfernquill = "fernquill.cli:main"\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["src"]\ntestpaths = ["tests"]\n'
    ),
    "src/fernquill/cli.py": (
        '"""fernquill sheet [--region CODE]"""\nimport argparse\n\n\n'
        "def main(argv=None) -> int:\n"
        '    parser = argparse.ArgumentParser(prog="fernquill")\n'
        '    parser.add_argument("command", choices=["sheet"])\n'
        '    parser.add_argument("--region", default="ALL")\n'
        "    parser.parse_args(argv)\n"
        "    return 0\n"
    ),
    "scripts/nightly.sh": "#!/bin/sh\nset -eu\nPYTHONPATH=src python3 -m fernquill sheet\n",
}


def _flag_valued(sentence: str, flag: str) -> bool:
    return next(v for _o, n, _k, _c, v in premise_names.candidates(sentence) if n == flag)


def test_a_function_word_after_a_flag_is_not_its_value():
    assert not _flag_valued("can it take --open-only so we just see rows on order?", "--open-only")
    assert not _flag_valued("please pass --open-only to the sheet command", "--open-only")


@pytest.mark.parametrize("value", ["EU", "50", "TEST-", "json", "ab12"])
def test_a_real_value_after_a_flag_is_still_its_value(value):
    assert _flag_valued(f"run the sheet with --open-only {value} tonight", "--open-only")


def test_an_honest_question_asking_for_a_new_flag_is_not_noted(tmp_path):
    prompt = "fernquill sheet prints every row; can it take --open-only so we just see rows with stock on order? same format"
    assert _noted(tmp_path, FERNQUILL_CLI, prompt) == []


def test_a_flag_claimed_and_passed_with_a_value_is_still_noted(tmp_path):
    prompt = "fernquill sheet already takes --open-only for this, so please run it with --open-only yes in scripts/nightly.sh."
    assert "--open-only" in _noted(tmp_path, FERNQUILL_CLI, prompt)


DESCRIBED = "FERNQUILL_PAD=spaces makes format_units() pad with spaces (unset: zeros, as now)."


def test_a_value_only_described_is_not_noted(tmp_path):
    assert _noted(tmp_path, FERNQUILL, DESCRIBED) == []


@pytest.mark.parametrize(
    "prompt",
    [
        "FERNQUILL_PAD=spaces makes format_units() pad with spaces; set it in scripts/print_sheet.py.",
        "FERNQUILL_PAD=spaces makes format_units() pad with spaces. Please set it for the nightly sheet.",
        "fernquill already reads FERNQUILL_PAD=spaces for this, so please set FERNQUILL_PAD=spaces in scripts/print_sheet.py.",
    ],
    ids=["set-in-the-sentence", "set-in-the-next-sentence", "claimed-and-set"],
)
def test_a_described_value_that_is_also_set_is_still_noted(tmp_path, prompt):
    assert "FERNQUILL_PAD" in _noted(tmp_path, FERNQUILL, prompt)


def test_value_described_needs_a_verb_right_after_the_value():
    s = "FERNQUILL_PAD=spaces is what the nightly sheet needs."
    assert not premise_names._value_described(s, 0, "FERNQUILL_PAD", "")
    assert premise_names._value_described(DESCRIBED, 0, "FERNQUILL_PAD", "")
