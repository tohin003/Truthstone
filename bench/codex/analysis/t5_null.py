# ruff: noqa  (one-off evidence script for amendment G13, kept verbatim)
# Amendment G13 evidence (docs/BENCH-golden.md): the null distribution of the T5 statistic.
# Usage: .venv/bin/python bench/codex/analysis/t5_null.py <screen run>/cells.jsonl
"""Null distribution of the T5 gate statistic: split identical (observe) replicates into pseudo-arms."""
import json, random, statistics, sys
from collections import defaultdict
from truthstone.bench.codex.acceptance import _median_ratio_ci

path = sys.argv[1]
cells = [json.loads(l) for l in open(path)]
cells = [c for c in cells if c.get("arm") == "observe"]
pairs = defaultdict(list)  # (task, phrasing) -> cells
for c in cells:
    task = c["task"] if "task" in c else c["cell_id"].split(".")[0]
    phr = c.get("phrasing") or c["cell_id"].split(".")[1]
    tok = (c.get("usage") or {}).get("total_tokens")
    wall = c.get("wall_s") or (c.get("duration_ms") or 0) / 1000 or None
    pairs[(task, phr)].append((tok, wall))
pairs = {k: v for k, v in pairs.items() if len(v) == 2 and all(x[0] and x[1] for x in v)}
print("pairs with two replicates:", len(pairs), "tasks:", len({k[0] for k in pairs}))

def split(rng):
    a, b = defaultdict(lambda: {"tok": [], "wall": []}), defaultdict(lambda: {"tok": [], "wall": []})
    for (task, _), reps in pairs.items():
        x, y = (reps if rng.random() < 0.5 else reps[::-1])
        a[task]["tok"].append(x[0]); a[task]["wall"].append(x[1])
        b[task]["tok"].append(y[0]); b[task]["wall"].append(y[1])
    return a, b

def point(a, b, key):
    g = statistics.median([v for t in a for v in a[t][key]])
    o = statistics.median([v for t in b for v in b[t][key]])
    return g / o

rng = random.Random(7)
pts = {"tok": [], "wall": []}
both_le1 = both_le095 = 0
N = 4000
for _ in range(N):
    a, b = split(rng)
    pt, pw = point(a, b, "tok"), point(a, b, "wall")
    pts["tok"].append(pt); pts["wall"].append(pw)
    both_le1 += pt <= 1.0 and pw <= 1.0
    both_le095 += pt <= 0.95 and pw <= 0.95
for k in pts:
    s = sorted(pts[k])
    print(f"{k}: null point ratio 2.5/50/97.5% = {s[int(.025*N)]:.3f} / {s[N//2]:.3f} / {s[int(.975*N)]:.3f}; "
          f"P(<=1.00)={sum(x<=1.0 for x in s)/N:.2f} P(<=0.95)={sum(x<=0.95 for x in s)/N:.2f}")
print(f"P(both <=1.00)={both_le1/N:.2f}  P(both <=0.95)={both_le095/N:.2f}")
# bootstrap upper bounds as the gate computes them, for a sample of null splits
ups = {"tok": [], "wall": []}
for _ in range(150):
    a, b = split(rng)
    for key in ("tok", "wall"):
        _, up = _median_ratio_ci({t: b[t][key] for t in b}, {t: a[t][key] for t in a}, 1000)
        ups[key].append(up)
for k in ups:
    s = sorted(ups[k])
    print(f"{k}: null upper-95 bound median {s[len(s)//2]:.3f}; P(upper<=1.10)={sum(x<=1.10 for x in s)/len(s):.2f}")
