"""C1, day 4 (``intent/premise_switch.py``): pinned, prompt by prompt, to the frozen prototypes.

The specification is ``premise_proto_v52.py`` over ``premise_proto_v43.py`` (FROZEN-v3.txt). The expected
results in ``tests/data/premise_batteries/expected-c1.json`` were computed by those prototypes, installed
on release-day3, from the very files beside it:

* ``v52``: v5.2 installed, the result when ``USED_SWITCH_SPEAKS`` is True. Battery rows equal
  ``blind-results-b1-v52-dev.json`` and ``blind-results-b2-v52-dev.json``.
* ``speaking``: v4.3 installed alone, then v5.2's final precision filter: what is noted when
  ``USED_SWITCH_SPEAKS`` is False (battery 3's registered decision). Battery rows equal the v4.3 rows of
  ``blind-results.json`` and ``blind-results-b2.json`` less the filter's two drops.
* ``recorded``: v52 less speaking, on ``Premise.recorded`` when the used-switch rule only records.

The battery copies are byte-identical to the frozen files (their SHA-256 is pinned below). The probes
and the development tables are JSON conversions of the frozen tools; two identifiers the leakage lint
objects to were renamed in the copy and re-pinned.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from truthstone.adapters.codex import translate
from truthstone.bench.codex.premise import names_absence
from truthstone.core.config import NotesSettings, Settings
from truthstone.core.engine import Guard
from truthstone.intent import premise, premise_switch

DATA = Path(__file__).resolve().parent / "data" / "premise_batteries"
EXPECTED = json.loads((DATA / "expected-c1.json").read_text(encoding="utf-8"))["cases"]

# Day 5 (``premise_switch._READS_BEFORE`` and "set/put ... there" in ``_verb_back``, beyond the prototypes):
# the only pinned values that move, re-pinned here so the frozen file stays the prototypes' record. v5.2's
# result (``v52``, ``v52_only_in``) moves nowhere. Four false-premise prompts ("<subject> takes/reads
# `x` ...") are now noted by v4.3 itself, so what was only ``recorded`` is ``speaking``; on four more prompts
# (three false premises, one honest probe whose `--out` the repository has) only ``assertions()`` grows,
# which is read for names already noted only (``premise_unmet``, the engine's ``again``), so nothing else
# changes.
DAY5 = {
    "b1/fp05-ratelimiter-burst-size-canonical::fp05-ratelimiter-burst-size-canonical": {
        "assertions": ["burst_size"], "speaking": ["burst_size"], "recorded": []},
    "b1/fp05-ratelimiter-burst-size-conversational::fp05-ratelimiter-burst-size-conversational": {
        "assertions": ["burst_size"], "speaking": ["burst_size"], "recorded": []},
    "b1/fp07-backup-compress-env-canonical::fp07-backup-compress-env-canonical": {
        "assertions": ["BACKUP_COMPRESS"], "speaking": ["BACKUP_COMPRESS"], "recorded": []},
    "b2/stockpot-scale-fractions-kwarg--canonical::stockpot-scale-fractions-kwarg--canonical": {
        "assertions": ["round_to_fractions"], "speaking": ["round_to_fractions"], "recorded": []},
    "b1/fp14-label-return-address-conversational::fp14-label-return-address-conversational": {
        "assertions": ["include_return_address"]},
    "b1/fp17-resize-keep-exif-conversational::fp17-resize-keep-exif-conversational": {
        "assertions": ["--keep-exif"]},
    "b2/trailmix-simplify-tolerance-flag--terse::trailmix-simplify-tolerance-flag--terse": {
        "assertions": ["--tolerance"]},
    "probes::probe23": {"assertions": ["--out"]},
}


def _expected(key: str) -> dict:
    return {**EXPECTED[key], **DAY5.get(key, {})}


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)
    # Day 6: the pins are C1's (the frozen prototypes, with the day-5 changes above). The relied-switch
    # rule (C7, ``intent/premise_names.py``) adds its names after C1 in ``premise.check``; it is switched
    # off here so every pinned value stays the prototypes' record. Its own results on these batteries are
    # measured in ``.claude/handoff/day5/fix-premise2.md`` and its shapes tested in ``test_day6_premise.py``.
    monkeypatch.setattr(premise_switch, "RELIED_SPEAKS", False)


def _text(content) -> str:
    if isinstance(content, list):
        return "\n".join(content)
    return content if isinstance(content, str) else json.dumps(content)


def _build(root: Path, files: dict) -> list[str]:
    out = []
    for rel, content in sorted(files.items()):
        rel = rel.lstrip("/")
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, dict) and "generated_bytes" in content:
            line = "export const generated_0000000 = 0;\n"
            count = content["generated_bytes"] // len(line) + 1
            path.write_text(
                "".join(line.replace("0000000", f"{i:07d}") for i in range(count)) + _text(content["tail"])
            )
        else:
            path.write_text(_text(content))
        out.append(rel)
    return out


def _groups() -> list[tuple[str, str, dict, list[str] | None, list[tuple[str, str, str]]]]:
    """(group id, root directory name, files, index or None, [(case key, prompt, want)])."""
    groups = []
    for name in ("b1", "b2"):
        for line in (DATA / f"{name}-premise.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            files = {
                k.lstrip("/"): v for k, v in (row.get("repo") or {}).items() if ".." not in Path(k).parts
            }
            want = "note" if row["set"] == "fp" else "silent"
            groups.append(
                (
                    f"{name}/{row['id']}",
                    "blind-root",
                    files,
                    None,
                    [(f"{name}/{row['id']}::{row['id']}", row["prompt"], want)],
                )
            )
    probes = json.loads((DATA / "r3_probes.json").read_text(encoding="utf-8"))
    groups.append(
        (
            "probes",
            "acme-probe",
            probes["repo"],
            None,
            [(f"probes::probe{i}", p["prompt"], p["want"]) for i, p in enumerate(probes["probes"])],
        )
    )
    dev = json.loads((DATA / "c1-dev-tables.json").read_text(encoding="utf-8"))
    for g in dev["groups"]:
        groups.append(
            (
                g["id"],
                g["root"],
                g["files"],
                g["index"],
                [(f"{g['id']}::{c['id']}", c["prompt"], c["want"]) for c in g["cases"]],
            )
        )
    return groups


GROUPS = _groups()


def test_the_battery_copies_are_the_frozen_files():
    for name, frozen in (
        ("b1-premise.jsonl", "aa03f94e6cdbb898d6de49cb3e17ae34b5c0616693d1c8b306760fba43af5fe0"),
        ("b2-premise.jsonl", "06a63f64131cfbe098ffae9bd9ff62ebfb93a285e9cabf507f1d9f40a8d5f0be"),
    ):
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == frozen, name
    probes = json.loads((DATA / "r3_probes.json").read_text(encoding="utf-8"))
    assert probes["source_sha256"] == "1d41b37bcd534eff9e1c59a85226ef9c690a4e815679eba7f675e2d08bdcaae4"
    assert len(probes["probes"]) == 36
    assert len(EXPECTED) == sum(len(cases) for *_, cases in GROUPS) == 440


@pytest.mark.parametrize("group", GROUPS, ids=[g[0] for g in GROUPS])
def test_each_prompt_gives_the_frozen_prototypes_result(group, tmp_path, monkeypatch):
    _gid, rootname, files, index, cases = group
    root = tmp_path / rootname
    root.mkdir()
    built = _build(root, files)
    listed = list(index) if index is not None else built
    for key, prompt, _want in cases:
        expected = _expected(key)
        monkeypatch.setattr(premise_switch, "USED_SWITCH_SPEAKS", True)
        speaking = premise.check(prompt, root, listed)
        assert [a.name for a in speaking.missing] == expected["v52"], key
        assert speaking.only_in == expected["v52_only_in"], key
        assert speaking.recorded == [], key
        assert [a.name for a in premise.assertions(prompt)] == expected["assertions"], key
        monkeypatch.setattr(premise_switch, "USED_SWITCH_SPEAKS", False)
        recording = premise.check(prompt, root, listed)
        assert [a.name for a in recording.missing] == expected["speaking"], key
        assert recording.only_in == expected["speaking_only_in"], key
        assert [a.name for a in recording.recorded] == expected["recorded"], key
        assert [a.name for a in premise.assertions(prompt)] == expected["assertions"], key


def test_the_probes_are_never_wrong_when_the_used_switch_rule_speaks():
    """The round-3 review probes: v5.2 gets all 36 right (0 wrong); recorded-only, the used-switch
    probes are recorded instead of noted."""
    probes = next(cases for gid, *_rest, cases in GROUPS if gid == "probes")
    wrong = [key for key, _p, want in probes if (want == "note") != bool(EXPECTED[key]["v52"])]
    assert wrong == []
    unspoken = [key for key, _p, want in probes if want == "note" and not EXPECTED[key]["speaking"]]
    assert all(EXPECTED[key]["recorded"] for key in unspoken)


def test_battery_recall_and_honest_notes_as_measured():
    """The development record (FIX-DESIGN v4, section C1): v5.2 on battery 1 notes 57 of 60 false
    premises and 0 of 45 honest prompts; on battery 2, 63 of 72 and 0 of 60."""

    def tally(name: str, column: str) -> tuple[int, int]:
        fp = honest = 0
        for gid, _r, _f, _i, cases in GROUPS:
            if gid.startswith(f"{name}/"):
                ((key, _p, want),) = cases
                noted = bool(EXPECTED[key][column])
                fp += noted and want == "note"
                honest += noted and want == "silent"
        return fp, honest

    assert tally("b1", "v52") == (57, 0)
    assert tally("b2", "v52") == (63, 0)


def test_the_used_switch_rule_ships_recorded_only():
    """Battery 3's registered decision (5/60 honest notes > 1 and > today's 4/60)."""
    assert premise_switch.USED_SWITCH_SPEAKS is False


# -- what a recorded name never reaches -------------------------------------------------------------


def _probe_repo(tmp_path: Path) -> Path:
    probes = json.loads((DATA / "r3_probes.json").read_text(encoding="utf-8"))
    root = tmp_path / "acme-probe"
    root.mkdir()
    _build(root, probes["repo"])
    return root


USED = "Pass `--totals` to `acme/report.py` in the cron line."  # a used switch nothing reads (a probe)


def _prompt(repo: Path, text: str) -> dict:
    return {
        "session_id": "s",
        "turn_id": "t",
        "cwd": str(repo),
        "hook_event_name": "UserPromptSubmit",
        "prompt": text,
    }


def _readme_patch(repo: Path) -> dict:
    readme = repo / "README.md"
    command = f"*** Begin Patch\n*** Update File: {readme}\n@@\n # acme\n+Nightly totals.\n*** End Patch\n"
    return {
        "session_id": "s",
        "turn_id": "t",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": command},
    }


def test_a_recorded_name_is_never_noted_held_or_answered_to(tmp_path):
    repo = _probe_repo(tmp_path)
    found = premise.check(
        USED, repo, [p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file()]
    )
    assert found.missing == [] and [a.name for a in found.recorded] == ["--totals"]
    assert found.note == "" and found.hold == "" and found.finding() is None
    assert "--totals" not in [a.name for a in premise.assertions(USED)]  # premise_unmet's names
    # Day 8: the feasibility reminder off, so this pins the premise rules' own prompt-time output.
    guard = Guard(Settings(notes=NotesSettings(feasibility=False)))
    try:
        ws = guard.workspace(repo)
        ws.index.ready(timeout=30)
        out, _results, decision = translate.dispatch(guard, _prompt(repo, USED))
        assert out == {} and not decision.findings
        assert ws.current_spec.premises == []
        assert not ws.premises_noted.get("s")
        assert translate.dispatch(guard, _readme_patch(repo))[0] == {}  # no premise hold
    finally:
        guard.close()


def test_when_the_used_switch_rule_speaks_its_name_is_noted_and_answered_to(tmp_path, monkeypatch):
    monkeypatch.setattr(premise_switch, "USED_SWITCH_SPEAKS", True)
    repo = _probe_repo(tmp_path)
    guard = Guard(Settings())
    try:
        ws = guard.workspace(repo)
        ws.index.ready(timeout=30)
        out, _results, _decision = translate.dispatch(guard, _prompt(repo, USED))
        assert out["hookSpecificOutput"]["additionalContext"].startswith("`--totals` appears nowhere")
        assert ws.current_spec.premises == ["--totals"]
        held = translate.dispatch(guard, _readme_patch(repo))[0]
        assert held["hookSpecificOutput"]["permissionDecision"] == "deny"
    finally:
        guard.close()
    assert "--totals" not in [a.name for a in premise.assertions(USED)]  # comp-3-4: never premise_unmet's


# -- the note's and the hold's words ----------------------------------------------------------------


def _symbol(name: str) -> premise.Assertion:
    return premise.Assertion(
        name, "symbol", (name.removesuffix("()"), name.removesuffix("()").rpartition(".")[2])
    )


@pytest.mark.parametrize(
    "found, names",
    [
        (premise.Premise(missing=[premise.Assertion("ACME_TRACE", "env", ("ACME_TRACE",))]), ["ACME_TRACE"]),
        (
            premise.Premise(
                missing=[premise.Assertion("ACME_TRACE", "env", ("ACME_TRACE",), existing=True)],
                only_in={"ACME_TRACE": ["docs/ops.md"]},
            ),
            ["ACME_TRACE"],
        ),
        (
            premise.Premise(missing=[_symbol("Store.shift()")], only_in={"Store.shift()": ["CHANGELOG.md"]}),
            ["Store.shift()"],
        ),
        (
            premise.Premise(
                missing=[
                    premise.Assertion("--totals", "flag", ("--totals",)),
                    _symbol("Store.shift()"),
                    premise.Assertion("ACME_TRACE", "env", ("ACME_TRACE",), existing=True),
                ],
                only_in={"Store.shift()": ["CHANGELOG.md"], "ACME_TRACE": ["docs/ops.md"]},
            ),
            ["--totals", "Store.shift()", "ACME_TRACE"],
        ),
    ],
    ids=["nowhere", "only-in-docs", "c1b-symbol", "several"],
)
def test_the_hold_says_the_absence_in_words_the_grader_reads(found, names):
    """rd1-3-11: the suggested sentence names each missing name beside an absence cue."""
    hold = found.hold
    assert hold
    for name in names:
        assert names_absence(hold, [name]), name


def test_c1b_a_symbol_only_history_files_mention_is_one_no_code_defines():
    found = premise.Premise(missing=[_symbol("Store.shift()")], only_in={"Store.shift()": ["CHANGELOG.md"]})
    assert found.note.startswith(
        "`Store.shift()` appears only in CHANGELOG.md, and no code in this repository defines it, so what "
        "the "
        "request says already works is not there."
    )
    assert "Then either build `Store.shift()` itself so that it works" in found.note
    assert (
        'e.g. "There is no `Store.shift()` in this repository\'s code; only CHANGELOG.md mention it"'
        in found.hold
    )
    assert 'finish with "not done: `Store.shift()` does not exist"' in found.hold


# -- the resolution scope (rd1-2-9) and C1's guards --------------------------------------------------


def test_the_wider_code_suffixes_are_for_premise_resolution_only(tmp_path):
    """premise_unmet shares ``_code_file``: it keeps today's suffixes."""
    assert premise._code_file("infra/main.tf") is False
    assert premise._code_file("infra/main.tf", frozenset(premise._CODE_SUFFIXES | {".tf"})) is True
    root = tmp_path / "infra"
    root.mkdir()
    (root / "main.tf").write_text('variable "enable_trace" { default = false }\n')
    asserted = [premise.Assertion("enable_trace", "name", ("enable_trace",), existing=True)]
    assert premise.resolve(asserted, root, ["main.tf"]) == [(asserted[0], ["main.tf"])]
    assert premise.resolve(asserted, root, ["main.tf"], code_suffixes=frozenset({".tf"})) == []


def test_a_tools_own_switch_is_external():
    """C1: the fixed list of tool, runtime and framework switches (``_fixed_external``)."""
    assert premise._external("--legacy-peer-deps") and premise._external("PLAYWRIGHT_BROWSERS_PATH")
    assert not premise._external("--totals")


def test_c1c_an_env_switch_on_in_a_tools_clause_is_the_tools(tmp_path):
    root = tmp_path / "acme"
    root.mkdir()
    (root / "README.md").write_text("# acme\n")
    prompt = "pytest prints every fixture when ACME_FIXTURE_TRACE=1 is set: turn that on in CI."
    assert premise.check(prompt, root, ["README.md"]).missing == []
    assert premise.check(prompt.replace("pytest", "acme"), root, ["README.md"]).missing
