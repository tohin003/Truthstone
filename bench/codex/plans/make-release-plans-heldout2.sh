#!/bin/sh
# The release plans for the second sealed held-out split, golden-heldout2 (amendment G22),
# regenerated for one pinned build:
#
#   sh bench/codex/plans/make-release-plans-heldout2.sh <truthstone-ref>
#
# The heldout2 variant of make-release-plans.sh: the same design (G9: the 31 tasks x 3 phrasings x
# R=2 x both arms = 186 pairs), the same shards and accounts (G18: main takes pair shards 0-10/20,
# p takes 11-19/20; the shards run ONE AT A TIME, main first) and the same models. Only the suite
# and the plan names differ: every plan is new, so no run directory of the spent golden-heldout
# study is ever resumed. Run from the root of a CLEAN checkout of the frozen benchmark
# (registration refuses task content git does not track, and `plan` refuses any golden-heldout2
# digest but the frozen one). Nothing is launched. OUT=<dir> writes the plans elsewhere (a dry
# check); the default is bench/codex/plans.
set -eu
ref=${1:?usage: make-release-plans-heldout2.sh <truthstone-ref>}
py=".venv/bin/python"
out="${OUT:-bench/codex/plans}"
suite="golden-heldout2"
three="--phrasing canonical --phrasing terse --phrasing conversational"
sol="--model gpt-6.1-sol --effort medium --truthstone-ref $ref --weekly-percent-per-cell 0.1"
luna="--model gpt-6-luna --effort medium --truthstone-ref $ref --weekly-percent-per-cell 0.1"
main_shards="0,1,2,3,4,5,6,7,8,9,10/20"
p_shards="11,12,13,14,15,16,17,18,19/20"

# The release gate (G9 on golden-heldout2): Codex + Sol, both arms, two disjoint pair shards, one
# runner per account; the analysis and the gate pool the two runs as one design.
$py -m truthstone.bench.codex plan --suite $suite --arms both --stage main $three \
    --replicates 1,2 $sol --shard $main_shards --accounts main \
    --name golden-heldout2-sol-main-main --out "$out/golden-heldout2-sol-main-main.json"
$py -m truthstone.bench.codex plan --suite $suite --arms both --stage main $three \
    --replicates 1,2 $sol --shard $p_shards --accounts p \
    --name golden-heldout2-sol-main-p --out "$out/golden-heldout2-sol-main-p.json"

# G10 on golden-heldout2 (weaker models; reported, never gates). Luna: the same shards, each after
# the same account's Sol shard has finished (one runner per account).
$py -m truthstone.bench.codex plan --suite $suite --arms both --stage main $three \
    --replicates 1,2 $luna --shard $main_shards --accounts main \
    --name golden-heldout2-luna-main-main --out "$out/golden-heldout2-luna-main-main.json"
$py -m truthstone.bench.codex plan --suite $suite --arms both --stage main $three \
    --replicates 1,2 $luna --shard $p_shards --accounts p \
    --name golden-heldout2-luna-main-p --out "$out/golden-heldout2-luna-main-p.json"
# Claude Code: re-make these with --per-cell-session and --per-cell-week from each model's smoke
# cells before running them (unset, the runner cannot refuse a pair the windows cannot finish).
for model in claude-sonnet-5-5 claude-opus-5-5; do
    $py -m truthstone.bench.codex plan --host claude --accounts work,personal --suite $suite \
        --arms both --stage main $three --replicates 1,2 --model $model --effort medium \
        --truthstone-ref "$ref" --name "golden-heldout2-$model" \
        --out "$out/golden-heldout2-$model.json"
done
