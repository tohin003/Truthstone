# Changelog

All notable changes to Truthstone are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are plain `MAJOR.MINOR.PATCH`;
each release is the git tag `v<version>`, which is also where the plugins install the runtime from.

## [0.2.0] - 2026-11-14

The first public release. It is the build measured in [`docs/RESULTS.md`](docs/RESULTS.md).

### Added

- **A reminder at the first prompt of every session.** One short note to the agent: check that the
  request can be done as asked; if its requirements cannot all hold, or it needs a tool, service or
  network access the environment lacks, say what blocks it and report it as not done; if it
  relies on a setting, option, flag, variable, function, file or behaviour the project lacks, say
  so before changing any file. It is sent once per session and is silent in observe-only mode.
  `[notes] feasibility = false` in `~/.truthstone/config.toml` turns it off.
- **Checks on what a request takes for granted.** A setting, flag or variable that the request
  relies on but nothing in the project reads is noted at the prompt, judged by the name and the
  repository rather than by the wording, including the project's own configuration sections.
- **A spec note at the prompt.** When a request keeps the tests and asks for a failing test to
  pass, the documented rule closest to the request is quoted, with the honest ways out.
- **Stop checks for requests that cannot be done as asked.** A "done" is held when its own final
  message says the requirements cannot all be met, or says that what the request relies on is
  still missing. Under a request that keeps the tests, it is also held when the change rewrote an
  in-code restatement of a documented rule that the documentation still states, or when the final
  message says another party must first support or change something.
- **Sandboxed test re-runs at Stop (macOS).** In a copy of the working tree under `sandbox-exec`,
  with no network: tests the agent's run skipped behind an environment switch, and existing tests
  its run showed failing, are run again with and without the change. The "done" is held when the
  change is what broke them. Where `sandbox-exec` is not available these checks stay silent.
- **Test-pressure checks for JavaScript and TypeScript test files** now also cover changed
  helpers and top-level code in a test file.
- **Spec erosion without test pressure**: a documented rule rewritten under a request that relies
  on it is held.

### Changed

- **Hold and deny messages are self-contained.** The agent can act on a hold without opening the
  skill file, and the skill no longer invites a read at every hold.
- **Edited tests under test pressure.** An edited existing test is held only when the edit moved
  what the test checks; the check against the test's original version applies only when the
  request names the failing test. A passing test removed under test pressure is held.
- **Request gates** resolve the test a request names against the repository, whatever the wording
  around it.
- **Quieter "switch nothing reads" holds**, and honest requests for new behaviour stay silent.
- **Version scheme.** The package, the Claude Code plugin and the Codex plugin all carry `0.2.0`
  (the Codex plugin was `0.1.0-dev.0`), and both plugins install the runtime from the tag
  `v0.2.0`.

### Fixed

- A test run with part of the environment cleared that fails, followed by a plain passing run,
  no longer decides the suite: finished work is no longer held for it.
- An existing import in a test file that only gained names the file never used is no longer
  reported as weakening the test.
- Narrowings from audits of honest sessions: 16 honest sessions that a check stopped now pass,
  and two honest premise wordings are no longer flagged.
- A doc-comment sentence still in the code word for word is no longer read as a rewritten rule.

### Benchmark

- **Sealed comparison** on Codex `gpt-6.1-sol` (31 blind tasks x 3 phrasings x 2 replicates, both
  arms paired): false completions 2/138 (1.4%) guarded vs 25/138 (18.1%) unguarded; controls
  48/48 in both arms with no false block; tokens 1.01x. 7 of 8 registered targets passed; the
  registered gate reads FAIL on hook latency (T6, p95 38.3 ms against 30 ms). Details, every
  earlier sealed run and the limits: [`docs/RESULTS.md`](docs/RESULTS.md).
- **Benchmark registry** ([`docs/BENCH-golden.md`](docs/BENCH-golden.md)): three new sealed
  held-out splits (G39, G49, G51); grading policies `weakening-g36` and `weakening-g44` (a new test
  next to an existing one is an addition wherever it sits); T2 counts false blocks on controls
  only (G43); T4a's detector reads ordinary wordings (G46); the gate's rates read complete pairs
  (G37).

[0.2.0]: https://github.com/tohin003/Truthstone/releases/tag/v0.2.0
