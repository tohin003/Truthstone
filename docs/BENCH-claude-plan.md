# Pre-registration draft: Truthstone's Claude Code plugin, guarded vs observe-only

Truthstone (previously named AgentGuard). Sibling of `docs/BENCH-codex-plan.md`, whose
design, oracles, statistics, voids and stop rules apply unchanged unless this document says
otherwise. **Status: draft.** The harness, the scripted dry run and the no-model preflight
are done. No live cell has run: the user decided (amendment A5 of the Codex plan) that a
golden benchmark set comes first, then the Codex study on `gpt-6.1-sol`, then this one on
`claude-opus-5-5`. The task suite, N and the per-cell cost are filled in when the golden set
is frozen and two smoke cells have measured the cost.

## 1. The comparison

Same as Codex: paired cells, same task, phrasing and replicate, back to back in a balanced
random order; the arms differ only in `observe_only` in each arm's own `TRUTHSTONE_HOME`
(its daemon on its own loopback port, never 8787, never the user's home). The agent cannot
see the difference: no environment variable, file name or path names the arm.

## 2. Driver (pinned per plan, covered by the plan digest)

```
claude -p <prompt> --output-format stream-json --verbose --include-hook-events \
  --model claude-opus-5-5 --effort <effort> --permission-mode dontAsk \
  --allowedTools Bash,Edit,Write,MultiEdit,NotebookEdit,Read,Glob,Grep,TodoWrite,Task,Agent \
  --no-session-persistence \
  --plugin-dir <build>/plugins/truthstone-claude --plugin-dir <harness logging plugin> \
  --setting-sources project --strict-mcp-config
```

- **Plugin, session-only.** `--plugin-dir` on a symlink-free copy of the build under test's
  `plugins/truthstone-claude`. It is never installed into any settings, and `--bare` is never
  used (subscription sign-in is unavailable under it). The account's own plugins, hooks,
  model defaults and MCP servers are excluded (`--setting-sources project`,
  `--strict-mcp-config`).
- **Runtime from the build, no GitHub.** `TRUTHSTONE_RUNTIME_SPEC` is the exported build (a
  local path, so an editable install) and `TRUTHSTONE_UV` the uv to install it with.
  Claude Code fixes the plugin data dir at `$CLAUDE_CONFIG_DIR/plugins/data/truthstone-inline`
  (an override is ignored), so the runtime is per account and shared by both arms, which run
  the same build. Its spec is checked before and after every cell; a change voids the cell.
- **Permissions: `dontAsk` plus the coding tools.** Every prompt becomes a refusal, so the
  guard's `ask` (review a risky command, a narrowed rewrite) is deterministically a refusal
  the model reads in the tool result: nobody is there to say yes. Under `bypassPermissions`
  it is undocumented whether a hook's `ask` still prompts. Web tools stay off (as on Codex).
- **Cells.** A fresh scratch repo under `/private/tmp/<neutral>` (outside `/Users`, so no
  ancestor `CLAUDE.md` of the user applies), with the shared protocol written to `CLAUDE.md`
  (Codex reads the same text from `AGENTS.md`). The task interpreter is a read-only venv, so
  no cell can install into another's. `TMPDIR` is per cell.
- **Binary pinned.** The study copies the (self-contained) Claude Code binary once and runs
  every cell with `DISABLE_AUTOUPDATER=1`; the version is in the plan and checked per cell.
- **Settings checked per cell.** Model from the stream's `init`; effort and permission mode
  from what Claude Code reports to the hooks (`effort.level`, `permission_mode`). Any drift
  voids the cell.

## 3. Instrument checks

- **Manipulation check, before any model call, per arm and per account.** Synthetic
  payloads through the plugin's own `hook.sh` and `forward.py`: guarded must refuse
  `git clean -fdx` (deny or ask) and hold an unverified Stop; observe-only must produce
  nothing model-visible (no decision, reason, or additional context) and must record the
  would-have hold. Passed on both accounts and both arms on the renamed build (2026-11-04).
- **Per-cell attestation.** Claude Code reports every hook run in the stream
  (`system/hook_response`, with stdout and exit code). Model-visible interventions are read
  from there: a PreToolUse deny or ask, an exit-2 block, a Stop block, a PostToolUse block,
  and any additional context (or plain stdout on SessionStart and UserPromptSubmit). Each
  kind must be matched by Truthstone decisions of that kind in the arm's own database; in
  the observe arm any of them halts the run. A `systemMessage` is shown to the developer
  only and does not count.

## 4. Accounts and usage windows

Accounts are config dirs: `work` = `~/.claude-work`, `personal` = `~/.claude-personal`. The
real `HOME` is kept, because the subscription sign-in lives in the login keychain.

- Windows are read with `claude -p /usage` (no model call) before the study, every 30
  minutes, after any usage-limit void and after any wait; between reads, each cell's own
  `rate_limit_event` (`five_hour` and `seven_day` utilisation) is the reading.
- **The 98% rule (the user's):** no cell starts on an account whose 5-hour utilisation is at
  or above 98%. The runner waits for the reset, confirms with `/usage`, and continues from
  the checkpoint.
- **Personal reserve:** no cell is scheduled on `personal` while its 5-hour window is at or
  above 70% or its weekly window at or above 85%. `work` stops at 95% weekly (adjustable;
  `work` is also claude-w's account).
- **Choice:** the eligible account with more headroom. A pair starts only on an account that
  can also start its second cell (counting the measured per-cell spend), and both cells of a
  pair run on that account; the account is recorded per cell. If the second cell may not
  start, it is not started and the pair is void (re-run, no attempt spent).
- **429 or usage limit inside a cell:** infrastructure, never an outcome; the pair is void
  and re-run. Three such voids in a row stop the session. Paid overage (`isUsingOverage`)
  halts the run (both accounts report overage as disabled today).

## 5. Budget (to be measured)

Not measured yet: the lead put live runs on hold before the two smoke cells. Readings at
12:18 IST, 2026-11-04: `personal` 5-hour 38%, weekly 40% (resets 2026-11-06 07:29); `work`
5-hour 98% (ineligible under the 98% rule), weekly 41%. A rough prior from this session's
own consumption on `personal` (an Opus session reading ~150k cached tokens per call moved the
5-hour reading about 7 points and the weekly about 1 point in 20 minutes): a medium-effort
cell of 0.3-0.6M cached input and ~5k output would cost very roughly 0.3-1 point of the
5-hour window and 0.05-0.15 of the weekly. The two smoke cells replace this before N is set;
the runner refuses a study the windows cannot finish.

## 6. Risks specific to this host

1. **Sign-in expiry.** Claude Code warned that `work`'s sign-in can end any time until
   2026-11-07 and `personal`'s between 2026-11-06 and 2026-11-09. An expired sign-in voids
   cells (auth); re-login is the user's step.
2. **Real `HOME`, no sandbox, network on.** The agent runs unsandboxed with the user's home
   readable. Mitigations: scratch repos outside `/Users`, read-only task interpreter, user
   settings excluded, web tools off. Bash can still reach the network (pip, curl), unlike
   the Codex study.
3. **Shared plugin data dir.** Another session loading the same plugin by `--plugin-dir` on
   the same account would share and could reinstall the runtime; the per-cell spec check
   voids the cell rather than letting it pass silently. Remove
   `~/.claude-{work,personal}/plugins/data/truthstone-inline` after the study (the preflight
   residue was removed on 2026-11-04).
4. **The plugin is visible in both arms** (its skills are listed), by design.
5. **`work` is claude-w's account.** Its 5-hour window was at 98% during the preflight; the
   rules simply route pairs to `personal` while that lasts.

## 7. Commands

```bash
python -m truthstone.bench.codex claude-usage                      # both accounts, the choice
python -m truthstone.bench.codex plan --host claude --name <name> --accounts work,personal \
  --model claude-opus-5-5 --effort medium --per-cell-session <measured> --per-cell-week <measured> \
  --out bench/codex/plans/<name>.json
python -m truthstone.bench.codex preflight --plan bench/codex/plans/<name>.json   # no model call
python -m truthstone.bench.codex smoke --plan bench/codex/plans/claude-smoke.json --confirm-live
python -m truthstone.bench.codex run --plan bench/codex/plans/<name>.json --confirm-live
python -m truthstone.bench.codex dry-run --host claude --run-dir <dir>   # scripted, simulated accounts
```
