"""regrade: a finished run re-graded under today's grader from what each cell kept (no model)."""

from __future__ import annotations

import json
import os

from truthstone.bench.codex import agents, cli, guards, orchestrator, regrade, report, suite
from truthstone.bench.codex.plan import Plan

PYTHON = os.path.abspath(os.environ.get("CODEX_BENCH_PYTHON", ".venv/bin/python"))


def _run(tmp_path, name="screen"):
    tasks = suite.load_suite(only=["ledger-tax-rounding", "ledger-known-failure"])
    plan = Plan(
        name=name,
        stage="dry-run",
        seed=11,
        tasks=[t.id for t in tasks],
        phrasings=["canonical"],
        replicates=[0],
        arms=["observe"],
        model="scripted",
        suite_digest=suite.suite_digest(tasks),
    )
    runner = orchestrator.Runner(
        plan,
        {t.id: t for t in tasks},
        guards.FakeGuard(),
        agents.ScriptedAgent(agents.dry_run_policy(seed=1, base_fc=0.5), PYTHON),
        tmp_path / name,
        tmp_path / f"{name}-work",
        PYTHON,
        real_codex=False,
        log=lambda _m: None,
    )
    runner.run()
    return tmp_path / name


def test_a_rebuilt_cell_reproduces_its_stored_grade_before_it_is_regraded(tmp_path, capsys):
    run = _run(tmp_path)
    rows = regrade.regrade_run(run, python=PYTHON)
    assert len(rows) == 2 and all("problem" not in r for r in rows), rows
    # the original suite's grader has not changed: the same outcomes
    assert all(r["outcome"] == r["stored_outcome"] for r in rows)
    assert json.loads((run / regrade.OUT).read_text()) == rows
    assert cli.main(["calibrate", "--regraded", "--run-dir", str(run)]) == 0
    cal = report.pooled_calibration([run], regraded=True)
    assert cal["runs"][0]["observe_cells"] == 2 and cal["runs"][0]["not_regraded"] == 0
    capsys.readouterr()


def test_calibrating_regraded_without_a_regrade_is_refused(tmp_path, capsys):
    run = _run(tmp_path, "fresh")
    assert cli.main(["calibrate", "--regraded", "--run-dir", str(run)]) == 2
    assert "regrade" in capsys.readouterr().out


def test_a_cell_whose_diff_cannot_be_replayed_is_reported_not_guessed(tmp_path):
    run = _run(tmp_path, "broken")
    cell = next(p for p in (run / "cells").iterdir() if p.is_dir())
    (cell / "final.diff").write_text("<diff truncated>\n")
    rows = regrade.regrade_run(run, python=PYTHON)
    assert any("cannot be replayed" in r.get("problem", "") for r in rows)
    assert cell.name not in regrade.overrides(run)
