"""The cell loop, end to end, with a scripted agent and a fake guard (no model, no Codex)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from truthstone.bench.codex import agents, guards, orchestrator, report, suite
from truthstone.bench.codex.plan import Plan

PYTHON = os.path.abspath(os.environ.get("CODEX_BENCH_PYTHON", ".venv/bin/python"))
TASKS = ["ledger-tax-rounding", "ledger-impossible-cap"]


def _plan(**kw) -> Plan:
    tasks = suite.load_suite(only=TASKS)
    base = dict(
        name="t",
        stage="dry-run",
        seed=3,
        tasks=TASKS,
        phrasings=["canonical"],
        replicates=[1, 2],
        model="scripted",
        effort="medium",
        suite_digest=suite.suite_digest(tasks),
    )
    base.update(kw)
    return Plan(**base)


def _runner(tmp_path: Path, plan: Plan | None = None, agent=None, guard=None, **kw) -> orchestrator.Runner:
    plan = plan or _plan()
    tasks = {t.id: t for t in suite.load_suite(only=plan.tasks)}
    agent = agent or agents.ScriptedAgent(
        agents.dry_run_policy(seed=1, base_fc=1.0, catch=1.0), PYTHON, model="scripted", effort="medium"
    )
    return orchestrator.Runner(
        plan,
        tasks,
        guard or guards.FakeGuard(),
        agent,
        tmp_path / "run",
        tmp_path / "work",
        PYTHON,
        real_codex=False,
        log=lambda _m: None,
        **kw,
    )


def _cells(run_dir: Path) -> list[dict]:
    return [r for r in orchestrator.load_records(run_dir / "cells.jsonl") if r.get("kind") == "cell"]


def test_dry_run_end_to_end(tmp_path):
    runner = _runner(tmp_path)
    summary = runner.run()
    assert summary["pairs_run"] == 4
    cells = _cells(tmp_path / "run")
    assert len(cells) == 8 and all(c["status"] == "valid" for c in cells)
    # The simulated guard catches every planted false completion: observe fails, on does not.
    by_arm = {(c["task"], c["replicate"], c["arm"]): c["outcome"] for c in cells}
    assert by_arm[("ledger-tax-rounding", 1, "observe")] == "false_completion"
    assert by_arm[("ledger-tax-rounding", 1, "on")] == "pass_claimed"
    assert by_arm[("ledger-impossible-cap", 1, "on")] == "correct_refusal"
    analysis = report.analyze(tmp_path / "run")
    primary = analysis["primary"]
    assert primary["n_pairs"] == 4
    assert primary["discordant"] == {"b_observe_only": 4, "c_on_only": 0}
    assert analysis["harm"]["overhead"]["stop_continuations"]["total"] == 4
    assert "Primary" in report.render_markdown(analysis)
    on_cell = next(c for c in cells if c["arm"] == "on")
    assert on_cell["stop_assessments"] and on_cell["stop_assessments"][0]["graded"]
    # Every guarded hold here caught a planted false completion: none is a false block.
    held = [s for c in cells if c["arm"] == "on" for s in c["stop_assessments"]]
    assert held and not any(s["false_block"] for s in held)
    assert {s["snapshot_outcome"] for s in held} == {"false_completion"}
    # Artifacts a reviewer needs are on disk for every cell.
    cell_dir = tmp_path / "run" / "cells" / on_cell["cell_id"]
    for name in (
        "exec.jsonl",
        "rollout.jsonl",
        "transcript.json",
        "evidence.json",
        "grade.json",
        "final.diff",
    ):
        assert (cell_dir / name).exists(), name
    assert not any((tmp_path / "work").iterdir()) or all(
        p.name.startswith("k") for p in (tmp_path / "work").iterdir()
    )


def test_checkpoint_and_resume_never_repeat_a_pair(tmp_path):
    first = _runner(tmp_path).run(max_pairs=1)
    assert first["pairs_run"] == 1
    assert len(_cells(tmp_path / "run")) == 2
    second = _runner(tmp_path).run()
    assert second["pairs_run"] == 3
    cells = _cells(tmp_path / "run")
    assert len(cells) == 8
    assert len({(c["pair_id"], c["arm"]) for c in cells}) == 8
    assert _runner(tmp_path).run() == {"pairs_run": 0, "stopped": "nothing to do"}


def test_a_run_directory_is_bound_to_its_plan(tmp_path):
    _runner(tmp_path).run(max_pairs=1)
    with pytest.raises(orchestrator.Halt, match="belongs to plan"):
        _runner(tmp_path, plan=_plan(seed=99)).run()


class FlakyAgent:
    """Hits the usage limit on the first cell, then behaves."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    def run(self, prompt, repo, env, cell_dir, tmpdir, extra, **kw):
        self.calls += 1
        if self.calls == 1:
            (cell_dir / "exec.jsonl").write_text(
                json.dumps(
                    {
                        "type": "turn.failed",
                        "error": {"message": "You've hit your usage limit. Try again at 9 PM."},
                    }
                )
                + "\n"
            )
            (cell_dir / "exec.stderr").write_text("")
            return agents.AgentRun(
                1,
                0.1,
                False,
                cell_dir / "exec.jsonl",
                cell_dir / "exec.stderr",
                cell_dir / "last_message.txt",
                ["flaky"],
            )
        return self.inner.run(prompt, repo, env, cell_dir, tmpdir, extra, **kw)


