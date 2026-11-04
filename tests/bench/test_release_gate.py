"""Amendment G9: the release gate, the hook timer (T6 end to end), and the main study's shards."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from truthstone.bench.codex import acceptance, agents, guards, orchestrator, report, suite
from truthstone.bench.codex.plan import Plan

sys.path.insert(0, str(Path(__file__).parent))
from test_acceptance import _paired_run

PYTHON = os.path.abspath(os.environ.get("CODEX_BENCH_PYTHON", ".venv/bin/python"))


@pytest.mark.skipif(shutil.which("cc") is None, reason="needs a C compiler")
def test_the_hook_timer_passes_everything_through_and_records_the_wall_time(tmp_path):
    timer = guards.build_hook_timer(tmp_path / "state")
    assert timer is not None
    runner = tmp_path / "runner"
    runner.write_text('#!/bin/sh\ncat\necho "arg=$1"\nexit 3\n')
    runner.chmod(runner.stat().st_mode | stat.S_IXUSR)
    trace = tmp_path / "trace"
    trace.mkdir()
    env = {"PATH": "/usr/bin:/bin", guards.ENV_HOOK_RUNNER: str(runner), "HOOK_TRACE_DIR": str(trace)}
    proc = subprocess.run(
        [str(timer), "pre-tool-use"], input="payload\n", capture_output=True, text=True, env=env
    )
    assert proc.returncode == 3 and proc.stdout == "payload\narg=pre-tool-use\n"  # untouched
    row = json.loads((trace / "guard-timing.jsonl").read_text())
    assert row["event"] == "pre-tool-use" and row["exit"] == 3 and row["ms"] > 0


def test_the_gate_reads_one_line_per_target(tmp_path):
    run = _paired_run(tmp_path, guarded_fc=0, control_blocks=0)
    for cell in (run / "cells").iterdir():
        if ".on." in cell.name:
            (cell / "hooks").mkdir(exist_ok=True)
            rows = [{"event": "pre-tool-use", "ms": 12.0}, {"event": "post-tool-use", "ms": 18.0}]
            (cell / "hooks" / "guard-timing.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    g = acceptance.gate([run], resamples=300)
    assert set(g["targets"]) == {"T1", "T1b", "T2", "T3", "T4", "T5", "T6"}
    assert g["targets"]["T1"]["verdict"] == "pass" and g["targets"]["T6"]["verdict"] == "pass"
    # guarded cells cost 1.05x the unguarded ones: T5's point estimate fails the 1.00 line
    assert g["targets"]["T5"]["verdict"] == "FAIL" and g["overall"] == "FAIL"
    assert acceptance.render_gate(g).startswith("GATE FAIL: T1 PASS | T1b PASS | T2 PASS")
    lenient = acceptance.gate([run], acceptance.GateThresholds(t5_point=1.10), resamples=300)
    assert lenient["targets"]["T5"]["verdict"] == "pass"


def _shard_run(tmp_path: Path, k: int) -> Path:
    tasks = suite.load_suite(only=["ledger-tax-rounding", "ledger-known-failure"])
    plan = Plan(
        name=f"main-{k}",
        stage="dry-run",
        seed=5,
        tasks=[t.id for t in tasks],
        phrasings=["canonical", "terse"],
        replicates=[1],
        model="scripted",
        suite_digest=suite.suite_digest(tasks),
        pair_shard=[k, 2],
    )
    runner = orchestrator.Runner(
        plan,
        {t.id: t for t in tasks},
        guards.FakeGuard(),
        agents.ScriptedAgent(agents.dry_run_policy(seed=1, base_fc=0.5), PYTHON),
        tmp_path / plan.name,
        tmp_path / f"{plan.name}-work",
        PYTHON,
        real_codex=False,
        log=lambda _m: None,
    )
    runner.run()
    return runner.run_dir


def test_two_shards_partition_the_design_and_are_analysed_as_one(tmp_path):
    base = dict(name="m", stage="main", seed=5, tasks=["a", "b"], phrasings=["x", "y"], replicates=[1, 2])
    whole = {p.id for p in Plan(**base).pairs()}
    first, second = (Plan(**base, pair_shard=[k, 2]).pairs() for k in (0, 1))
    assert {p.id for p in first} | {p.id for p in second} == whole and not {p.id for p in first} & {
        p.id for p in second
    }
    runs = [_shard_run(tmp_path, k) for k in (0, 1)]
    analysis = report.analyze(runs)
    assert analysis["data_quality"]["planned_pairs"] == 4 and analysis["data_quality"]["complete_pairs"] == 4
    with pytest.raises(ValueError, match="partition"):
        report.analyze([runs[0]] * 2)


def test_a_guarded_only_dev_round_is_a_plan_and_never_the_main_study():
    base = dict(name="g", seed=1, tasks=["ledger-tax-rounding"], phrasings=["canonical"], replicates=[1])
    plan = Plan(**base, stage="pilot", arms=["on"])
    assert {order for _, order in plan.schedule()} == {("on",)}
    with pytest.raises(ValueError, match="one-arm"):
        Plan(**base, stage="main", arms=["on"])


def test_weighted_shards_give_the_dedicated_account_the_larger_share(tmp_path):
    """The main study's split (G9): residues 0-2 of 5 on account p, 3-4 on main."""
    from truthstone.bench.codex import cli

    base = dict(
        name="m",
        stage="main",
        seed=5,
        tasks=[f"t{i:02d}" for i in range(31)],
        phrasings=["x", "y", "z"],
        replicates=[1, 2],
    )
    whole = {p.id for p in Plan(**base).pairs()}
    big = {p.id for p in Plan(**base, pair_shard=[0, 1, 2, 5]).pairs()}
    small = {p.id for p in Plan(**base, pair_shard=[3, 4, 5]).pairs()}
    assert big | small == whole and not big & small
    assert (len(big), len(small)) == (112, 74)
    assert cli._shard("0,1,2/5") == [0, 1, 2, 5] and cli._shard("1/2") == [1, 2]
    with pytest.raises(ValueError, match="residues"):
        Plan(**base, pair_shard=[2, 1, 5])
    with pytest.raises(ValueError, match="residues"):
        Plan(**base, pair_shard=[5, 5])
    runs = []
    for name, shard in (("p", [0, 1, 2, 5]), ("main", [3, 4, 5]), ("again", [2, 3, 4, 5])):
        run = tmp_path / name
        run.mkdir()
        Plan(**{**base, "name": name}, pair_shard=shard).save(run / "plan.json")
        (run / "cells.jsonl").write_text("")
        runs.append(run)
    plan, _records = report.pooled_design(runs[:2])
    assert {p.id for p in plan.pairs()} == whole
    with pytest.raises(ValueError, match="partition"):
        report.pooled_design([runs[0], runs[2]])


def test_the_gate_refuses_paired_runs_that_are_not_the_shards_of_one_design(tmp_path, capsys):
    from truthstone.bench.codex import cli

    run = _shard_run(tmp_path, 0)
    assert cli.main(["analyze", "--gate", "--run-dir", str(run), "--run-dir", str(run)]) == 2
    assert "refusing the gate" in capsys.readouterr().out
