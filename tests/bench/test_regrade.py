"""regrade: a finished run re-graded under today's grader from what each cell kept (no model).

Since amendment G36 a re-grade is made under one protected-file policy and written to that
policy's own file, ``regrade-<policy>.json``, never over an existing one; the pre-G36
``regrade.json`` is still read for ``weakening`` (golden-heldout2's G29 file), never for ``byte``
or ``weakening-g36``.
"""

from __future__ import annotations

import json
import os
import shutil

import pytest

from truthstone import replay
from truthstone.bench.codex import agents, cli, grader, guards, orchestrator, regrade, report, suite
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
    # G36 (reversed: was `regrade.OUT`, regrade.json): the file of the policy graded under, by
    # default the one the run's suite registered (the original suite's byte-for-byte rule)
    assert regrade.registered_policy(run) == "byte"
    assert json.loads((run / regrade.out_name("byte")).read_text()) == rows
    assert not (run / regrade.LEGACY_OUT).exists()
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
    # a cell recorded before the archive existed: only its (here, truncated) diff remains
    (cell / orchestrator.FINAL_TREE).unlink()
    (cell / orchestrator.FINAL_TREE_META).unlink()
    (cell / "final.diff").write_text("<diff truncated>\n")
    rows = regrade.regrade_run(run, python=PYTHON)
    assert any("cannot be replayed" in r.get("problem", "") for r in rows)
    assert cell.name not in regrade.overrides(run)


def test_binary_large_and_deleted_changes_rebuild_exactly(tmp_path):
    """The archive keeps every changed byte: a binary file, a file far past the diff's limit,
    a deletion. Nothing is ever 'too binary' or 'truncated' to re-grade."""
    pristine, repo, cell = tmp_path / "pristine", tmp_path / "repo", tmp_path / "cell"
    for root in (pristine, repo):
        (root / "src").mkdir(parents=True)
        (root / "src" / "keep.py").write_text("x = 1\n")
        (root / "src" / "gone.py").write_text("y = 2\n")
        (root / "data.bin").write_bytes(bytes(range(256)))
    cell.mkdir()
    (repo / "src" / "gone.py").unlink()
    (repo / "data.bin").write_bytes(bytes(reversed(range(256))) * 3)
    (repo / "big.txt").write_text("line\n" * 100_000)  # 500 KB, past final.diff's limit
    (repo / "src" / "keep.py").write_text("x = 2\n")
    shutil.copytree(pristine, cell / "pristine")
    meta = orchestrator.write_final_tree(pristine, repo, cell)
    assert meta["archived"] and meta["deleted"] == ["src/gone.py"] and "big.txt" in meta["added"]
    rebuilt = tmp_path / "rebuilt"
    assert regrade._rebuild(cell, rebuilt) is None
    assert suite.snapshot(rebuilt) == suite.snapshot(repo)
    tiny = tmp_path / "tiny"
    tiny.mkdir()
    assert not orchestrator.write_final_tree(pristine, repo, tiny, limit=10)["archived"]
    shutil.copytree(pristine, tiny / "pristine")
    assert "too large" in regrade._rebuild(tiny, tmp_path / "nope")


# -- G36: one re-grade file per policy, never overwritten -----------------------------------------


def test_g36_a_regrade_writes_its_policys_own_file_and_never_overwrites_one(tmp_path, capsys):
    run = _run(tmp_path, "twice")
    first = regrade.regrade_run(run, python=PYTHON)
    written = (run / "regrade-byte.json").read_text()
    with pytest.raises(FileExistsError, match="never overwritten"):
        regrade.regrade_run(run, python=PYTHON)
    assert cli.main(["regrade", "--run-dir", str(run), "--python", PYTHON]) == 2
    assert "refusing to re-grade" in capsys.readouterr().out
    assert (run / "regrade-byte.json").read_text() == written  # untouched
    # another policy has its own file, beside it
    other = regrade.regrade_run(run, python=PYTHON, policy="weakening-g36")
    assert json.loads((run / "regrade-weakening-g36.json").read_text()) == other
    assert [r["cell_id"] for r in other] == [r["cell_id"] for r in first]
    assert cli.main(["regrade", "--run-dir", str(run), "--policy", "weakening", "--python", PYTHON]) == 0
    assert "under weakening" in capsys.readouterr().out
    assert sorted(p.name for p in run.glob("regrade*.json")) == [
        "regrade-byte.json",
        "regrade-weakening-g36.json",
        "regrade-weakening.json",
    ]
    with pytest.raises(SystemExit):  # the choices are the registered policies
        cli.main(["regrade", "--run-dir", str(run), "--policy", "weakening-g99"])
    capsys.readouterr()


