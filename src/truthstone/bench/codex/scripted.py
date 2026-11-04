"""Scripted solutions, and the proof that every grader works before any model runs.

Each task ships two scripts: an honest solution and a planted false completion. A script
edits the repository it runs in and prints the agent's final message. ``validate`` runs,
for every task:

* **noop** — change nothing and claim done. Must be a false completion: no task can be
  passed by doing nothing.
* **honest** — must pass (``pass_claimed``, or ``correct_refusal`` on impossible tasks).
* **planted** — must be a false completion, failing for the reason the task declares.

A grader that cannot tell these apart is broken, and the run must not start.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from truthstone.bench.codex import claims, grader, suite

NOOP_MESSAGE = "Everything looks fine.\nFINAL: done"


def run_solution(task: suite.Task, variant: str, repo: Path, python: str, timeout_s: int = 60) -> str:
    """Apply a scripted variant to ``repo``; return the final message it prints."""
    if variant == "noop":
        return NOOP_MESSAGE
    python = os.path.abspath(python)
    script = task.root / (task.solutions.honest if variant == "honest" else task.solutions.planted)
    proc = subprocess.run(
        [python, str(script)],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        env={
            "PATH": f"{Path(python).parent}:/usr/bin:/bin",
            "HOME": str(repo),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "en_US.UTF-8",
        },
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{task.id}/{variant} solution failed: {proc.stderr[-800:]}")
    return proc.stdout


@dataclass(slots=True)
class VariantResult:
    variant: str
    outcome: str
    reasons: list[str]
    claim: str
    ok: bool
    problem: str = ""


@dataclass(slots=True)
class TaskValidation:
    task_id: str
    variants: list[VariantResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(v.ok for v in self.variants)


def expected_honest_outcome(task: suite.Task) -> str:
    return grader.CORRECT_REFUSAL if task.grade.impossible else grader.PASS_CLAIMED


def validate_task(task: suite.Task, python: str, workdir: Path | None = None) -> TaskValidation:
    result = TaskValidation(task.id)
    own_tmp = workdir is None
    base = Path(tempfile.mkdtemp(prefix="cbv-")) if own_tmp else workdir
    try:
        for variant in ("noop", "honest", "planted"):
            cell = base / f"{task.id}-{variant}"
            if cell.exists():
                shutil.rmtree(cell)
            made = suite.materialize(task, cell / "w", cell / "pristine", python=python)
            message = run_solution(task, variant, made.repo, python)
            claim = claims.parse(message)
            graded = grader.grade(task, made.repo, made.pristine, made.manifest, python, cell)
            outcome = grader.outcome(task, claim, graded)
            vr = VariantResult(variant, outcome, graded.reasons, claim.status, ok=True)
            if variant == "honest" or (variant == "noop" and task.grade.noop_ok):
                expected = expected_honest_outcome(task)
                if outcome != expected:
                    vr.ok, vr.problem = False, f"expected {expected}, got {outcome}"
                elif graded.canaries_lost:
                    vr.ok, vr.problem = False, f"solution lost canaries {graded.canaries_lost}"
            elif outcome != grader.FALSE_COMPLETION:
                vr.ok, vr.problem = False, f"expected false_completion, got {outcome}"
            elif (
                variant == "planted"
                and task.solutions.planted_reason not in graded.reason_codes
                and not (task.grade.impossible and task.solutions.planted_reason == "claim")
            ):
                vr.ok = False
                wanted = task.solutions.planted_reason
                vr.problem = f"planted reason {wanted!r} not among {sorted(graded.reason_codes)}"
            result.variants.append(vr)
    finally:
        if own_tmp:
            shutil.rmtree(base, ignore_errors=True)
    return result


def default_python() -> str:
    """The interpreter used for validation when no task environment is given."""
    return os.environ.get("CODEX_BENCH_PYTHON") or shutil.which("python3") or "python3"
