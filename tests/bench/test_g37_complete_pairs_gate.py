"""Amendment G37: the gate's rates read complete pairs; its harm counts read every guarded cell.

`analyze --gate` used to read every valid cell of every attempt. When a pair's unguarded cell
voided and the pair was re-run, the guarded cell of the voided attempt was counted too: on
golden-heldout3 T1 read 11/140 instead of 11/138. And a guarded harm event in a task only one arm
ran validly was dropped by `compared()`. Under G37, when every cell record of the runs read
carries `pair_id` and `attempt` (`pair_excluded` records set aside first), a pair is one (task,
phrasing, replicate), complete when both arms are valid at their latest attempt: the rates (T1,
T3, T4a, T5) read complete pairs, the harm counts (T1b, T2, T4b, T6) every valid guarded cell.
What is left out, dropped or voided is printed beside the gate. Synthetic runs on golden-dev
task ids (no task text).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.bench.test_acceptance import CONTROLS, DEV, HEADROOM, IMPOSSIBLE
from truthstone.bench.codex import acceptance, orchestrator
from truthstone.bench.codex.plan import Plan

OPPORTUNITY = [*HEADROOM, IMPOSSIBLE]


def _cell(task: str, arm: str, attempt: int = 1, replicate: int = 1, **fields) -> dict:
    t = DEV[task]
    return {
        "kind": "cell",
        "cell_id": f"{task}.canonical.r{replicate}.{arm}.a{attempt}",
        "pair_id": f"{task}|canonical|r{replicate}",
        "task": task,
        "set": t.set,
        "family": t.family,
        "recipe": t.recipe,
        "phrasing": "canonical",
        "replicate": replicate,
        "arm": arm,
        "attempt": attempt,
        "status": "valid",
        "void_reason": None,
        "outcome": "pass_claimed",
        "success": True,
        "usage": {"total_tokens": 100_000 if arm == "observe" else 105_000},
        "wall_s": 40.0 if arm == "observe" else 42.0,
        "credits_est": 1.0,
        "false_blocks": 0,
        "visible_denials": 0,
        "evidence": {"interventions": {}},
        **fields,
    }


def _void(task: str, arm: str, attempt: int, reason: str, replicate: int = 1) -> dict:
    return _cell(task, arm, attempt, replicate, status="void", void_reason=reason, outcome=None, success=None)


FC = {"outcome": "false_completion", "success": False}


def _write(root: Path, name: str, records: list[dict], arms: tuple[str, ...] = ("on", "observe")) -> Path:
    run = root / name
    (run / "cells").mkdir(parents=True)
    tasks = sorted({r["task"] for r in records if r.get("kind") == "cell"})
    Plan(
        name=name,
        stage="pilot",
        seed=1,
        tasks=tasks,
        phrasings=["canonical"],
        replicates=[1, 2],
        arms=list(arms),
        suite="golden-dev",
        model="m",
    ).save(run / "plan.json")
    with (run / "cells.jsonl").open("w") as handle:
        for record in records:
            record = dict(record)
            evidence = record.pop("_evidence", {})
            timings = record.pop("_timings", None)
            handle.write(json.dumps(record) + "\n")
            if record.get("kind") != "cell":
                continue
            cell = run / "cells" / record["cell_id"]
            cell.mkdir()
            (cell / "evidence.json").write_text(json.dumps(evidence))
            if timings:
                (cell / "hooks").mkdir()
                rows = [{"event": "pre-tool-use", "ms": ms} for ms in timings]
                (cell / "hooks" / "guard-timing.jsonl").write_text(
                    "".join(json.dumps(r) + "\n" for r in rows)
                )
    return run


def _without_attempts(run: Path) -> None:
    """The same run as a run recorded without G37's fields reads (today's behaviour)."""
    path = run / "cells.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    path.write_text("".join(json.dumps({k: v for k, v in r.items() if k != "attempt"}) + "\n" for r in rows))


def _heldout3_shape(root: Path) -> Path:
    """Ten opportunity pairs and two control pairs, one guarded FC in a complete pair, four
    unguarded FCs; one pair whose unguarded cell voided (attestation) and was re-run: its first
    guarded cell, a false completion, is valid; one pair excluded after three void attempts."""
    records: list[dict] = []
    for n, task in enumerate(OPPORTUNITY):
        for replicate in (1, 2):
            if (task, replicate) == (HEADROOM[0], 1):
                records += [
                    _cell(task, "on", 1, replicate, **FC),
                    _void(task, "observe", 1, "attestation", replicate),
                    _cell(task, "on", 2, replicate),
                    _cell(task, "observe", 2, replicate),
                ]
                continue
            if (task, replicate) == (HEADROOM[1], 2):
                for attempt in (1, 2, 3):
                    records += [
                        _void(task, "on", attempt, "harness_error", replicate),
                        _void(task, "observe", attempt, "harness_error", replicate),
                    ]
                records.append(
                    {"kind": "pair_excluded", "pair_id": f"{task}|canonical|r2", "attempts": 3, "ts": 1.0}
                )
                continue
            guarded = FC if (task, replicate) == (HEADROOM[2], 1) else {}
            unguarded = FC if replicate == 1 and n in (1, 2, 3, 4) else {}
            records += [
                _cell(task, "on", 1, replicate, **guarded),
                _cell(task, "observe", 1, replicate, **unguarded),
            ]
    for task in CONTROLS:
        records += [_cell(task, "on"), _cell(task, "observe")]
    return _write(root, "heldout3-shape", records)


def test_heldout3s_shape_rates_read_the_rerun_and_the_orphan_is_printed(tmp_path):
    run = _heldout3_shape(tmp_path)
    run_set = acceptance.load_run_set([run])
    assert run_set.g37  # the pair_excluded record carries no attempt, and does not switch G37 off
    orphan = f"{HEADROOM[0]}.canonical.r1.on.a1"
    paired = {c["cell_id"]: c["_paired"] for c in run_set.cells}
    assert paired[orphan] is False and paired[f"{HEADROOM[0]}.canonical.r1.on.a2"] is True
    g = acceptance.gate([run], resamples=200)
    # 9 complete opportunity pairs (one excluded); the orphan's false completion left out of T1
    assert g["targets"]["T1"]["why"].startswith("guarded 1/9 = 11.1% vs unguarded 44.4%")
    lists = g["g37"]
    assert lists["pairs"] == 11
    assert [(c["cell_id"], c["arm"], c["outcome"]) for c in lists["left_out"]] == [
        (orphan, "on", "false_completion")
    ]
    assert lists["regrade_dropped"] == [] and lists["compared_dropped"] == []
    assert lists["excluded_pairs"] == [
        {
            "run": "heldout3-shape",
            "pair_id": f"{HEADROOM[1]}|canonical|r2",
            "void_reasons": {"observe": ["harness_error"] * 3, "on": ["harness_error"] * 3},
        }
    ]
    voids = lists["build_caused_voids"]
    assert voids["observe"] == {
        "attestation": [f"{HEADROOM[0]}.canonical.r1.observe.a1"],
        "harness_error": [f"{HEADROOM[1]}.canonical.r2.observe.a{k}" for k in (1, 2, 3)],
    }
    assert voids["on"] == {"harness_error": [f"{HEADROOM[1]}.canonical.r2.on.a{k}" for k in (1, 2, 3)]}
    text = acceptance.render_gate(g)
    assert "G37: the rates read 11 complete pair(s)" in text
    assert f"heldout3-shape/{orphan}: on, false_completion" in text
    assert "build-caused voids, observe: attestation 1" in text
    assert f"heldout3-shape/{HEADROOM[1]}|canonical|r2 (observe: harness_error" in text
    # the same records without `attempt`: the reading before G37 counts the orphan (n + 1)
    _without_attempts(run)
    before = acceptance.gate([run], resamples=200)
    assert before["targets"]["T1"]["why"].startswith("guarded 2/10 = 20.0%")
    assert "g37" not in before and "G37" not in acceptance.render_gate(before)


def test_harm_events_in_voided_attempts_and_one_arm_tasks_are_counted(tmp_path):
    """Each harm count reads every valid guarded cell: a blocked control, a control premise flag,
    an impossible task's false completion and hook timings, each (i) in an attempt whose twin
    voided and (ii) in a task only the guarded arm ran validly."""
    flagged = {"findings": [{"subject": "premise_unmet: Store.shift", "failure_mode": "premise"}]}
    blocked = {"false_blocks": 1}
    records = [
        # (i) voided attempts, re-run cleanly
        _cell(CONTROLS[0], "on", 1, **blocked, _evidence=flagged, _timings=[25.0, 26.0]),
        _void(CONTROLS[0], "observe", 1, "daemon"),
        _cell(CONTROLS[0], "on", 2),
        _cell(CONTROLS[0], "observe", 2),
        _cell(IMPOSSIBLE, "on", 1, **FC),
        _void(IMPOSSIBLE, "observe", 1, "usage_limit"),
        _cell(IMPOSSIBLE, "on", 2),
        _cell(IMPOSSIBLE, "observe", 2),
        # (ii) tasks only the guarded arm ran validly
        _cell(CONTROLS[1], "on", **blocked, _evidence=flagged, _timings=[27.0]),
        _void(CONTROLS[1], "observe", 1, "preflight"),
        _cell(HEADROOM[0], "on", 1, replicate=2, **FC),
        _void(HEADROOM[0], "observe", 1, "settings_drift", replicate=2),
        # complete pairs
        _cell(HEADROOM[0], "on", _timings=[5.0]),
        _cell(HEADROOM[0], "observe"),
        _cell(HEADROOM[1], "on"),
        _cell(HEADROOM[1], "observe", **FC),
    ]
    run = _write(tmp_path, "harm", records)
    a = acceptance.acceptance([run], resamples=200, allow_heldout=True)
    assert a["T2"]["on"]["k"] == 2 and a["T2"]["on"]["n"] == 3  # both blocked guarded controls
    assert a["T4b"]["on"]["k"] == 2
    assert a["T1b"]["on"]["k"] == 1 and a["T1b"]["on"]["n"] == 2  # the voided attempt's FC, and the re-run
    # the rates read the complete pairs only: the one-arm HEADROOM[0] r2 FC is left out of T1
    assert (a["T1"]["on"]["k"], a["T1"]["on"]["n"]) == (0, 3) and (
        a["T1"]["observe"]["k"],
        a["T1"]["observe"]["n"],
    ) == (1, 3)
    g = acceptance.gate([run], resamples=200)
    assert g["targets"]["T2"]["verdict"] == "FAIL" and g["targets"]["T2"]["why"].startswith(
        "2 control cell(s) with a false block (G43); reported, never judged: 0 control cell(s) with correct"
    )
    assert g["targets"]["T1b"]["verdict"] == "FAIL"
    assert g["targets"]["T4"]["verdict"] == "n/a"  # no guarded false-premise cells
    assert g["targets"]["T6"]["why"] == "p95 26.9 ms over 4 hooks"
    assert {c["cell_id"] for c in g["g37"]["left_out"]} == {
        f"{CONTROLS[0]}.canonical.r1.on.a1",
        f"{IMPOSSIBLE}.canonical.r1.on.a1",
        f"{CONTROLS[1]}.canonical.r1.on.a1",
        f"{HEADROOM[0]}.canonical.r2.on.a1",
    }
    # compared() drops the one-arm control (its task ran in the guarded arm only)
    assert [c["cell_id"] for c in g["g37"]["compared_dropped"]] == [f"{CONTROLS[1]}.canonical.r1.on.a1"]
    assert g["one_arm_tasks"] == [CONTROLS[1]]
    voids = g["g37"]["build_caused_voids"]
    assert sorted(voids["observe"]) == ["daemon", "preflight", "settings_drift"] and voids["on"] == {}
    families = g["g37"]["families"]
    assert families["control"]["control"] == {
        "blocked": [2, 3],
        "correct_blocks_only": [0, 3],
        "premise_flags": [2, 3],
    }
    assert families["impossible"]["guarded_every_cell"] == [1, 2]
    assert families["impossible"]["paired"] == {"observe": [0, 1], "on": [0, 1]}
    # without G37 the one-arm control and its block are dropped by compared()
    _without_attempts(run)
    before = acceptance.gate([run], resamples=200)
    assert before["targets"]["T2"]["why"].startswith("1 control cell(s) with a false block (G43);")


def test_on_a_single_paired_run_the_complete_pairs_are_the_orchestrators(tmp_path):
    """rd3-3-3: on one paired run, G37's complete pairs are `orchestrator.complete_pairs`."""
    t1, t2, t3, t4, t5 = HEADROOM[0], HEADROOM[1], HEADROOM[2], HEADROOM[3], IMPOSSIBLE
    records = [
        _cell(t1, "on"),
        _cell(t1, "observe"),  # complete at once
        _cell(t2, "observe"),
        _void(t2, "on", 1, "attestation"),
        _cell(t2, "observe", 2),
        _cell(t2, "on", 2),
        _void(t3, "on", 1, "usage_limit"),
        _cell(t3, "on", 2),
        _cell(t3, "observe", 2),  # the second arm never started
        _cell(t4, "on"),
        _void(t4, "observe", 1, "harness_error"),  # stopped: incomplete
        *[_void(t5, arm, k, "harness_error") for k in (1, 2, 3) for arm in ("on", "observe")],
        {"kind": "pair_excluded", "pair_id": f"{t5}|canonical|r1", "attempts": 3, "ts": 1.0},
    ]
    run = _write(tmp_path, "single", records)
    cells = acceptance.load_cells([run])
    paired = {c["cell_id"] for c in cells if c["_paired"]}
    expected = {r["cell_id"] for pair in orchestrator.complete_pairs(records) for r in pair}
    assert paired == expected and len(paired) == 6
    assert {c["cell_id"] for c in cells if not c["_paired"]} == {
        f"{t2}.canonical.r1.observe.a1",
        f"{t4}.canonical.r1.on.a1",
    }


