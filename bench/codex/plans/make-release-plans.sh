#!/bin/sh
# The release plans (golden amendments G9 and G10), regenerated for one pinned build:
#
#   sh bench/codex/plans/make-release-plans.sh <truthstone-ref>
#
# Run from the root of a CLEAN checkout of the frozen benchmark (registration refuses task content
# git does not track). Nothing is launched. Each plan pins the build ref, the suite digest of its
# split (the frozen held-out digest for the held-out plans) and its accounts.
set -eu
ref=${1:?usage: make-release-plans.sh <truthstone-ref>}
py=".venv/bin/python"
out="bench/codex/plans"
three="--phrasing canonical --phrasing terse --phrasing conversational"
sol="--model gpt-6.1-sol --effort medium --truthstone-ref $ref --weekly-percent-per-cell 0.1"
luna="--model gpt-6-luna --effort medium --truthstone-ref $ref --weekly-percent-per-cell 0.1"

# G9, the dev GO/NO-GO: the guarded arm alone on dev, 20 tasks x 3 phrasings x replicate 1 = 60
# cells on the dedicated account; acceptance pools it with the extended screen's unguarded cells.
$py -m truthstone.bench.codex plan --suite golden-dev --arms on --stage pilot $three --replicates 1 \
    $sol --accounts p --name golden-dev-sol-guarded1 --out $out/golden-dev-sol-guarded1.json
# ... and the screened FP-CONFIG candidate (not held-out; 6/6 unguarded false completions in the
# candidate screen), so the check covers both strong recipes: 3 more guarded cells, same account.
# Run the two plans one after the other (one runner per account at a time).
$py -m truthstone.bench.codex plan --suite golden-candidates --task fetchkit-debug-env-premise \
    --arms on --stage pilot $three --replicates 1 $sol --accounts p \
    --name golden-cand-sol-guarded1 --out $out/golden-cand-sol-guarded1.json

# G9, the held-out main study (the release gate): both arms, 31 tasks x 3 phrasings x R=2, as two
# disjoint pair shards run in parallel, one per account; the analysis pools them.
for shard in 0 1; do
    account=$([ $shard = 0 ] && echo p || echo main)
    $py -m truthstone.bench.codex plan --suite golden-heldout --arms both --stage main $three \
        --replicates 1,2 $sol --shard $shard/2 --accounts $account \
        --name golden-heldout-sol-main-$account --out $out/golden-heldout-sol-main-$account.json
done

# G10, weaker models on the same frozen split (reported, not gates).
for shard in 0 1; do
    account=$([ $shard = 0 ] && echo p || echo main)
    $py -m truthstone.bench.codex plan --suite golden-heldout --arms both --stage main $three \
        --replicates 1,2 $luna --shard $shard/2 --accounts $account \
        --name golden-heldout-luna-main-$account --out $out/golden-heldout-luna-main-$account.json
done
for model in claude-sonnet-5-5 claude-opus-5-5; do
    $py -m truthstone.bench.codex plan --host claude --accounts work,personal --suite golden-heldout \
        --arms both --stage main $three --replicates 1,2 --model $model --effort medium \
        --truthstone-ref "$ref" --name "golden-heldout-$model" --out "$out/golden-heldout-$model.json"
done
