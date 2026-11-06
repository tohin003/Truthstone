"""G22: the heldout2 release-plan script is make-release-plans.sh aimed at the second sealed split.

Same design, shards and accounts as the registered release (G9, G18: main takes pair shards 0-10
of 20, p takes 11-19); every plan names golden-heldout2 and has a new name, so no run directory of
the spent golden-heldout study can ever be resumed by it.
"""

from __future__ import annotations

import re

from truthstone.bench.codex import suite
from truthstone.bench.codex.plan import Plan

PLANS = suite.BENCH_ROOT / "plans"
ORIGINAL = PLANS / "make-release-plans.sh"
HELDOUT2 = PLANS / "make-release-plans-heldout2.sh"


def _var(text: str, name: str) -> str:
    match = re.search(rf'^{name}="([^"]+)"$', text, re.MULTILINE)
    assert match, name
    return match.group(1)


def _plan_commands(text: str) -> list[str]:
    joined = text.replace("\\\n", " ")
    return [line for line in joined.splitlines() if "truthstone.bench.codex plan" in line]


def test_the_shards_and_accounts_are_the_registered_ones():
    original, heldout2 = ORIGINAL.read_text(encoding="utf-8"), HELDOUT2.read_text(encoding="utf-8")
    for name in ("main_shards", "p_shards", "three"):
        assert _var(heldout2, name) == _var(original, name), name
    assert _var(heldout2, "main_shards") == "0,1,2,3,4,5,6,7,8,9,10/20"
    assert _var(heldout2, "p_shards") == "11,12,13,14,15,16,17,18,19/20"
    commands = _plan_commands(heldout2)
    assert len(commands) == 5  # Sol main + p, Luna main + p, one Claude line (two models)
    for command in commands:
        assert "--suite $suite" in command and "--arms both --stage main $three" in command
        assert "--replicates 1,2" in command
    for shard, account in (("$main_shards", "main"), ("$p_shards", "p")):
        assert sum(f"--shard {shard} --accounts {account}" in c for c in commands) == 2
    for command in commands:  # G21: main's plans carry the final run's weekly line, no other does
        assert ("--week-stop main=80" in command) == ("--accounts main " in command)
    assert _var(heldout2, "suite") == "golden-heldout2"
    assert _var(heldout2, "sol") == _var(original, "sol") and _var(heldout2, "luna") == _var(original, "luna")


def test_every_plan_name_is_new():
    original, heldout2 = ORIGINAL.read_text(encoding="utf-8"), HELDOUT2.read_text(encoding="utf-8")
    names = re.findall(r"--name \"?([\w$.-]+)\"?", heldout2.replace("\\\n", " "))
    assert names and all(name.startswith("golden-heldout2-") for name in names)
    assert not set(names) & set(re.findall(r"--name \"?([\w$.-]+)\"?", original.replace("\\\n", " ")))


def test_the_shards_partition_heldout2s_design_with_main_taking_eleven_twentieths():
    tasks = [t.id for t in suite.load_suite(suite="golden-heldout2")]
    base = dict(
        name="h2", stage="main", seed=1, tasks=tasks, phrasings=list(suite.PHRASINGS), replicates=[1, 2]
    )
    whole = {p.id for p in Plan(**base).pairs()}
    main = {p.id for p in Plan(**base, pair_shard=[*range(11), 20]).pairs()}
    p = {p.id for p in Plan(**base, pair_shard=[*range(11, 20), 20]).pairs()}
    assert len(whole) == 186 and main | p == whole and not main & p
    assert len(main) > len(p)
