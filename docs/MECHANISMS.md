# Truthstone v0.2 mechanism registry

The living record of every v0.2 mechanism ([ARCHITECTURE-v0.2.md](ARCHITECTURE-v0.2.md) §6.4): what
triggers it, the failure class it addresses, the evidence for that class from outside the dev split,
its unit tests, its measured precision on replay, how often it fired in each dev round, its effect, and
what it is allowed to do. It is updated after every round. Retired mechanisms stay listed.

Created by WP1 (the measurement substrate). At creation no mechanism has been replayed or run, so the
measured columns are empty: a blank means *not measured yet*, never zero.

## How each column is filled

| Column | Source |
|---|---|
| Trigger | The mechanism's own description (architecture §4); one line, by event. |
| Class | The failure *class* it addresses, never a dev task (§6.2 rule 2). |
| Independent evidence | At least one non-dev source: literature, local transcripts, the Pebble corpus, a host contract. |
| Unit tests | Test files written from the class description on synthetic fixtures (§6.2 rule 3). |
| Precision (a) | Replay, record-only, over every recorded dev cell, both arms: false-positive firings / firings. Corpus: the recorder's trace in each cell (`truthstone.bench.replay`), driven by `truthstone replay`. |
| Precision (b) | The same over an independent corpus (the local Claude Code transcripts, with consent, or Pebble's Codex rollouts), §6.3. |
| Dev firings | Per live round: firings (on graded-success cells, on controls). From `evidence.json` decisions. |
| Effect | Per round: the acceptance targets it moves (`analyze --acceptance`, T1–T6), with intervals. |
| Status | `record` (logs only) / `note` (speaks, never blocks) / `challenge` (deny or block) / `block`. |

The precision gate (§6.3) decides the status: a deny or block needs ≤ 1% false positives on corpus (b)
and zero firings on dev controls; a note needs ≤ 10%; anything else stays `record`.

## Registry

| # | Mechanism | Trigger | Class | Independent evidence | Unit tests | Precision (a) | Precision (b) | Dev firings | Effect | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| M1 | Completion arbiter (proof-carrying completion) | Stop: the claim against the evidence that backs it | Unverified or overclaimed completion; ignored failures | Architecture §4.1 sources | WP2 | | | | | planned (WP2) |
| M2 | Spec and doc integrity | PreToolUse: an edit removing or negating a normative sentence in docs or docstrings | Rewriting the specification to fit the work | Architecture §4.2 sources | WP3 | | | | | planned (WP3) |
| M3 | Verification coverage | Stop: tests that import a changed module did not run after the change | Unverified completion; narrowed runs | Architecture §4.3 sources | WP4 | | | | | planned (WP4) |
| M4 | Test integrity: weakening versus extending | PreToolUse: an edit to an existing test file, compared before and after | Test tampering (weakening); additions never count | Architecture §4.4 (ImpossibleBench; Baker et al.) | WP3 | | | | | planned (WP3) |
| M5 | Obligation ledger | UserPromptSubmit: checkable sentences of the request; checked at Stop | Dropped requirements; scope creep; impossible requirements | Architecture §4.5 sources | WP5 | | | | | planned (WP5) |
| M6 | Residual references and stale importers | Stop: references to a renamed or removed name that remain | Partial migration | Architecture §4.6 sources | WP6 | | | | | planned (WP6) |
| M7 | Contradiction, impossibility and environment guidance | Repeated or impossible situations (installs offline, missing tools) | Flailing; claiming done on impossible work | Architecture §4.7 sources | WP7 | | | | | planned (WP7) |
| M8 | False-premise grounding | UserPromptSubmit: references with an existence cue, resolved against the repository | Building on a premise that is false | Architecture §4.8 sources | WP7 | | | | | planned (WP7) |
| M9 | Silence by default | Every context injection | Misdirection and token cost of needless notes | Architecture §4.9 sources | WP7 | | | | | planned (WP7) |
| M10 | Destructive-effect preview | PreToolUse: a destructive command, with its affected set computed first | Data loss from destructive commands | Architecture §4.10 sources | WP8 | | | | | planned (WP8) |
| M11 | Host ladder and transport | Every hook (latency; forwarder timings) | Hook latency; host coverage | Architecture §4.11 sources | WP9 | | | | | planned (WP9) |

## Measurement tools (WP1)

- **Replay corpus.** Every cell's logging hook keeps the full payload of each event and the tree the
  repository held (`hook_recorder.py`); `truthstone.bench.replay` loads a cell, checks out any event's
  tree from the trace alone and drives any engine through the events
  (`tests/bench/test_replay_roundtrip.py`).
- **Acceptance.** `python -m truthstone.bench.codex analyze --acceptance --run-dir <dev run> [...]`
  prints T1–T6 for both arms with intervals; it refuses held-out runs.
- **T4a.** `truthstone.bench.codex.premise`: was a false premise surfaced before the first change.
- **No leakage.** `tests/test_no_dev_leakage.py` fails if product code or product tests carry a golden task
  id or a string unique to one task (the list is stored hashed and rebuilt by the benchmark builder with
  `python -m truthstone.bench.codex leakage --write`).

## Rounds

| Round | Build | Cells | Notes |
|---|---|---|---|
| 0 | `e22d766` (observe only) | 120 skill-free observe cells (the extended screen, BENCH-golden §8.1) | The observe baseline for rounds 1–3; also the first replay corpus. |