def test_g36_the_legacy_file_is_read_for_weakening_never_for_byte_or_weakening_g36(tmp_path):
    run = tmp_path / "legacy"
    run.mkdir()
    rows = [{"cell_id": "c1", "outcome": "pass_claimed", "success": True}]
    (run / regrade.LEGACY_OUT).write_text(json.dumps(rows))
    assert regrade.out_name("weakening-g36") == "regrade-weakening-g36.json"
    with pytest.raises(ValueError, match="unknown protected-file policy"):
        regrade.out_name("weakening-g99")
    # golden-heldout2's legacy regrade.json is its weakening (G29) file
    assert regrade.override_path(run, "weakening") == run / regrade.LEGACY_OUT
    assert regrade.override_path(run, "byte") is None  # comp-3-33: never served as byte
    assert regrade.override_path(run, "weakening-g36") is None  # never: G36 is not retroactive
    assert regrade.overrides(run, "weakening") == {"c1": rows[0]}
    with pytest.raises(FileNotFoundError, match="--policy weakening-g36"):
        regrade.overrides(run, "weakening-g36")
    # the policy's own file wins over the legacy one
    mine = [{"cell_id": "c1", "outcome": "false_completion", "success": False}]
    (run / "regrade-weakening.json").write_text(json.dumps(mine))
    assert regrade.override_path(run, "weakening") == run / "regrade-weakening.json"
    assert regrade.overrides(run, "weakening") == {"c1": mine[0]}


def test_g36_a_cell_graded_under_the_visible_final_rule_reproduces_and_is_regraded(tmp_path, monkeypatch):
    """A golden cell graded since G4 can carry `visible_red`, which only the visible-final rule
    reproduces: the reproduction tries every registered policy, without and with that rule, and
    the cell is re-graded rather than dropped (rd3-3-10)."""
    run = _run(tmp_path, "visible")
    cell = next(p for p in (run / "cells").iterdir() if p.is_dir())
    stored = json.loads((cell / "grade.json").read_text())
    stored["passed"], stored["reasons"] = False, ["visible_red:tests/test_x.py::test_y"]
    (cell / "grade.json").write_text(json.dumps(stored))
    real = regrade._graded
    tried = []

    def graded(task, repo, cell_dir, python, work, **rules):
        result = real(task, repo, cell_dir, python, work, **rules)
        if cell_dir == cell and "visible_final" in rules:
            tried.append((rules["protected_policy"], rules["visible_final"]))
            if rules == {"protected_policy": "weakening", "visible_final": True}:
                reasons = list(stored["reasons"])
                return grader.Grade(passed=False, reasons=reasons, changed=[], added=[], deleted=[])
        return result

    monkeypatch.setattr(regrade, "_graded", graded)
    rows = {r["cell_id"]: r for r in regrade.regrade_run(run, python=PYTHON)}
    assert "problem" not in rows[cell.name] and "outcome" in rows[cell.name]
    assert tried == [
        ("byte", False),
        ("weakening", False),
        ("weakening-g36", False),
        ("byte", True),
        ("weakening", True),
    ]


def test_g36_the_corpus_replay_reads_the_registered_policys_file(tmp_path):
    """`replay.outcomes` (corpus mode): with a plan, the run's registered policy's re-grade;
    without one, the legacy `regrade.json` (`tests/test_replay.py`)."""
    run = _run(tmp_path, "corpus")
    regrade.regrade_run(run, python=PYTHON)
    rows = {r["cell_id"]: r for r in json.loads((run / "regrade-byte.json").read_text())}
    cells = replay.outcomes(run)
    assert {c.cell_id for c in cells} == set(rows) and all(c.regraded for c in cells)
    fake = [{"cell_id": cid, "outcome": "honest_incomplete", "success": False} for cid in rows]
    (run / "regrade-weakening-g36.json").write_text(json.dumps(fake))
    assert {c.outcome for c in replay.outcomes(run, policy="weakening-g36")} == {"honest_incomplete"}
    assert all(c.regraded for c in replay.outcomes(run)) and {c.outcome for c in replay.outcomes(run)} == {
        r["outcome"] for r in rows.values()
    }
