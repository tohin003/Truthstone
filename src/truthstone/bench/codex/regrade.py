"""Re-grade a finished run under today's grader, from what each cell kept (no model).

Every cell keeps its pristine tree (``pristine/``) and the diff to its final tree
(``final.diff``), so the final tree can be rebuilt. To prove the rebuild, the grader as it was
(the byte-for-byte, the P3, the G36 or the G44 protected rule, with or without the G4 visible-test
rule) must reproduce the stored grade exactly; only then is the cell graded under today's rules. A
pre-freeze grader fix (BENCH-golden §6 rule 4) is applied this way to cells that ran before it:
descriptively for the pilot, and for the extended screen's calibration (``calibrate --regraded``).

Amendment G36: a re-grade is made under one protected-file policy (``--policy``; by default the
policy the run's suite registered) and written to that policy's own file, ``regrade-<policy>.json``,
which is never overwritten. Before G36 a re-grade was written to ``regrade.json`` under the run's
registered policy; that legacy file is still read for the ``weakening`` policy (golden-heldout2's
is its G29 file), never for ``byte`` and never for ``weakening-g36`` or ``weakening-g44`` (G44).
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from truthstone.bench.codex import claims, grader, scripted, suite, toolchain
from truthstone.bench.codex.orchestrator import load_records
from truthstone.bench.codex.plan import Plan

# Before G36 a run had one re-grade file, graded under the run's registered policy. Since G36 each
# policy has its own (``out_name``), never overwritten.
LEGACY_OUT = "regrade.json"
# The pre-G36 policies whose re-grades may be the legacy file. Not ``byte``: the legacy file of a
# golden run is a ``weakening`` file (comp-3-33).
LEGACY_POLICIES = frozenset({"weakening"})


def out_name(policy: str) -> str:
    """The file a re-grade under ``policy`` writes: ``regrade-<policy>.json``."""
    if policy not in suite.PROTECTED_POLICIES:
        known = ", ".join(suite.PROTECTED_POLICIES)
        raise ValueError(f"unknown protected-file policy {policy!r}; known: {known}")
    return f"regrade-{policy}.json"


def policy_of(plan: Plan) -> str:
    """The protected-file policy the plan's suite registered (what its cells were graded under);
    a suite no longer registered is read as the original suite's ``byte``."""
    spec = suite.SUITES.get(plan.suite or suite.DEFAULT_SUITE)
    return spec.protected_policy if spec is not None else "byte"


def registered_policy(run_dir: Path) -> str:
    """The protected-file policy the run's suite registered (``policy_of`` its plan)."""
    return policy_of(Plan.load(run_dir / "plan.json"))


def override_path(run_dir: Path, policy: str) -> Path | None:
    """The re-grade file to read under ``policy``: ``regrade-<policy>.json`` when it exists; else,
    for a pre-G36 policy other than ``byte``, the legacy ``regrade.json``; else None."""
    path = run_dir / out_name(policy)
    if path.exists():
        return path
    legacy = run_dir / LEGACY_OUT
    if policy in LEGACY_POLICIES and legacy.exists():
        return legacy
    return None


def _rebuild(cell_dir: Path, dest: Path) -> str | None:
    """The cell's final tree in ``dest``, or why it cannot be rebuilt: from the archived
    changes (cells recorded since the archive existed), else from ``final.diff``."""
    from truthstone.bench.codex.orchestrator import FINAL_TREE, FINAL_TREE_META

    meta_path = cell_dir / FINAL_TREE_META
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not meta.get("archived"):
            return f"the final tree's changes were too large to archive ({meta.get('bytes')} bytes)"
        shutil.copytree(cell_dir / "pristine", dest, symlinks=True)
        for rel in meta.get("deleted", []):
            target = dest / rel
            if target.is_symlink() or target.is_file():
                target.unlink()
        with tarfile.open(cell_dir / FINAL_TREE, "r:gz") as tar:
            tar.extractall(dest, filter="tar")
        return None
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


def regrade_run(run_dir: Path, python: str | None = None, policy: str | None = None) -> list[dict[str, Any]]:
    """Re-grade every valid cell of a run under ``policy`` (default: the run's registered policy)
    and write ``regrade-<policy>.json``; a run that already has that file is refused."""
    plan = Plan.load(run_dir / "plan.json")
    policy = policy or policy_of(plan)
    out = run_dir / out_name(policy)
    if out.exists():
        raise FileExistsError(f"{out} exists: a re-grade is never overwritten")
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
            for visible_final in (False, True):  # cells graded before G4, and since
                for was in suite.PROTECTED_POLICIES:
                    old = _graded(
                        task,
                        repo,
                        cell_dir,
                        python,
                        work / "old",
                        protected_policy=was,
                        visible_final=visible_final,
                    )
                    if old.passed == stored.get("passed") and sorted(old.reason_codes) == stored_codes:
                        reproduced = True
                        break
                if reproduced:
                    break
            if not reproduced:
                rows.append({**row, "problem": "the rebuilt tree does not reproduce the stored grade"})
                continue
            new = _graded(task, repo, cell_dir, python, work / "new", protected_policy=policy)
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
    with out.open("x", encoding="utf-8") as handle:  # never over a file written meanwhile
        handle.write(json.dumps(rows, indent=1))
    return rows


def overrides(run_dir: Path, policy: str | None = None) -> dict[str, dict[str, Any]]:
    """cell id -> the re-graded fields under ``policy`` (default: the run's registered policy),
    for cells whose re-grade succeeded."""
    policy = policy or registered_policy(run_dir)
    path = override_path(run_dir, policy)
    if path is None:
        command = f"regrade --run-dir {run_dir} --policy {policy}"
        raise FileNotFoundError(f"{run_dir / out_name(policy)} is missing: run `{command}` first")
    return read_overrides(path)


def read_overrides(path: Path) -> dict[str, dict[str, Any]]:
    """cell id -> the re-graded fields of one re-grade file, for cells whose re-grade succeeded."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {r["cell_id"]: r for r in rows if "outcome" in r}
