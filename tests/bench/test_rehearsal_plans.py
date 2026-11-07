"""G38: the dress rehearsal's plan script is the release gate's design aimed at golden-rehearsal at
one replicate: both arms paired, every pair on account main (no p shard), main's weekly stop at 98%.

Same Sol model, effort, flags and phrasings as the registered release scripts (G9); the plan names
golden-rehearsal and has a new name, so no run directory of the spent held-out studies can ever be
resumed by it.
"""

from __future__ import annotations

import re

from truthstone.bench.codex import suite
from truthstone.bench.codex.plan import Plan

PLANS = suite.BENCH_ROOT / "plans"
ORIGINAL = PLANS / "make-release-plans.sh"
HELDOUT2 = PLANS / "make-release-plans-heldout2.sh"
HELDOUT3 = PLANS / "make-release-plans-heldout3.sh"
REHEARSAL = PLANS / "make-release-plans-rehearsal.sh"


def _var(text: str, name: str) -> str:
    match = re.search(rf'^{name}="([^"]+)"$', text, re.MULTILINE)
    assert match, name
    return match.group(1)


def _plan_commands(text: str) -> list[str]:
    joined = text.replace("\\\n", " ")
    return [line for line in joined.splitlines() if "truthstone.bench.codex plan" in line]


def _names(text: str) -> set[str]:
    return set(re.findall(r"--name \"?([\w$.-]+)\"?", text.replace("\\\n", " ")))


def test_one_paired_sol_plan_one_replicate_on_main_with_the_98_percent_weekly_stop():
    rehearsal = REHEARSAL.read_text(encoding="utf-8")
    for older in (ORIGINAL, HELDOUT2, HELDOUT3):  # the registered phrasings and Sol flags
        text = older.read_text(encoding="utf-8")
        for name in ("three", "sol"):
            assert _var(rehearsal, name) == _var(text, name), (older.name, name)
    assert _var(rehearsal, "suite") == "golden-rehearsal"
    commands = _plan_commands(rehearsal)
    assert len(commands) == 1  # Sol only: no p shard, no weaker-model lines
    (command,) = commands
    assert "--suite $suite --arms both --stage main $three" in command
    assert re.search(r"--replicates 1 ", command)
    assert "--accounts main --week-stop main=98" in command
    assert "--shard" not in command and "--accounts p" not in command and "luna" not in command
    assert "$sol" in command and "--host" not in command


def test_every_plan_name_is_new():
    names = _names(REHEARSAL.read_text(encoding="utf-8"))
    assert names == {"golden-rehearsal-sol-main"}
    for older in (ORIGINAL, HELDOUT2, HELDOUT3):
        assert not names & _names(older.read_text(encoding="utf-8")), older.name


def test_the_one_plan_covers_the_whole_design_once():
    tasks = [t.id for t in suite.load_suite(suite="golden-rehearsal")]
    plan = Plan(name="rh", stage="main", seed=1, tasks=tasks, phrasings=list(suite.PHRASINGS), replicates=[1])
    pairs = [p.id for p in plan.pairs()]
    assert len(tasks) == 31 and len(pairs) == len(set(pairs)) == 93
