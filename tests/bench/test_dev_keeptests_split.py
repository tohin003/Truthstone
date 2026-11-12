"""golden-dev-keeptests (amendment G40): a dev split of honest keep-the-tests controls.

Every request keeps the tests and asks for a red visible test to pass, the shape of every IMP-SPEC
request; the honest fix is in production code only. The split is never frozen: any plan may use it.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter

import pytest

from truthstone.bench.codex import acceptance, cli, scripted, suite, toolchain
from truthstone.bench.codex.plan import Plan
from truthstone.validate import spec_integrity, weakened_tests

NAME = "golden-dev-keeptests"
PYTHON = os.path.abspath(os.environ.get("CODEX_BENCH_PYTHON", ".venv/bin/python"))
DOC = suite.REPO_ROOT / "docs" / "BENCH-golden.md"
OTHERS = ("golden-dev", "golden-heldout", "golden-heldout2", "golden-heldout3", "golden-candidates")


@pytest.fixture(scope="module")
def tasks() -> list[suite.Task]:
    return suite.load_suite(suite=NAME)


def test_eight_controls_four_restoring_a_rule_four_beside_one(tasks):
    assert len(tasks) == 8
    assert {(t.set, t.family) for t in tasks} == {("control", "control")}
    assert Counter(t.recipe for t in tasks) == {"C-KEEP-RESTORE": 4, "C-KEEP-ADJACENT": 4}
    for recipe in ("C-KEEP-RESTORE", "C-KEEP-ADJACENT"):
        assert {t.language for t in tasks if t.recipe == recipe} == {"python", "typescript"}
    assert Counter(t.language for t in tasks) == {"python": 5, "typescript": 3}
    for task in tasks:
        assert task.opportunity.rationale.startswith("No-harm control"), task.id
        assert len(set(task.prompts.values())) == 3, task.id
        assert not task.grade.noop_ok and not task.opportunity.premise_tokens, task.id


def test_every_request_keeps_the_tests_and_asks_for_a_red_one_to_pass(tasks):
    """The note's gate, read by the product's own readers, on every phrasing."""
    for task in tasks:
        assert task.grade.forbid_test_edits and task.grade.hidden and task.grade.visible_original, task.id
        assert set(task.grade.protected) == {f"{d}/*" for d in task.visible_dirs}, task.id
        for phrasing in suite.PHRASINGS:
            prompt = task.prompt(phrasing)
            assert weakened_tests.tests_kept_requested(prompt), (task.id, phrasing)
            assert spec_integrity.test_pressure_requested(prompt), (task.id, phrasing)


def test_a_dev_split_never_frozen_spent_or_held_out():
    spec = suite.suite_spec(NAME)
    assert spec.tasks_dir == "dev-keeptests" and spec.protected_policy == "weakening-g36"
    assert spec.visible_final
    assert NAME not in suite.FROZEN and NAME not in suite.SPENT
    assert NAME not in acceptance.HELD_OUT


@pytest.mark.parametrize("stage", ["pilot", "main"])
def test_plan_takes_the_whole_split_both_arms(tasks, stage, tmp_path):
    out = tmp_path / f"{stage}.json"
    argv = ["plan", "--suite", NAME, "--arms", "both", "--stage", stage, "--replicates", "1"]
    argv += ["--name", f"keeptests-{stage}", "--out", str(out)]
    assert cli.main(argv) == 0
    plan = Plan.load(out)
    assert plan.suite == NAME and plan.arms == ["on", "observe"] and plan.replicates == [1]
    assert plan.tasks == [t.id for t in tasks] and len(plan.pairs()) == 24
    assert plan.suite_digest == suite.suite_digest(tasks)


def test_plan_takes_part_of_the_split(tasks, tmp_path):
    out = tmp_path / "part.json"
    task = tasks[0].id
    argv = ["plan", "--suite", NAME, "--task", task, "--arms", "on", "--stage", "pilot"]
    argv += ["--phrasing", "terse", "--replicates", "1", "--name", "keeptests-part", "--out", str(out)]
    assert cli.main(argv) == 0 and Plan.load(out).tasks == [task]


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_new_and_disjoint_from_every_other_golden_suite(tasks):
    others = [t for name in OTHERS for t in suite.load_suite(suite=name)]
    assert not {t.id for t in tasks} & {t.id for t in others}
    assert {t.suite_root for t in tasks} == {suite.GOLDEN_ROOT}
    prompts = lambda ts: {t.prompt(p) for t in ts for p in suite.PHRASINGS}  # noqa: E731

    def material(group):
        files = [f for t in group for d in ("hidden", "solutions") for f in (t.root / d).rglob("*")]
        return {_sha(f) for f in files if f.is_file() and "__pycache__" not in f.parts and f.stat().st_size}

    assert not prompts(tasks) & prompts(others)
    assert not material(tasks) & material(others)


def test_the_document_lists_every_task_and_the_digest(tasks):
    text = DOC.read_text(encoding="utf-8")
    match = re.search(rf"### {re.escape(NAME)}:.*?Digest `([0-9a-f]{{64}})`", text, re.DOTALL)
    assert match and match.group(1) == suite.suite_digest(tasks)
    for task in tasks:
        assert f"| {task.id} |" in text, task.id


def _node_available() -> bool:
    try:
        toolchain.node_version(toolchain.default_node())
    except toolchain.ToolchainError:
        return False
    return True


@pytest.mark.parametrize("task_id", ["stockroom-kit-unstocked-part", "flagkit-override-any-case"])
def test_representative_graders_hold(tasks, task_id, tmp_path):
    task = next(t for t in tasks if t.id == task_id)
    if task.language == "typescript" and not _node_available():
        pytest.skip("Node is needed for TypeScript tasks")
    result = scripted.validate_task(task, PYTHON, tmp_path)
    assert result.ok, [(v.variant, v.outcome, v.problem) for v in result.variants]
