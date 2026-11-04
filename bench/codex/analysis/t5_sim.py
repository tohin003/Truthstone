# ruff: noqa  (one-off evidence script for amendment G13, kept verbatim)
# Amendment G13 evidence: P(pass) of candidate T5 rules at held-out size (31 tasks x 3 x 2 per arm).
# Usage: .venv/bin/python bench/codex/analysis/t5_sim.py <screen run>/cells.jsonl
"""Pass probability of candidate T5 rules at held-out size (31 tasks x 3 phrasings x 2 reps per arm),
from a model fitted to the dev screen: log cost = task-phrasing level + replicate noise."""
import json, math, random, statistics, sys
from collections import defaultdict
from truthstone.bench.codex.acceptance import _median_ratio_ci

cells = [json.loads(l) for l in open(sys.argv[1])]
pairs = defaultdict(list)
for c in cells:
    if c.get("arm") != "observe":
        continue
    task, phr = c["cell_id"].split(".")[:2]
    tok = (c.get("usage") or {}).get("total_tokens")
    wall = c.get("wall_s") or (c.get("duration_ms") or 0) / 1000 or None
    if tok and wall:
        pairs[(task, phr)].append((math.log(tok), math.log(wall)))
pairs = {k: v for k, v in pairs.items() if len(v) == 2}
levels = defaultdict(list)  # task -> list of (tok, wall) phrasing levels
noise = {"tok": [], "wall": []}
for (task, _), (a, b) in pairs.items():
    levels[task].append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    noise["tok"].append((a[0] - b[0]) / math.sqrt(2)); noise["wall"].append((a[1] - b[1]) / math.sqrt(2))
sd = {k: statistics.pstdev(v) for k, v in noise.items()}
print(f"replicate noise sd (log): tokens {sd['tok']:.3f}, wall {sd['wall']:.3f}")
tasks = list(levels)
RULES = {
    "R0 current: tok&wall point<=1.00, upper<=1.10": (("tok", "wall"), 1.00, 1.10),
    "R1 tokens only: point<=1.05, upper<=1.15": (("tok",), 1.05, 1.15),
    "R2 tok&wall: point<=1.05, upper<=1.20": (("tok", "wall"), 1.05, 1.20),
    "R3 tokens only: point<=1.00, upper<=1.15": (("tok",), 1.00, 1.15),
}
rng = random.Random(11)
def study(effect):
    """One simulated held-out study; effect = true guarded/observe cost multiplier."""
    chosen = [rng.choice(tasks) for _ in range(31)]
    arms = [defaultdict(lambda: {"tok": [], "wall": []}) for _ in range(2)]
    for i, t in enumerate(chosen):
        for lv in levels[t][:3]:
            for arm, mult in ((0, 1.0), (1, effect)):
                for _ in range(2):
                    for j, k in enumerate(("tok", "wall")):
                        arms[arm][f"{t}#{i}"][k].append(math.exp(lv[j] + rng.gauss(0, sd[k])) * mult)
    out = {}
    for k in ("tok", "wall"):
        p, u = _median_ratio_ci({t: arms[0][t][k] for t in arms[0]}, {t: arms[1][t][k] for t in arms[1]}, 600)
        out[k] = (p, u)
    return out
for effect in (1.00, 0.95, 1.05):
    res = [study(effect) for _ in range(250)]
    print(f"\ntrue cost effect x{effect:.2f}:")
    for name, (keys, pmax, umax) in RULES.items():
        ok = sum(all(r[k][0] <= pmax and r[k][1] <= umax for k in keys) for r in res) / len(res)
        print(f"  P(pass) {ok:.2f}  {name}")
