# ruff: noqa  (one-off evidence script for amendment G13, kept verbatim)
# Amendment G13 evidence: P(pass) of option B at the dev GO/NO-GO size (guarded 1 rep vs observe 2).
# Usage: .venv/bin/python bench/codex/analysis/t5_dev.py <screen run>/cells.jsonl
"""Option B at GO/NO-GO size: 20 dev tasks x 3 phrasings, guarded 1 rep vs observe 2 reps (the screen)."""
import json, math, random, statistics, sys
from collections import defaultdict
from truthstone.bench.codex.acceptance import _median_ratio_ci
cells = [json.loads(l) for l in open(sys.argv[1])]
pairs = defaultdict(list)
for c in cells:
    task, phr = c["cell_id"].split(".")[:2]
    tok = (c.get("usage") or {}).get("total_tokens")
    if tok and c.get("arm") == "observe":
        pairs[(task, phr)].append(math.log(tok))
pairs = {k: v for k, v in pairs.items() if len(v) == 2}
sd = statistics.pstdev([(a - b) / math.sqrt(2) for a, b in pairs.values()])
rng = random.Random(3)
for effect in (1.00, 1.05, 1.10):
    ok_b = ok_point = 0
    for _ in range(300):
        obs, grd = defaultdict(list), defaultdict(list)
        for (task, _), (a, b) in pairs.items():
            level = (a + b) / 2
            obs[task] += [math.exp(level + rng.gauss(0, sd)) for _ in range(2)]
            grd[task].append(math.exp(level + rng.gauss(0, sd)) * effect)
        p, u = _median_ratio_ci(obs, grd, 600)
        ok_b += p <= 1.05 and u <= 1.15
        ok_point += p <= 1.05
    print(f"true x{effect:.2f}: P(pass B: point<=1.05 & upper<=1.15)={ok_b/300:.2f}  P(point<=1.05 only)={ok_point/300:.2f}")