def test_with_pair_ids_but_no_attempts_the_reading_is_as_before(tmp_path):
    records = [
        {k: v for k, v in _cell(task, arm).items() if k != "attempt"}
        for task in OPPORTUNITY
        for arm in ("on", "observe")
    ]
    run = _write(tmp_path, "no-attempt", records)
    run_set = acceptance.load_run_set([run])
    assert not run_set.g37 and all(c["_paired"] for c in run_set.cells)
    assert "g37" not in acceptance.acceptance([run], resamples=100)


def test_a_pair_whose_latest_cell_the_regrade_dropped_leaves_the_paired_reading(tmp_path):
    records = [_cell(task, arm) for task in OPPORTUNITY for arm in ("on", "observe")]
    run = _write(tmp_path, "regraded", records)
    dropped = f"{HEADROOM[0]}.canonical.r1.on.a1"
    rows = [
        {"cell_id": r["cell_id"], "outcome": r["outcome"], "success": r["success"], "codes": []}
        for r in records
        if r["cell_id"] != dropped
    ]
    (run / "regrade-weakening.json").write_text(json.dumps(rows))  # golden-dev's registered policy
    g = acceptance.gate([run], resamples=200)
    assert g["regrade_files"] == {"regraded": "regrade-weakening.json"}
    assert g["targets"]["T1"]["why"].startswith("guarded 0/4")
    assert [c["cell_id"] for c in g["g37"]["regrade_dropped"]] == [dropped]
    assert [c["cell_id"] for c in g["g37"]["left_out"]] == [f"{HEADROOM[0]}.canonical.r1.observe.a1"]
    text = acceptance.render_gate(g)
    assert "dropped by the re-grade: 1 cell(s)" in text and f"regraded/{dropped}: on" in text


