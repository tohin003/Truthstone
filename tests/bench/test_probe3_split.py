"""golden-probe3 (amendment G47): a third out-of-sample probe split, built blind before golden-heldout4.

Built the way a held-out split is built (blind to the product and to every other split's tasks),
reviewed task by task before registration, graded under the G44 policy (`weakening-g44`) and run
on the guarded arm only. Never frozen, never spent, never held out: any plan may use it, whole or
in part. Its task list stays out of the pre-registration and out of this file (the lead stays
blind to it until the probe has run); its digest is registered in docs/BENCH-golden.md §4.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter

import pytest

from truthstone.bench.codex import acceptance, cli, premise, scripted, suite, toolchain
from truthstone.bench.codex.plan import Plan

NAME = "golden-probe3"
PYTHON = os.path.abspath(os.environ.get("CODEX_BENCH_PYTHON", ".venv/bin/python"))
DOC = suite.REPO_ROOT / "docs" / "BENCH-golden.md"
OTHERS = (
    "golden-dev",
    "golden-heldout",
    "golden-heldout2",
    "golden-heldout3",
    "golden-rehearsal",
    "golden-candidates",
    "golden-dev-keeptests",
    "golden-probe1",
    "golden-probe2",
)


@pytest.fixture(scope="module")
def tasks() -> list[suite.Task]:
    return suite.load_suite(suite=NAME)


def test_composition_after_review(tasks):
    """21 built (8 impossible, 4 false-premise, 3 test-tampering, 2 unverified-completion, 4 control);
    none was removed at review."""
    assert Counter(t.family for t in tasks) == {
        "impossible": 8,
        "false-premise": 4,
        "test-tampering": 3,
        "unverified-completion": 2,
        "control": 4,
    }
    assert Counter(t.set for t in tasks) == {"headroom": 9, "impossible": 8, "control": 4}
    assert Counter(t.language for t in tasks) == {"python": 10, "typescript": 11}
    controls = [t.recipe for t in tasks if t.set == "control"]
    assert len(set(controls)) == len(controls) == 4  # each control recipe once
    for task in tasks:
        assert len(set(task.prompts.values())) == 3, task.id
        opening = "No-harm control" if task.set == "control" else "Designed to present"
        assert task.opportunity.rationale.startswith(opening), task.id
        assert "built blind" in task.opportunity.prediction.lower(), task.id
        assert bool(task.opportunity.premise_tokens) == (task.family == "false-premise"), task.id
        assert task.grade.impossible == (task.set == "impossible"), task.id


def test_a_probe_split_never_frozen_spent_or_held_out():
    spec = suite.suite_spec(NAME)
    assert spec.tasks_dir == "probe3" and spec.protected_policy == "weakening-g44"
    assert spec.visible_final
    assert NAME not in suite.FROZEN and NAME not in suite.SPENT
    assert NAME not in acceptance.HELD_OUT
    assert NAME in acceptance.PREMISE_SUITES


@pytest.mark.parametrize(("arms", "stage"), [("on", "pilot"), ("both", "main")])
def test_plan_takes_the_whole_split(tasks, arms, stage, tmp_path):
    """The probe runs the guarded arm alone (a pilot-stage plan); a paired main plan is allowed too."""
    out = tmp_path / f"{stage}.json"
    argv = ["plan", "--suite", NAME, "--arms", arms, "--stage", stage, "--replicates", "1"]
    argv += ["--name", f"probe3-{stage}", "--out", str(out)]
    assert cli.main(argv) == 0
    plan = Plan.load(out)
    assert plan.suite == NAME and plan.replicates == [1]
    assert plan.arms == (["on"] if arms == "on" else ["on", "observe"])
    assert plan.tasks == [t.id for t in tasks] and len(plan.pairs()) == 3 * len(tasks)
    assert plan.suite_digest == suite.suite_digest(tasks)


def test_plan_takes_part_of_the_split(tasks, tmp_path):
    out = tmp_path / "part.json"
    task = tasks[0].id
    argv = ["plan", "--suite", NAME, "--task", task, "--arms", "both", "--stage", "pilot"]
    argv += ["--phrasing", "terse", "--replicates", "1", "--name", "probe3-part", "--out", str(out)]
    assert cli.main(argv) == 0 and Plan.load(out).tasks == [task]


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_new_and_disjoint_from_every_other_golden_suite(tasks):
    others = [t for name in OTHERS for t in suite.load_suite(suite=name)]
    assert not {t.id for t in tasks} & {t.id for t in others}
    assert {t.suite_root for t in tasks} == {suite.GOLDEN_ROOT}
    prompts = lambda ts: {t.prompt(p) for t in ts for p in suite.PHRASINGS}  # noqa: E731

    def material(group):  # hidden tests and scripted solutions, by content (empty files aside)
        files = [f for t in group for d in ("hidden", "solutions") for f in (t.root / d).rglob("*")]
        return {_sha(f) for f in files if f.is_file() and "__pycache__" not in f.parts and f.stat().st_size}

    assert not prompts(tasks) & prompts(others)
    assert not material(tasks) & material(others)


def test_the_document_registers_the_digest_and_names_no_task(tasks):
    text = DOC.read_text(encoding="utf-8")
    match = re.search(rf"### {re.escape(NAME)}:.*?Digest `([0-9a-f]{{64}})`", text, re.DOTALL)
    assert match and match.group(1) == suite.suite_digest(tasks)
    for task in tasks:
        assert task.id not in text, task.id


def test_t4a_reads_the_premise_tokens_and_the_honest_answer_surfaces_them(tasks, tmp_path):
    premised = [t for t in tasks if t.family == "false-premise"]
    cells = [{"task": t.id, "family": t.family, "_suite": NAME} for t in premised]
    assert acceptance._premise_tokens(cells) == {t.id: t.opportunity.premise_tokens for t in premised}
    for task in premised:  # the honest answer names a token next to an absence cue
        made = suite.materialize(task, tmp_path / task.id / "w", tmp_path / task.id / "p", python=PYTHON)
        message = scripted.run_solution(task, "honest", made.repo, PYTHON)
        assert premise.names_absence(message, task.opportunity.premise_tokens), task.id


def _node_available() -> bool:
    try:
        toolchain.node_version(toolchain.default_node())
    except toolchain.ToolchainError:
        return False
    return True


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_a_representative_grader_holds(tasks, language, tmp_path):
    """The whole split is proved by `validate --suite golden-probe3`; one task per language here."""
    if language == "typescript" and not _node_available():
        pytest.skip("Node is needed for TypeScript tasks")
    task = next(t for t in tasks if t.language == language and t.set == "impossible")
    result = scripted.validate_task(task, PYTHON, tmp_path)
    assert result.ok, [(v.variant, v.outcome, v.problem) for v in result.variants]
