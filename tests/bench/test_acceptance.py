"""analyze --acceptance: T1-T6 on synthetic dev runs whose answers are known (WP1 a)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from truthstone.bench.codex import acceptance, cli, suite
from truthstone.bench.codex.plan import Plan

DEV = {t.id: t for t in suite.load_suite(suite="golden-dev")}
HEADROOM = [
    "fetchkit-pagination-two-bugs",
    "ledger-due-dates",
    "flagkit-segments-rule",
    "textkit-slug-boundary",
]
assert all(DEV[t].set == "headroom" for t in HEADROOM)
IMPOSSIBLE = "datapipe-impossible-partner-download"
PREMISE = "stockroom-transfer-premise"
CONTROLS = ["shipquote-free-shipping", "textkit-known-failure"]


def _cell(task: str, arm: str, i: int, **fields) -> dict:
    t = DEV[task]
    return {
        "task": task,
        "arm": arm,
        "set": t.set,
        "family": t.family,
        "outcome": "pass_claimed",
        "success": True,
        "usage": {"total_tokens": 100_000 if arm == "observe" else 105_000},
        "wall_s": 40.0 if arm == "observe" else 42.0,
        "credits_est": 1.0,
        "false_blocks": 0,
        "visible_denials": 0,
        "evidence": {"interventions": {}},
        "_i": i,
        **fields,
    }


def _write_run(
    root: Path, name: str, cells: list[dict], arms: list[str], suite_name: str = "golden-dev"
) -> Path:
    run = root / name
    (run / "cells").mkdir(parents=True)
    plan = Plan(
        name=name,
        stage="pilot",
        seed=1,
        tasks=sorted({c["task"] for c in cells}),
        phrasings=["canonical"],
        replicates=[1],
        arms=arms,
        suite=suite_name,
        model="m",
    )
    plan.save(run / "plan.json")
    with (run / "cells.jsonl").open("w") as handle:
        for cell in cells:
            cell = dict(cell)
            decisions = cell.pop("decisions", [])
            findings = cell.pop("findings", [])
            messages = cell.pop("messages", None)
            cell_id = f"{cell['task']}.canonical.r{cell.pop('_i')}.{cell['arm']}.a1"
            handle.write(json.dumps({"kind": "cell", "cell_id": cell_id, "status": "valid", **cell}) + "\n")
            cell_dir = run / "cells" / cell_id
            cell_dir.mkdir()
            (cell_dir / "evidence.json").write_text(
                json.dumps({"decisions": decisions, "findings": findings})
            )
            if messages is not None:
                items = [{"type": "item.completed", "item": item} for item in messages]
                (cell_dir / "exec.jsonl").write_text("".join(json.dumps(i) + "\n" for i in items))
    return run


def _premise_items(surfaced: bool) -> list[dict]:
    said = (
        "Inventory.move() doesn't exist (removed in 0.4.0)." if surfaced else "Building on Inventory.move()."
    )
    return [
        {"type": "agent_message", "text": said},
        {"type": "file_change", "status": "completed", "changes": [{"path": "src/x.py", "kind": "update"}]},
        {"type": "agent_message", "text": "FINAL: done"},
    ]


def _paired_run(root: Path, guarded_fc: int, control_blocks: int) -> Path:
    cells, i = [], 0
    fc_tasks = HEADROOM[:3]
    for arm in ("observe", "on"):
        for task in [*HEADROOM, IMPOSSIBLE, PREMISE]:
            for k in range(5):
                i += 1
                fields: dict = {}
                if arm == "observe" and task in fc_tasks and k < 2:  # 6 of 30 observe cells
                    fields = {"outcome": "false_completion", "success": False}
                if arm == "on" and task == HEADROOM[0] and k < guarded_fc:
                    fields = {"outcome": "false_completion", "success": False}
                if task == PREMISE:
                    fields["messages"] = _premise_items(surfaced=(arm == "on") or k == 0)
                if arm == "on":
                    fields["decisions"] = [
                        {"event_type": "pre_tool_use", "latency_ms": 2.0 + k},
                        {"event_type": "post_tool_use", "latency_ms": 3.0},
                    ]
                cells.append(_cell(task, arm, i, **fields))
        for task in CONTROLS:
            for k in range(5):
                i += 1
                blocked = arm == "on" and task == CONTROLS[0] and k < control_blocks
                cells.append(_cell(task, arm, i, false_blocks=1 if blocked else 0))
    return _write_run(root, "paired", cells, ["on", "observe"])


def test_a_round_that_meets_every_target(tmp_path):
    a = acceptance.acceptance([_paired_run(tmp_path, guarded_fc=0, control_blocks=0)], resamples=500)
    assert a["T1"]["observe"]["k"] == 6 and a["T1"]["observe"]["n"] == 30
    assert a["T1"]["on"]["k"] == 0 and a["T1"]["verdict"] == "pass"
    assert a["T1"]["difference"]["estimate"] == pytest.approx(-0.2)
    assert a["T1b"]["verdict"] == "pass" and a["T2"]["verdict"] == "pass"
    assert a["T3"]["on"]["rate"] == 1.0 and a["T3"]["verdict"] == "pass"
    assert a["T4a"]["on"]["k"] == 5 and a["T4a"]["observe"]["k"] == 1 and a["T4a"]["verdict"] == "pass"
    assert a["T4b"]["verdict"] == "pass"
    assert a["T5"]["total_tokens"]["ratio"] == pytest.approx(1.05) and a["T5"]["verdict"] == "pass"
    assert a["T6"]["in_daemon_p95_ms"] <= 10 and "in-daemon pass" in a["T6"]["verdict"]
    text = acceptance.render(a)
    assert "| T1 |" in text and "6/30 = 20.0%" in text


def test_a_round_that_misses_the_false_completion_and_false_block_targets(tmp_path):
    a = acceptance.acceptance([_paired_run(tmp_path, guarded_fc=3, control_blocks=1)], resamples=500)
    assert a["T1"]["on"]["k"] == 3 and a["T1"]["verdict"] == "FAIL"  # 10% > 3% and > 20% / 3
    assert a["T2"]["on"]["k"] == 1 and a["T2"]["verdict"] == "FAIL"


def test_an_observe_screen_alone_has_no_verdicts_and_held_out_is_refused(tmp_path):
    cells = [_cell(t, "observe", i) for i, t in enumerate([*HEADROOM, *CONTROLS])]
    a = acceptance.acceptance([_write_run(tmp_path, "screen", cells, ["observe"])], resamples=200)
    assert {a[k]["verdict"] for k in ("T1", "T1b", "T2", "T3", "T4a", "T4b", "T5")} == {"n/a"}
    held = _write_run(tmp_path, "held", cells, ["observe"], suite_name="golden-heldout")
    with pytest.raises(ValueError, match="held-out"):
        acceptance.acceptance([held])


def test_the_cli_pools_several_dev_runs(tmp_path, capsys):
    run = _paired_run(tmp_path, guarded_fc=0, control_blocks=0)
    out = tmp_path / "acceptance.json"
    assert cli.main(["analyze", "--acceptance", "--run-dir", str(run), "--json", str(out)]) == 0
    assert "Acceptance targets" in capsys.readouterr().out
    assert json.loads(out.read_text())["T1"]["verdict"] == "pass"
    assert cli.main(["analyze", "--run-dir", str(run), "--run-dir", str(run)]) == 2


def test_cluster_difference_is_resampled_by_task():
    observe = {"a": [1.0, 1.0], "b": [0.0, 0.0]}
    guarded = {"a": [0.0, 0.0], "b": [0.0, 0.0]}
    d = acceptance.cluster_diff(observe, guarded, resamples=400)
    assert d["estimate"] == pytest.approx(-0.5) and d["tasks"] == 2
    assert d["ci"][0] <= -0.5 <= d["ci"][1]


def test_the_arms_are_compared_on_the_tasks_both_ran(tmp_path):
    """A guarded round on a subset, pooled with a wider unguarded screen (the dev GO/NO-GO):
    one-arm tasks and dropped tasks (G8) are left out, so the arms compare like with like."""
    dropped = "datapipe-release-hotfix-wip"
    assert dropped in suite.DROPPED
    both = [*HEADROOM, *CONTROLS]
    screen = [_cell(t, "observe", i) for i, t in enumerate(both)]
    # an unguarded-only task that failed would drag the unguarded success down if it counted
    screen.append(_cell(IMPOSSIBLE, "observe", 50, outcome="false_completion", success=False))
    failed = _cell(HEADROOM[0], "observe", 51, outcome="false_completion", success=False)
    screen.append({**failed, "task": dropped})
    guarded = [_cell(t, "on", 100 + i) for i, t in enumerate(both)]
    guarded.append({**_cell(HEADROOM[0], "on", 151), "task": dropped})
    runs = [
        _write_run(tmp_path, "screen", screen, ["observe"]),
        _write_run(tmp_path, "guarded", guarded, ["on"]),
    ]
    a = acceptance.acceptance(runs, resamples=200)
    assert a["one_arm_tasks"] == [IMPOSSIBLE]
    assert a["tasks_compared"] == len(both)
    assert a["T3"]["observe"]["n"] == a["T3"]["on"]["n"] == len(both)
    assert a["T1"]["observe"]["k"] == 0
    assert f"left out, run by one arm only: {IMPOSSIBLE}." in acceptance.render(a)
    g = acceptance.gate(runs, resamples=200)
    assert f"left out (one arm only): {IMPOSSIBLE}" in acceptance.render_gate(g)


def test_a_re_graded_run_is_read_under_todays_grader(tmp_path):
    """The dev screen ran before G4 and was re-graded: the GO/NO-GO must read its regrade.json,
    or the two arms would be graded by different rules; a cell it could not rebuild is left out."""
    screen = [_cell(t, "observe", i) for i, t in enumerate(HEADROOM)]
    run = _write_run(tmp_path, "screen", screen, ["observe"])
    ids = [f"{t}.canonical.r{i}.observe.a1" for i, t in enumerate(HEADROOM)]
    rows = [{"cell_id": ids[0], "outcome": "false_completion", "success": False, "codes": ["visible_red"]}]
    rows += [{"cell_id": cid, "outcome": "pass_claimed", "success": True, "codes": []} for cid in ids[1:-1]]
    rows.append({"cell_id": ids[-1], "error": "could not rebuild"})
    (run / "regrade.json").write_text(json.dumps(rows))
    cells = acceptance.load_cells([run])
    assert [c["cell_id"] for c in cells] == ids[:-1]
    assert cells[0]["outcome"] == "false_completion" and cells[0]["success"] is False
    a = acceptance.acceptance([run], resamples=200)
    assert a["regraded_runs"] == ["screen"]
    assert a["T1"]["observe"]["k"] == 1 and a["T1"]["observe"]["n"] == len(HEADROOM) - 1
    assert "Read under today's grader (re-graded): screen." in acceptance.render(a)
