"""G49: the heldout5 release-plan script, the plans of the fifth sealed held-out split's release run.

The registered design (G9: 31 tasks x 3 phrasings x R=2 x both arms), Codex + Sol with the earlier
release scripts' models and flags, on one account, main, with its weekly stop at 98% (G31's
arrangement): two disjoint pair shards of ten twentieths each, run one after the other, the same
shards and flags as the heldout4 script. Every plan names golden-heldout5 and has a new name, so no
run directory of an earlier study can ever be resumed by it. Registered after G44, its cells are
graded under `weakening-g44` from the start; the policy lives in the suite's registration, so the
frozen digest the plans pin is the one G49 registers.
"""

from __future__ import annotations

import re

from truthstone.bench.codex import regrade, suite
from truthstone.bench.codex.plan import Plan

PLANS = suite.BENCH_ROOT / "plans"
OLDER = (
    PLANS / "make-release-plans.sh",
    PLANS / "make-release-plans-heldout2.sh",
    PLANS / "make-release-plans-heldout3.sh",
    PLANS / "make-release-plans-heldout4.sh",
)
HELDOUT4 = PLANS / "make-release-plans-heldout4.sh"
HELDOUT5 = PLANS / "make-release-plans-heldout5.sh"


def _var(text: str, name: str) -> str:
    match = re.search(rf'^{name}="([^"]+)"$', text, re.MULTILINE)
    assert match, name
    return match.group(1)


def _plan_commands(text: str) -> list[str]:
    joined = text.replace("\\\n", " ")
    return [line for line in joined.splitlines() if "truthstone.bench.codex plan" in line]


def _names(text: str) -> set[str]:
    return set(re.findall(r"--name \"?([\w$.-]+)\"?", text.replace("\\\n", " ")))


def test_the_design_model_and_flags_are_the_registered_ones_on_main_alone():
    heldout4, heldout5 = HELDOUT4.read_text(encoding="utf-8"), HELDOUT5.read_text(encoding="utf-8")
    for name in ("three", "sol", "a_shards", "b_shards"):  # the same phrasings, model, flags and shards
        assert _var(heldout5, name) == _var(heldout4, name), name
    assert _var(heldout5, "sol") == (
        "--model gpt-6.1-sol --effort medium --truthstone-ref $ref --weekly-percent-per-cell 0.1"
    )
    assert _var(heldout5, "suite") == "golden-heldout5"
    assert _var(heldout5, "a_shards") == "0,1,2,3,4,5,6,7,8,9/20"
    assert _var(heldout5, "b_shards") == "10,11,12,13,14,15,16,17,18,19/20"
    commands = _plan_commands(heldout5)
    assert len(commands) == 2  # Sol only: the release gate's two shards
    for command, shard, name in zip(commands, ("$a_shards", "$b_shards"), ("a", "b"), strict=True):
        assert "--suite $suite --arms both --stage main $three" in command
        assert "--replicates 1,2 $sol" in command
        assert f"--shard {shard} --accounts main --week-stop main=98" in command
        assert f"--name golden-heldout5-sol-main-{name} " in command
        assert f'--out "$out/golden-heldout5-sol-main-{name}.json"' in command
        assert "--accounts p" not in command and "--host" not in command


def test_every_plan_name_is_new():
    names = _names(HELDOUT5.read_text(encoding="utf-8"))
    assert names == {"golden-heldout5-sol-main-a", "golden-heldout5-sol-main-b"}
    for older in OLDER:
        assert not names & _names(older.read_text(encoding="utf-8")), older.name


def test_the_two_shards_partition_heldout5s_design():
    tasks = [t.id for t in suite.load_suite(suite="golden-heldout5")]
    assert len(tasks) == 31
    base = dict(
        name="h5", stage="main", seed=1, tasks=tasks, phrasings=list(suite.PHRASINGS), replicates=[1, 2]
    )
    whole = {p.id for p in Plan(**base).pairs()}
    a = {p.id for p in Plan(**base, pair_shard=[*range(10), 20]).pairs()}
    b = {p.id for p in Plan(**base, pair_shard=[*range(10, 20), 20]).pairs()}
    assert len(whole) == 186 and a | b == whole and not a & b
    assert (len(a), len(b)) == (96, 90)  # residues 0-9 and 10-19 of the 186 positions, modulo 20


def test_the_plans_cells_are_graded_under_weakening_g44_and_the_digest_is_the_frozen_one():
    """G49: golden-heldout5 is graded under `weakening-g44`, every task and the re-grade's registered
    policy alike, and the split digests to its frozen value."""
    name = _var(HELDOUT5.read_text(encoding="utf-8"), "suite")
    tasks = suite.load_suite(suite=name)
    ids = [t.id for t in tasks]
    plan = Plan(name="h5", stage="main", seed=1, tasks=ids, phrasings=["terse"], replicates=[1], suite=name)
    assert suite.suite_spec(name).protected_policy == regrade.policy_of(plan) == "weakening-g44"
    assert {t.grade.protected_policy for t in tasks} == {"weakening-g44"}
    assert suite.suite_digest(tasks) == suite.FROZEN[name]