def test_a_screen_and_a_guarded_round_pair_across_runs_as_before(tmp_path):
    """An unguarded screen and a guarded round of the same (task, phrasing, replicate) set: G37
    pairs them across the runs, and the rates read what the reading before G37 reads."""
    screen = _write(
        tmp_path,
        "screen",
        [_cell(t, "observe", **(FC if t == HEADROOM[0] else {})) for t in OPPORTUNITY],
        ("observe",),
    )
    rounds = _write(tmp_path, "round", [_cell(t, "on") for t in OPPORTUNITY], ("on",))
    g37 = acceptance.acceptance([screen, rounds], resamples=200)
    assert "g37" in g37 and g37["g37"]["pairs"] == len(OPPORTUNITY)
    for run in (screen, rounds):
        _without_attempts(run)
    before = acceptance.acceptance([screen, rounds], resamples=200)
    for key in ("T1", "T1b", "T3"):
        for arm in ("observe", "on"):
            assert g37[key][arm] == before[key][arm], (key, arm)


def test_a_tie_on_the_latest_attempt_goes_to_the_later_run_directory(tmp_path):
    first = _write(tmp_path, "first", [_cell(HEADROOM[0], "on", **FC), _cell(HEADROOM[0], "observe")])
    later = _write(tmp_path, "later", [_cell(HEADROOM[0], "on"), _cell(HEADROOM[0], "observe")])
    cells = acceptance.load_cells([first, later])
    assert {(Path(c["_run"]).name, c["_paired"]) for c in cells} == {("first", False), ("later", True)}
    g = acceptance.gate([first, later], resamples=100)
    assert g["targets"]["T1"]["why"].startswith("guarded 0/1")
    assert {c["run"] for c in g["g37"]["left_out"]} == {"first"}
    swapped = acceptance.gate([later, first], resamples=100)
    assert swapped["targets"]["T1"]["why"].startswith("guarded 1/1")


@pytest.mark.parametrize("reason", acceptance.BUILD_CAUSED_VOIDS)
def test_every_build_caused_void_is_printed_per_arm(tmp_path, reason):
    records = [
        _cell(HEADROOM[0], "observe"),
        _void(HEADROOM[0], "on", 1, reason),
        _cell(HEADROOM[0], "on", 2),
        _cell(HEADROOM[0], "observe", 2),
    ]
    g = acceptance.gate([_write(tmp_path, "v", records)], resamples=100)
    assert g["g37"]["build_caused_voids"]["on"] == {reason: [f"{HEADROOM[0]}.canonical.r1.on.a1"]}
    assert f"build-caused voids, on: {reason} 1" in acceptance.render_gate(g)
