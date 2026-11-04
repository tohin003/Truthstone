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

# G9, the held-out main study (the release gate): both arms, the 31 frozen tasks x 3 phrasings x
# R=2 = 186 pairs, as two disjoint pair shards run in parallel, one runner per account. The
# dedicated account p takes three fifths (112 pairs), main two fifths (74 pairs), which keeps main
# under its reserves; the analysis and the gate pool the two runs as one design.
$py -m truthstone.bench.codex plan --suite golden-heldout --arms both --stage main $three \
    --replicates 1,2 $sol --shard 0,1,2/5 --accounts p \
    --name golden-heldout-sol-main-p --out $out/golden-heldout-sol-main-p.json
$py -m truthstone.bench.codex plan --suite golden-heldout --arms both --stage main $three \
    --replicates 1,2 $sol --shard 3,4/5 --accounts main \
    --name golden-heldout-sol-main-main --out $out/golden-heldout-sol-main-main.json

# G10, weaker models on the same frozen split (reported, not gates). Luna: the same split; each
# shard starts only after the same account's Sol shard has finished (one runner per account).
$py -m truthstone.bench.codex plan --suite golden-heldout --arms both --stage main $three \
    --replicates 1,2 $luna --shard 0,1,2/5 --accounts p \
    --name golden-heldout-luna-main-p --out $out/golden-heldout-luna-main-p.json
$py -m truthstone.bench.codex plan --suite golden-heldout --arms both --stage main $three \
    --replicates 1,2 $luna --shard 3,4/5 --accounts main \
    --name golden-heldout-luna-main-main --out $out/golden-heldout-luna-main-main.json
# Claude Code: re-make these with --per-cell-session and --per-cell-week from each model's two
# smoke cells before running them (unset, the runner cannot refuse a pair the windows cannot finish).
for model in claude-sonnet-5-5 claude-opus-5-5; do
    $py -m truthstone.bench.codex plan --host claude --accounts work,personal --suite golden-heldout \
        --arms both --stage main $three --replicates 1,2 --model $model --effort medium \
        --truthstone-ref "$ref" --name "golden-heldout-$model" \
        --out "$out/golden-heldout-$model.json"
done