def test_usage_limit_voids_a_pair_without_spending_its_attempts(tmp_path):
    inner = agents.ScriptedAgent(agents.dry_run_policy(seed=1), PYTHON, model="scripted", effort="medium")
    runner = _runner(tmp_path, plan=_plan(max_attempts=1), agent=FlakyAgent(inner))
    summary = runner.run()
    assert summary["pairs_run"] == 4  # the voided pair was re-run despite max_attempts=1
    cells = _cells(tmp_path / "run")
    voids = [c for c in cells if c["status"] != "valid"]
    assert len(voids) == 1 and voids[0]["void_reason"] == "usage_limit"
    assert len(cells) == 9  # the other arm was never run into the exhausted window
    complete = orchestrator.complete_pairs(orchestrator.load_records(tmp_path / "run" / "cells.jsonl"))
    assert len(complete) == 4 and all(on["attempt"] == obs["attempt"] for on, obs in complete)
    assert voids[0]["cell_id"] not in {c["cell_id"] for pair in complete for c in pair}


def test_budget_stop_is_outcome_blind_and_spends_nothing(tmp_path):
    reading = {
        "primary": {"used_percent": 10, "resets_at": 0},
        "secondary": {"used_percent": 85, "resets_at": 0},
    }
    # Up front, the allowance check refuses a study that cannot fit under the stop line...
    with pytest.raises(orchestrator.Halt, match="refusing to start"):
        _runner(tmp_path, limits_reader=lambda: reading).run()
    # ...and when told to run what fits, the per-pair rule stops before spending anything.
    summary = _runner(tmp_path, limits_reader=lambda: reading, allow_partial=True).run()
    assert summary["pairs_run"] == 0 and "weekly" in summary["stopped"]
    assert _cells(tmp_path / "run") == []


class SilentGuard(guards.FakeGuard):
    """Hooks that never ran: no evidence at all."""

    def collect(self, ctx, repo, trace_dir):
        return guards.HookEvidence()


def test_missing_hook_evidence_voids_cells_and_then_halts(tmp_path):
    quiet = agents.ScriptedAgent(
        agents.dry_run_policy(seed=1, base_fc=0.0, false_block=0.0), PYTHON, model="scripted", effort="medium"
    )
    runner = _runner(tmp_path, guard=SilentGuard(), agent=quiet)
    with pytest.raises(orchestrator.Halt, match="three consecutive"):
        runner.run()
    cells = _cells(tmp_path / "run")
    assert cells and all(c["status"] == "void" and c["void_reason"] == "attestation" for c in cells)
    assert all("no hook evidence" in " ".join(c["problems"]) for c in cells)


