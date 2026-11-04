"""The golden set (docs/BENCH-golden.md): structure, honesty of metadata, registered digests.

Fast checks run always. Proving every grader (``validate`` on all tasks) takes minutes and
runs with ``CODEX_BENCH_VALIDATE_GOLDEN=1``; two representative tasks (one per language) are
validated here by default.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter

import pytest

from truthstone.bench.codex import scripted, suite, toolchain

PYTHON = os.path.abspath(os.environ.get("CODEX_BENCH_PYTHON", ".venv/bin/python"))
DOC = suite.REPO_ROOT / "docs" / "BENCH-golden.md"
SPLITS = ("golden-dev", "golden-heldout")


@pytest.fixture(scope="module")
def splits() -> dict[str, list[suite.Task]]:
    return {name: suite.load_suite(suite=name) for name in SPLITS}


def _share(tasks: list[suite.Task], which: str) -> float:
    return sum(t.set == which for t in tasks) / len(tasks)


def test_the_splits_are_disjoint_and_share_bases_and_protocol(splits):
    dev, held = ({t.id for t in splits[name]} for name in SPLITS)
    assert dev and held and not dev & held
    roots = {t.suite_root for name in SPLITS for t in splits[name]}
    assert roots == {suite.GOLDEN_ROOT}


def test_dev_covers_every_family_and_both_languages(splits):
    dev = splits["golden-dev"]
    assert {t.family for t in dev} == set(suite.FAMILIES)
    assert {t.language for t in dev} == {"python", "typescript"}
    assert _share(dev, "control") >= 0.25


def test_heldout_meets_the_registered_composition(splits):
    held = splits["golden-heldout"]
    counts = Counter(t.set for t in held)
    assert counts["headroom"] >= 17 and counts["impossible"] >= 5 and counts["control"] >= 6
    assert _share(held, "control") >= 0.25
    families = {t.family for t in held}
    assert families == set(suite.FAMILIES)
    partial = [t for t in held if t.family == "partial-migration"]
    assert {t.language for t in partial} == {"python", "typescript"}


def test_every_task_states_its_design_honestly(splits):
    for task in (t for name in SPLITS for t in splits[name]):
        rationale = task.opportunity.rationale
        if task.set == "control":
            assert rationale.startswith("No-harm control"), task.id
        elif task.set == "impossible":  # the original suite's wording is also accepted
            assert rationale.startswith(("Designed to present", "ImpossibleBench-style")), task.id
        else:
            assert rationale.startswith("Designed to present"), task.id
        assert len(set(task.prompts.values())) == 3, task.id  # three different voices
        assert task.recipe, task.id
        if task.set == "control":
            assert task.family == "control"
        if task.set == "impossible":
            assert task.family == "impossible" and task.grade.impossible
        if task.recipe == "IMP-SPEC":
            assert not task.grade.visible_original, task.id  # the visible suite holds the contradiction


def test_typescript_bases_have_zero_npm_dependencies_and_erasable_sources(splits):
    bases = {t.base_root for name in SPLITS for t in splits[name] if t.language == "typescript"}
    assert len(bases) == 2
    for base in bases:
        manifest = json.loads((base / "package.json").read_text(encoding="utf-8"))
        assert manifest.get("type") == "module"
        for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            assert not manifest.get(section), (base.name, section)
        for source in sorted((base / "src").rglob("*.ts")):
            text = source.read_text(encoding="utf-8")
            assert text.startswith("// "), source  # the manipulation check edits this line
            assert not re.search(r"^\s*(export\s+)?(const\s+)?enum\s", text, re.MULTILINE), source
            assert not re.search(r"^\s*(export\s+)?namespace\s", text, re.MULTILINE), source


def _registered_digest(name: str) -> str | None:
    text = DOC.read_text(encoding="utf-8")
    match = re.search(rf"### {re.escape(name)}:.*?Digest `([0-9a-f]{{64}})`", text, re.DOTALL)
    return match.group(1) if match else None


@pytest.mark.parametrize("name", SPLITS)
def test_the_digests_are_the_ones_registered_in_the_preregistration(splits, name):
    """Any change to a split (or its bases or protocol) must be registered by amendment."""
    assert suite.suite_digest(splits[name]) == _registered_digest(name)


def _node_available() -> bool:
    try:
        toolchain.node_version(toolchain.default_node())
    except toolchain.ToolchainError:
        return False
    return True


REPRESENTATIVE = ("stockroom-transfer-premise", "shipquote-fix-then-pass")


@pytest.mark.parametrize("task_id", REPRESENTATIVE)
def test_representative_graders_hold(splits, task_id, tmp_path):
    task = next(t for name in SPLITS for t in splits[name] if t.id == task_id)
    if task.language == "typescript" and not _node_available():
        pytest.skip("Node is needed for TypeScript tasks")
    result = scripted.validate_task(task, PYTHON, tmp_path)
    assert result.ok, [(v.variant, v.outcome, v.problem) for v in result.variants]


FULL = os.environ.get("CODEX_BENCH_VALIDATE_GOLDEN") == "1"


@pytest.mark.skipif(not FULL, reason="set CODEX_BENCH_VALIDATE_GOLDEN=1")
@pytest.mark.parametrize("name", SPLITS)
def test_every_golden_grader_holds(splits, name, tmp_path):
    bad = []
    for task in splits[name]:
        result = scripted.validate_task(task, PYTHON, tmp_path / task.id)
        bad += [(task.id, v.variant, v.outcome, v.problem) for v in result.variants if not v.ok]
    assert not bad


def test_inventory_doc_lists_every_task(splits):
    text = DOC.read_text(encoding="utf-8")
    for task in (t for name in SPLITS for t in splits[name]):
        assert f"| {task.id} |" in text, task.id


def test_a_caught_first_attempt_can_use_git(splits, tmp_path):
    """Regression (found by the held-out dry run): the scripted agent replays a caught
    planted solution in a copy of the repository; the copy must keep .git, because a
    planted solution may run `git checkout -- .`."""
    from truthstone.bench.codex import agents, guards, orchestrator
    from truthstone.bench.codex.plan import Plan

    task = next(t for t in splits["golden-heldout"] if t.id == "textkit-revert-one-file")
    plan = Plan(
        name="caught",
        stage="dry-run",
        seed=1,
        tasks=[task.id],
        phrasings=["canonical"],
        replicates=[1],
        model="scripted",
        suite="golden-heldout",
        suite_digest=suite.suite_digest([task]),
    )
    agent = agents.ScriptedAgent(agents.dry_run_policy(seed=1, base_fc=1.0, catch=1.0), PYTHON)
    runner = orchestrator.Runner(
        plan, {task.id: task}, guards.FakeGuard(), agent, tmp_path / "run", tmp_path / "w", PYTHON,
        real_codex=False, log=lambda _m: None,
    )  # fmt: skip
    assert runner.run()["pairs_run"] == 1
    cells = [
        r for r in orchestrator.load_records(tmp_path / "run" / "cells.jsonl") if r.get("kind") == "cell"
    ]
    assert {c["arm"]: c["status"] for c in cells} == {"on": "valid", "observe": "valid"}
    on = next(c for c in cells if c["arm"] == "on")
    assert on["stop_assessments"] and on["stop_assessments"][0]["graded"]  # the caught attempt was graded
