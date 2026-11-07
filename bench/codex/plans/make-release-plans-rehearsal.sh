#!/bin/sh
# The plan for the dress rehearsal, golden-rehearsal (amendment G38), regenerated for one pinned
# build:
#
#   sh bench/codex/plans/make-release-plans-rehearsal.sh <truthstone-ref>
#
# The release gate's design (G9) at one replicate: the 31 tasks x 3 phrasings x R=1 x both arms =
# 93 pairs (186 cells), Codex + Sol at medium effort with the heldout scripts' Sol flags, both arms
# paired, one plan on account main only (no p shard) with main's weekly stop at 98% (as G31 ran
# golden-heldout3). Only the suite, the replicates, the account and the plan name differ from the
# held-out scripts: the plan is new, so no run directory of a spent study is ever resumed. Run from
# the root of a CLEAN checkout of the frozen benchmark (registration refuses task content git does
# not track, and `plan` refuses any golden-rehearsal digest but the frozen one). Nothing is launched.
# OUT=<dir> writes the plan elsewhere (a dry check); the default is bench/codex/plans.
set -eu
ref=${1:?usage: make-release-plans-rehearsal.sh <truthstone-ref>}
py=".venv/bin/python"
out="${OUT:-bench/codex/plans}"
suite="golden-rehearsal"
three="--phrasing canonical --phrasing terse --phrasing conversational"
sol="--model gpt-6.1-sol --effort medium --truthstone-ref $ref --weekly-percent-per-cell 0.1"

# The release gate's design on golden-rehearsal: Codex + Sol, both arms, one replicate, every pair
# on main (one runner); the analysis and the gate read the one run.
$py -m truthstone.bench.codex plan --suite $suite --arms both --stage main $three \
    --replicates 1 $sol --accounts main --week-stop main=98 \
    --name golden-rehearsal-sol-main --out "$out/golden-rehearsal-sol-main.json"
