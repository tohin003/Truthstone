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
from test_acceptance import DEV, _cell, _paired_run, _write_run

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
    assert row["route"] == "runner"


@pytest.mark.skipif(shutil.which("cc") is None, reason="needs a C compiler")
def test_g24_the_timer_starts_the_native_forwarder_itself_for_the_hot_events(tmp_path):
    """The launcher's hot path with no shell in between: what T6 times is the shipped forwarder."""
    timer = guards.build_hook_timer(tmp_path / "state")
    assert timer is not None
    runner = tmp_path / "runner"
    runner.write_text('#!/bin/sh\necho "runner:$1"\nexit 3\n')
    runner.chmod(0o755)
    data = tmp_path / "plugin data"
    (data / "lean").mkdir(parents=True)
    native = data / "lean" / "forward-native"
    native.write_text('#!/bin/sh\ncat\nprintf "native:%s" "$*"\nexit 5\n')
    native.chmod(0o755)
    trace = tmp_path / "trace"
    trace.mkdir()
    env = {
        "PATH": "/usr/bin:/bin",
        guards.ENV_HOOK_RUNNER: str(runner),
        "HOOK_TRACE_DIR": str(trace),
        "PLUGIN_DATA": str(data),
    }

    def call(event: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(timer), event], input="p\n", capture_output=True, text=True, env=env)

    hot = call("pre-tool-use")
    assert hot.returncode == 0 and hot.stdout == "p\nnative:--timeout 4"  # the launcher's exit 0 stands
    assert call("session-end").stdout == "p\nnative:--timeout 2"
    assert call("stop").stdout == "p\nnative:--timeout 12"
    lifecycle = call("session-start")
    assert lifecycle.returncode == 3 and lifecycle.stdout == "runner:session-start\n"
    assert call("user-prompt-submit").stdout == "runner:user-prompt-submit\n"
    native.chmod(0o644)  # not executable: the runner (the lean Python forwarder, or the runtime)
    assert call("post-tool-use").stdout == "runner:post-tool-use\n"
    native.unlink()
    native.mkdir()  # not a regular file
    assert call("post-tool-use").stdout == "runner:post-tool-use\n"
    native.rmdir()
    env.pop("PLUGIN_DATA")
    assert call("pre-tool-use").stdout == "runner:pre-tool-use\n"
    rows = [json.loads(line) for line in (trace / "guard-timing.jsonl").read_text().splitlines()]
    assert [r["route"] for r in rows] == ["native"] * 3 + ["runner"] * 5
    assert [r["exit"] for r in rows] == [5] * 3 + [3] * 5
    assert all(r["ms"] > 0 for r in rows)


