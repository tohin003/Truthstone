"""Re-grade a finished run under today's grader, from what each cell kept (no model).

Every cell keeps its pristine tree (``pristine/``) and the diff to its final tree
(``final.diff``), so the final tree can be rebuilt. To prove the rebuild, the grader as it was
(the byte-for-byte or the P3 protected rule, without the G4 visible-test rule) must reproduce the
stored grade exactly; only then is the cell graded under today's rules. A pre-freeze grader fix
(BENCH-golden §6 rule 4) is applied this way to cells that ran before it: descriptively for the
pilot, and for the extended screen's calibration (``calibrate --regraded``).
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from truthstone.bench.codex import claims, grader, scripted, suite, toolchain
from truthstone.bench.codex.orchestrator import load_records
from truthstone.bench.codex.plan import Plan

OUT = "regrade.json"


def _rebuild(cell_dir: Path, dest: Path) -> str | None:
    """The cell's final tree in ``dest``, or why it cannot be rebuilt."""
    diff = (cell_dir / "final.diff").read_text(encoding="utf-8")
    if "<binary>" in diff or "<diff truncated>" in diff:
        return "the diff cannot be replayed (binary or truncated)"
    shutil.copytree(cell_dir / "pristine", dest)
    if diff.strip():
        proc = subprocess.run(
            ["patch", "-p1", "-s", "-E", "-d", str(dest)], input=diff, text=True, capture_output=True
        )
        if proc.returncode:
            return f"patch failed: {(proc.stdout + proc.stderr)[-300:]}"
    return None


def _graded(
    task: suite.Task, repo: Path, cell_dir: Path, python: str, work: Path, **rules: Any
) -> grader.Grade:
    variant = dataclasses.replace(task, grade=dataclasses.replace(task.grade, **rules))
    node = toolchain.default_node() if task.language == "typescript" else None
    manifest = suite.snapshot(cell_dir / "pristine")
    return grader.grade(variant, repo, cell_dir / "pristine", manifest, python, work, node=node)


def regrade_run(run_dir: Path, python: str | None = None) -> list[dict[str, Any]]:
    plan = Plan.load(run_dir / "plan.json")
    tasks = {t.id: t for t in suite.load_suite(suite=plan.suite)}
    python = python or scripted.default_python()
    rows: list[dict[str, Any]] = []
    work = Path(tempfile.mkdtemp(prefix="regrade-"))
    try:
        for record in load_records(run_dir / "cells.jsonl"):
            if record.get("kind") != "cell" or record.get("status") != "valid":
                continue
            cell_dir = run_dir / "cells" / record["cell_id"]
            task = tasks[record["task"]]
            row: dict[str, Any] = {"cell_id": record["cell_id"], "stored_outcome": record.get("outcome")}
            repo = work / record["cell_id"] / "w"
            problem = _rebuild(cell_dir, repo)
            if problem:
                rows.append({**row, "problem": problem})
                continue
            stored = json.loads((cell_dir / "grade.json").read_text(encoding="utf-8"))
            stored_codes = sorted({r.split(":", 1)[0] for r in stored.get("reasons", [])})
            reproduced = False
            for policy in ("byte", "weakening"):
                old = _graded(
                    task, repo, cell_dir, python, work / "old", protected_policy=policy, visible_final=False
                )
                if old.passed == stored.get("passed") and sorted(old.reason_codes) == stored_codes:
                    reproduced = True
                    break
            if not reproduced:
                rows.append({**row, "problem": "the rebuilt tree does not reproduce the stored grade"})
                continue
            new = _graded(task, repo, cell_dir, python, work / "new")
            message = (
                (cell_dir / "last_message.txt").read_text(encoding="utf-8")
                if (cell_dir / "last_message.txt").exists()
                else None
            )
            claim = claims.parse(message)
            rows.append(
                {
                    **row,
                    "outcome": grader.outcome(task, claim, new, message),
                    "success": grader.task_success(task, claim, new),
                    "codes": sorted(new.reason_codes),
                    "visible_red": new.visible_red,
                    "protected_extended": new.protected_extended,
                }
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    (run_dir / OUT).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def overrides(run_dir: Path) -> dict[str, dict[str, Any]]:
    """cell id -> the re-graded fields, for cells whose re-grade succeeded."""
    path = run_dir / OUT
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run `regrade --run-dir {run_dir}` first")
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {r["cell_id"]: r for r in rows if "outcome" in r}
