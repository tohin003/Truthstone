"""G28: the heldout3 release-plan script is make-release-plans-heldout2.sh aimed at the third sealed split.

Same design, shards, accounts and flags as the registered releases (G9, G18: main takes pair shards
0-10 of 20, p takes 11-19; G21: main's plans carry the 80% weekly line); every plan names
golden-heldout3 and has a new name, so no run directory of the spent golden-heldout or
golden-heldout2 studies can ever be resumed by it.
"""

from __future__ import annotations

import re

from truthstone.bench.codex import suite
from truthstone.bench.codex.plan import Plan

PLANS = suite.BENCH_ROOT / "plans"
ORIGINAL = PLANS / "make-release-plans.sh"
HELDOUT2 = PLANS / "make-release-plans-heldout2.sh"
HELDOUT3 = PLANS / "make-release-plans-heldout3.sh"


def _var(text: str, name: str) -> str:
    match = re.search(rf'^{name}="([^"]+)"$', text, re.MULTILINE)
    assert match, name
    return match.group(1)


def _plan_commands(text: str) -> list[str]:
    joined = text.replace("\\\n", " ")
    return [line for line in joined.splitlines() if "truthstone.bench.codex plan" in line]


def _names(text: str) -> set[str]:
    return set(re.findall(r"--name \"?([\w$.-]+)\"?", text.replace("\\\n", " ")))


def test_the_shards_accounts_and_flags_are_the_registered_ones():
    original, heldout2 = ORIGINAL.read_text(encoding="utf-8"), HELDOUT2.read_text(encoding="utf-8")
    heldout3 = HELDOUT3.read_text(encoding="utf-8")
    for name in ("main_shards", "p_shards", "three"):
        assert _var(heldout3, name) == _var(original, name) == _var(heldout2, name), name
    assert _var(heldout3, "main_shards") == "0,1,2,3,4,5,6,7,8,9,10/20"
    assert _var(heldout3, "p_shards") == "11,12,13,14,15,16,17,18,19/20"
    for name in ("sol", "luna"):
        assert _var(heldout3, name) == _var(original, name) == _var(heldout2, name), name
    assert _var(heldout3, "suite") == "golden-heldout3"
    commands = _plan_commands(heldout3)
    assert len(commands) == 5  # Sol main + p, Luna main + p, one Claude line (two models)
    for command in commands:
        assert "--suite $suite" in command and "--arms both --stage main $three" in command
        assert "--replicates 1,2" in command
    for shard, account in (("$main_shards", "main"), ("$p_shards", "p")):
        assert sum(f"--shard {shard} --accounts {account}" in c for c in commands) == 2
    for command in commands:  # G21: main's plans carry the final run's weekly line, no other does
        assert ("--week-stop main=80" in command) == ("--accounts main " in command)
    # The same commands as heldout2's script, but for the suite and the plan names.
    same = [c.replace("golden-heldout3", "golden-heldout2") for c in commands]
    assert same == _plan_commands(heldout2)


def test_every_plan_name_is_new():
    names = _names(HELDOUT3.read_text(encoding="utf-8"))
    assert names and all(name.startswith("golden-heldout3-") for name in names)
    for older in (ORIGINAL, HELDOUT2):
        assert not names & _names(older.read_text(encoding="utf-8")), older.name


def test_the_shards_partition_heldout3s_design_with_main_taking_eleven_twentieths():
    tasks = [t.id for t in suite.load_suite(suite="golden-heldout3")]
    base = dict(
        name="h3", stage="main", seed=1, tasks=tasks, phrasings=list(suite.PHRASINGS), replicates=[1, 2]
    )
    whole = {p.id for p in Plan(**base).pairs()}
    main = {p.id for p in Plan(**base, pair_shard=[*range(11), 20]).pairs()}
    p = {p.id for p in Plan(**base, pair_shard=[*range(11, 20), 20]).pairs()}
    assert len(whole) == 186 and main | p == whole and not main & p
    assert len(main) > len(p)