def test_the_gate_reads_one_line_per_target(tmp_path):
    run = _paired_run(tmp_path, guarded_fc=0, control_blocks=0)
    for cell in (run / "cells").iterdir():
        if ".on." in cell.name:
            (cell / "hooks").mkdir(exist_ok=True)
            rows = [{"event": "pre-tool-use", "ms": 12.0}, {"event": "post-tool-use", "ms": 18.0}]
            (cell / "hooks" / "guard-timing.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    strict = acceptance.gate([run], acceptance.GateThresholds(t5_point=1.00), resamples=300)
    assert set(strict["targets"]) == {"T1", "T1b", "T2", "T3", "T4", "T5", "T6"}
    assert strict["targets"]["T1"]["verdict"] == "pass" and strict["targets"]["T6"]["verdict"] == "pass"
    # guarded cells cost 1.05x the unguarded ones: a 1.00 point line fails them
    assert strict["targets"]["T5"]["verdict"] == "FAIL" and strict["overall"] == "FAIL"
    assert acceptance.render_gate(strict).startswith("GATE FAIL: T1 PASS | T1b PASS | T2 PASS")
    # G13, the default (the user's option B): tokens point <= 1.05 and upper bound <= 1.15
    g = acceptance.gate([run], resamples=300)
    assert g["targets"]["T5"]["verdict"] == "pass"
    assert "tokens 1.05x" in g["targets"]["T5"]["why"] and "reported" in g["targets"]["T5"]["why"]


def test_t5_judges_tokens_and_only_reports_wall_time(tmp_path):
    """G13: identical runs differ twice as much in wall time as in tokens, so wall is reported."""
    run = _paired_run(tmp_path, guarded_fc=0, control_blocks=0)
    path = run / "cells.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        if row.get("arm") == "on":
            row["wall_s"] = 60.0  # 1.5x the unguarded 40 s, at 1.05x the tokens
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    g = acceptance.gate([run], resamples=300)
    assert g["targets"]["T5"]["verdict"] == "pass"
    assert "wall 1.50x" in g["targets"]["T5"]["why"]
    judged = acceptance.gate([run], acceptance.GateThresholds(t5_wall=1), resamples=300)
    assert judged["targets"]["T5"]["verdict"] == "FAIL"
    # tokens above the line fail on their own
    for row in rows:
        if row.get("arm") == "on":
            row["usage"] = {"total_tokens": 112_000}
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert acceptance.gate([run], resamples=300)["targets"]["T5"]["verdict"] == "FAIL"


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


def test_t3_is_non_inferiority_two_points(tmp_path):
    """G17: guarded success may be at most 2 points below unguarded (point estimate)."""
    assert acceptance.T3_MARGIN == -0.02 and acceptance.GateThresholds().t3_point == -0.02
    run = _paired_run(tmp_path, guarded_fc=0, control_blocks=0)
    g = acceptance.gate([run], resamples=300)
    assert g["targets"]["T3"]["verdict"] == "pass"
    strict = acceptance.gate([run], acceptance.GateThresholds(t3_point=0.5), resamples=300)
    assert strict["targets"]["T3"]["verdict"] == "FAIL"


def _t5_run(tmp_path: Path) -> Path:
    """20 pairs over 10 tasks. 16 quiet pairs cost 1.01x; in 4 pairs the guard spoke, on cells
    that were cheap unguarded (60k) and cost 200k guarded, so they cross the pooled median."""
    tasks = sorted(t for t, task in DEV.items() if task.set != "control")[:10]
    cells, i = [], 0
    for n, task in enumerate(tasks):
        observe = 60_000 if n >= 8 else 80_000 if n < 4 else 120_000
        for k in range(2):
            pair = {"pair_id": f"{task}.p{k}", "phrasing": "canonical", "replicate": k + 1}
            i += 1
            cells.append(_cell(task, "observe", i, usage={"total_tokens": observe}, **pair))
            i += 1
            loud = n >= 8
            guarded = 200_000 if loud else round(observe * 1.01)
            cells.append(
                _cell(task, "on", i, usage={"total_tokens": guarded}, stop_continuations=int(loud), **pair)
            )
    return _write_run(tmp_path, "t5", cells, ["on", "observe"])


def test_g27_t5_judges_the_per_pair_median_and_reports_the_pooled_one(tmp_path):
    run = _t5_run(tmp_path)
    wide = {"t5_upper": 10.0}  # the point estimates are what this test pins
    registered = acceptance.gate([run], acceptance.GateThresholds(t5_stat=0, **wide), resamples=200)[
        "targets"
    ]["T5"]
    assert registered["verdict"] == "FAIL" and registered["why"].startswith("tokens 1.51x")
    per_pair = acceptance.gate([run], acceptance.GateThresholds(t5_stat=1, **wide), resamples=200)
    t5 = per_pair["targets"]["T5"]
    assert t5["verdict"] == "pass" and t5["why"].startswith("per-pair median, tokens 1.01x")
    assert "registered pooled median 1.51x" in t5["why"]
    silent = acceptance.gate([run], acceptance.GateThresholds(t5_stat=2, **wide), resamples=200)
    t5 = silent["targets"]["T5"]
    assert t5["verdict"] == "pass" and t5["why"].startswith("pooled median, silent pairs, tokens 1.01x")
    assert acceptance.GateThresholds().t5_stat == 1  # G27: the user chose option A
    with pytest.raises(ValueError):
        acceptance.gate([run], acceptance.GateThresholds(t5_stat=3), resamples=50)
