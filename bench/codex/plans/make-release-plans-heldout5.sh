#!/bin/sh
# The release plans for the fifth sealed held-out split, golden-heldout5 (amendment G49), built
# blind after golden-heldout4 was spent by the final release run's futility stop, regenerated for
# one pinned build:
#
#   sh bench/codex/plans/make-release-plans-heldout5.sh <truthstone-ref>
#
# The registered design (G9: the 31 tasks x 3 phrasings x R=2 x both arms = 186 pairs, every pair
# both arms back to back), Codex + Sol with the models and flags of the earlier release scripts, on
# ONE account, main (G31's arrangement, as for golden-heldout3 and golden-heldout4), with main's
# weekly stop at 98% (--week-stop main=98). Two disjoint pair shards, run one after the other on
# main (one runner per account): golden-heldout5-sol-main-a takes pair shards 0-9 of 20 (96 pairs),
# golden-heldout5-sol-main-b takes 10-19 (90 pairs). A pair never spans runs; the analysis and the
# gate read the two runs as one design. Every plan name is new, so no run directory of an earlier
# study is ever resumed. Run from the root of a CLEAN checkout of the frozen benchmark (registration
# refuses task content git does not track, and `plan` refuses any golden-heldout5 digest but the
# frozen one). Nothing is launched. OUT=<dir> writes the plans elsewhere (a dry check); the default
# is bench/codex/plans.
set -eu
ref=${1:?usage: make-release-plans-heldout5.sh <truthstone-ref>}
py=".venv/bin/python"
out="${OUT:-bench/codex/plans}"
suite="golden-heldout5"
three="--phrasing canonical --phrasing terse --phrasing conversational"
sol="--model gpt-6.1-sol --effort medium --truthstone-ref $ref --weekly-percent-per-cell 0.1"
a_shards="0,1,2,3,4,5,6,7,8,9/20"
b_shards="10,11,12,13,14,15,16,17,18,19/20"

# The release gate (G9 on golden-heldout5): Codex + Sol, both arms, two disjoint pair shards, both
# on main, run one after the other (a first, then b); the analysis and the gate pool the two runs.
$py -m truthstone.bench.codex plan --suite $suite --arms both --stage main $three \
    --replicates 1,2 $sol --shard $a_shards --accounts main --week-stop main=98 \
    --name golden-heldout5-sol-main-a --out "$out/golden-heldout5-sol-main-a.json"
$py -m truthstone.bench.codex plan --suite $suite --arms both --stage main $three \
    --replicates 1,2 $sol --shard $b_shards --accounts main --week-stop main=98 \
    --name golden-heldout5-sol-main-b --out "$out/golden-heldout5-sol-main-b.json"