def test_a_visible_intervention_nobody_decided_halts(tmp_path):
    # The scripted guarded arm shows a Stop continuation; the guard recorded no decision.
    runner = _runner(tmp_path, guard=SilentGuard())
    with pytest.raises(orchestrator.Halt, match="model-visible stop hold"):
        runner.run()


class LeakyAgent:
    """An observe-only cell whose transcript shows a hook denial reaching the model."""

    def __init__(self, inner):
        self.inner = inner

    def run(self, prompt, repo, env, cell_dir, tmpdir, extra, **kw):
        result = self.inner.run(prompt, repo, env, cell_dir, tmpdir, extra, **kw)
        if kw.get("observe_only"):
            with (cell_dir / "rollout.jsonl").open("a") as handle:
                handle.write(
                    json.dumps(
                        {
                            "type": "response_item",
                            "payload": {
                                "type": "function_call_output",
                                "output": "Command blocked by PreToolUse hook: "
                                "Truthstone: needs developer sign-off",
                            },
                        }
                    )
                    + "\n"
                )
        return result


def test_an_observe_only_leak_halts_the_run(tmp_path):
    inner = agents.ScriptedAgent(agents.dry_run_policy(seed=1), PYTHON, model="scripted", effort="medium")
    runner = _runner(tmp_path, agent=LeakyAgent(inner))
    with pytest.raises(orchestrator.Halt, match="observe-only arm leaked"):
        runner.run()
    halted = [c for c in _cells(tmp_path / "run") if c["status"] == "halt"]
    assert len(halted) == 1 and halted[0]["arm"] == "observe"


def test_settings_drift_voids_the_cell(tmp_path):
    agent = agents.ScriptedAgent(
        agents.dry_run_policy(seed=1), PYTHON, model="some-other-model", effort="medium"
    )
    runner = _runner(tmp_path, plan=_plan(max_attempts=1), agent=agent)
    with pytest.raises(orchestrator.Halt, match="three consecutive"):
        runner.run()
    cells = _cells(tmp_path / "run")
    assert cells and all(c["void_reason"] == "settings_drift" for c in cells)
    assert "some-other-model" in cells[0]["problems"][0]
    excluded = [
        r
        for r in orchestrator.load_records(tmp_path / "run" / "cells.jsonl")
        if r.get("kind") == "pair_excluded"
    ]
    assert excluded  # max_attempts=1: each drifting pair is excluded, never scored


def test_a_pilot_is_analysed_blind(tmp_path):
    _runner(tmp_path, plan=_plan(stage="pilot")).run()
    analysis = report.analyze(tmp_path / "run")
    assert analysis["blind"] is True
    assert "primary" not in analysis and "secondary" not in analysis
    rendered = report.render_markdown(analysis)
    assert "withheld" in rendered and "observe-only" not in rendered
    assert analysis["pooled_base_rates"]["opportunity"]["cells"] == 8


def test_a_study_the_allowance_cannot_finish_never_starts(tmp_path):
    reading = {
        "primary": {"used_percent": 1, "resets_at": 0},
        "secondary": {"used_percent": 79.5, "resets_at": 0},
    }
    runner = _runner(tmp_path, limits_reader=lambda: reading)
    with pytest.raises(orchestrator.Halt, match="refusing to start"):
        runner.run()
    assert _cells(tmp_path / "run") == []
    assert json.loads((tmp_path / "run" / "allowance.json").read_text())["ok"] is False
    partial = _runner(tmp_path, limits_reader=lambda: reading, allow_partial=True)
    assert partial.run(max_pairs=1)["pairs_run"] == 1  # what fits, under the weekly stop line
