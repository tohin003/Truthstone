# Final Reliability Snapshot

Measured on 2026-08-22 with Python 3.12, the local `.venv`, and the repository's official
benchmark tests. These numbers describe the current implementation, not a guarantee across
all machines.

## Latency

| Path | p50 | p95 | p99 | Result |
|---|---:|---:|---:|---|
| Read-only Guard event, in process | 0.20 ms | 0.26 ms | 0.50 ms | 385x under the 100 ms target |
| Mutating Guard event, in process | 0.59 ms | 0.67 ms | 0.81 ms | 149x under target |
| Prompt path over a real index | 2.98 ms | 3.07 ms | 3.15 ms | 163x under the 500 ms repository target |
| Indexed evidence check | 0.35 ms | 0.37 ms | 0.39 ms | 270x under the 100 ms target |
| Installed HTTP hook, end to end | 1.44 ms | 1.60 ms | 1.87 ms | 62x under target |
| Command shim fallback | 62.07 ms | 65.84 ms | 66.43 ms | within target, but much slower |

Command shim startup is why the normal installation uses HTTP hooks for per-tool events and
uses the shim only for the once-per-session daemon health/startup hooks.

Reproduce:

```bash
AGENTGUARD_HOME=/tmp/agentguard-bench .venv/bin/pytest -q tests/spec/test_s08_latency_budget.py -s
```

## Evidence Detection

> **Correction (2026-11-04, Stage 1 audit M4).** This section previously reported
> "392 of 400, 98.0% recall, 100% precision". The precision half was **vacuous**. It
> re-wrote each clean file with its own content, and the engine checks only the claims an
> edit *introduces*, so 0 claims were checked and a false positive was impossible. The
> recall sample was also self-selected: the first 400 sites in index order, 63 of them
> from one file, and no instance-attribute sites at all. The numbers below replace it.

The benchmark seeds references to members and names that do not exist, at real sites in
this repository's own source (`bench/` and `tests/fixtures/` are excluded). Sites are
drawn at random with a fixed seed, at most 5 per file. Precision is measured by a
**fresh-file replay**: each clean file's content is written as a *new* module beside it,
so every claim in it is checked. The number of claims checked is reported, and precision
is not reported at all if it is 0.

Results at commit `6ac1828` plus this change, 280 sites across 75 files:

| Kind of seeded reference | Caught | Recall |
|---|---|---|
| `Class.attr` on a class whose members are fully known | 76/76 | 100% |
| `from module import name` of a name the module does not define | 87/90 | 96.7% |
| `self.attr` inside a class whose members are fully known | 0/114 | **0%** |
| All | 163/280 | 58.2% |

**Precision: 100%.** The replay of the 75 clean files checked **3,264 claims** and
raised **0 false positives**.

The `self.attr` row is the SPEC §14 case: a method or attribute used on an instance. The
engine does not check member accesses through `self` at all. The old sample contained no
such site, which is how a 98% figure could stand.

Reproduce, on a scratch copy (the detector benchmark needs no agent and changes nothing):

```bash
AGENTGUARD_HOME="$HOME/.cache/agentguard-bench" .venv/bin/python - <<'PY'
from pathlib import Path
from agentguard.bench.mutation import run, render

print(render(run(Path.cwd(), limit=400)))
PY
```

The live `agentguard bench` harness **resets and cleans the repository it runs in**
(`git reset --hard`, `git clean -fdq`). It now refuses anything but a clean scratch copy
made for it, and refuses this source tree itself. The command documented here used to
point it at `.` with a `--task` flag that does not exist (the flag is `-t`). Use a
scratch copy:

```bash
.venv/bin/python -m agentguard.bench.runner . "$HOME/.cache/agentguard-bench/scratch"
AGENTGUARD_HOME="$HOME/.cache/agentguard-bench" .venv/bin/agentguard bench \
  --repo "$HOME/.cache/agentguard-bench/scratch" --settings .claude/settings.json \
  -t bait-asserted-method -n 1
```

## What This Proves

AgentGuard is fast enough for a hot hook path. Its repository-grounded evidence detector
catches nearly every missing member or name referenced through a fully known class or
module, and raises no false positives on 3,264 real claims. It does not check `self.attr`
member accesses, so it misses that whole kind of hallucination.

It does **not** prove that every real coding-agent session improves by the same percentage.
That requires paired live-agent control and guarded runs with the same model, prompt, and
starting repository. The shipped `agentguard bench` harness exists for that measurement.
