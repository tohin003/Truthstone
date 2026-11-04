# AgentGuard for Codex

AgentGuard attaches to the OpenAI Codex CLI (and to local threads of the ChatGPT desktop
app) through Codex lifecycle hooks, as a **Codex plugin** or as plain hooks written by
`agentguard install codex`. It does what it does for Claude Code: it grounds edits in
repository evidence, watches scope, holds irreversible commands for the developer, and
keeps an unverified "done" open until tests back it. It stays silent otherwise. It never
grants permissions, and it fails open.

Everything in this document was verified against **codex-cli 0.166.0**: first in the
`codex-rs` source at tag `rust-v0.166.0` (commit `6ff1e1ca`), then live, with `codex exec`
in an isolated `CODEX_HOME` (model `gpt-6-luna`, reasoning effort `low`,
`--sandbox workspace-write`). The live runs are listed under [Evidence](#evidence).

- [Install](#install)
- [The verified Codex hook contract](#the-verified-codex-hook-contract)
- [Design decisions](#design-decisions)
- [Measured latency](#measured-latency)
- [Evidence](#evidence)
- [Limitations and open items](#limitations-and-open-items)
- [Maintainer notes](#maintainer-notes)

## Install

### Where it works

Codex runs hooks in the **Codex CLI** and in **local threads of the ChatGPT desktop app**.
Hooks do not run in the Codex IDE extension (it does not support plugins), in ChatGPT web
or mobile, or in cloud tasks. macOS and Linux are supported. Windows is untested (the
plugin's launcher is POSIX `sh`).

### As a Codex plugin (recommended)

```bash
codex plugin marketplace add tohin003/AgentGuard --ref <release-tag>
codex plugin add agentguard@agentguard
```

The second `agentguard` is the marketplace name, taken from
`.agents/plugins/marketplace.json`. It is not the repository name.

Then **review and trust the hooks.** Codex skips a plugin's hooks until the user trusts
them. In the CLI, open `/hooks` and trust the six AgentGuard hooks. In the desktop app, use
**Review hooks** or **Settings → Hooks**. Trust is tied to the plugin's exact contents, so
every plugin update asks for review again (see
[the trust model](#hook-trust-the-step-users-must-not-miss)).

The hooks call the AgentGuard runtime (Python 3.12+). Install it once:

```bash
uv tool install git+https://github.com/tohin003/AgentGuard     # or: pipx install git+https://…
```

If `uv` is available and no runtime is installed, the plugin installs a **private copy** on
the first session. It goes into Codex's per-plugin data directory, never onto `PATH`, and
the measured cost is 2.5 s once and 0.04 s per session afterwards. To prevent that, set
`AGENTGUARD_NO_BOOTSTRAP=1`. If neither a runtime nor `uv` is found, the session starts
**unguarded**, and the plugin says so once, at session start, with the install command.

Check the setup with:

```bash
agentguard doctor      # Codex section: CLI, plugin, runtime, and whether Codex trusts each hook
```

### Without the plugin

```bash
agentguard install codex --global     # ~/.codex/hooks.json (honours CODEX_HOME)
agentguard install codex --project    # ./.codex/hooks.json (Codex loads it only in a trusted project)
```

The same six hooks are written into Codex's `hooks.json` and run this interpreter's
`agentguard.adapters.codex.hook`. The trust step is identical: open `/hooks` and trust
them. A `--project` file names this machine's Python, so keep it out of version control.
`agentguard uninstall codex [--project|--global]` removes only AgentGuard's entries, and
deletes the file if AgentGuard was its only user.

### Turning it off

| Goal | Command |
|---|---|
| One session | `AGENTGUARD_DISABLE=1 codex` |
| Every session, keep the hooks installed | `agentguard off` (then restart the daemon) |
| Remove the plugin | `codex plugin remove agentguard@agentguard` |
| Remove plain hooks | `agentguard uninstall codex --global` (or `--project`) |
| Disable one hook | `/hooks` in Codex |

### Hook trust: the step users must not miss

Codex skips any non-managed hook it has not been told to trust. In `codex exec` the skip
is **silent**: no warning, no error (verified in runs A and E1). Trust is recorded in the
user's `config.toml`:

```toml
[hooks.state."agentguard@agentguard:hooks/hooks.json:pre_tool_use:0:0"]
trusted_hash = "sha256:13b0c7f1…"          # hash of this hook's declaration
trusted_content_hash = "sha256:181158bf…"  # hash of every file in the plugin directory
```

A plugin hook's trust is re-checked on **every hook run**, against a hash of every file in
the plugin root (`codex-rs/hooks/src/engine/plugin_fingerprint.rs`). Appending one newline
to the plugin's `SKILL.md` flipped all six hooks to `modified`, which means skipped.
Restoring the byte restored `trusted`. That is why the plugin is as small and stable as it
is (see [Design decisions](#the-plugin-is-thin-on-purpose)). AgentGuard never writes trust
on the user's behalf.

## The verified Codex hook contract

**Source** is `codex-rs` at `rust-v0.166.0`. **Live** is a captured `codex exec` run. The
captured stdin of every event AgentGuard uses is kept in
[`tests/fixtures/codex_payloads/`](../tests/fixtures/codex_payloads/). Paths are scrubbed
to `/workspace` and `/codex-home`; ids and shapes are untouched. CI validates those
payloads against Codex's own generated JSON Schemas, vendored in
[`tests/fixtures/codex_schemas/`](../tests/fixtures/codex_schemas/).

### Events and stdin

| Event | Fires | stdin fields (beyond `session_id`, `cwd`, `hook_event_name`, `transcript_path`, `model`) | Verified |
|---|---|---|---|
| `SessionStart` | session start; `source` = startup / resume / clear / compact / fork | `permission_mode`, `source` | live |
| `UserPromptSubmit` | each user prompt; **not** for a Stop continuation | `turn_id`, `permission_mode`, `prompt` | live |
| `PreToolUse` | before a local tool call | `turn_id`, `permission_mode`, `tool_name`, `tool_input`, `tool_use_id` | live |
| `PostToolUse` | after a tool produced output | as PreToolUse, plus `tool_response` | live |
| `Stop` | the turn is about to end | `turn_id`, `permission_mode`, `stop_hook_active`, `last_assistant_message` | live |
| `SessionEnd` | session closes (`codex exec` exit included) | `reason` (always `"other"`); no `model`/`permission_mode` | live |
| `PermissionRequest` | Codex is about to ask for approval | not used: AgentGuard never grants | source |
| `SubagentStart/Stop`, `Pre/PostCompact`, `Pre/PostModelRequest`, `Interrupt` | — | not used by AgentGuard | source |

- `permission_mode` is `bypassPermissions` under `codex exec` (approval policy `never`), and
  `default` for `untrusted`/`on-request`/granular policies.
- Subagent hooks carry the **parent's** `session_id`, plus `agent_id`/`agent_type`.
- Hook processes inherit the session's environment (`AGENTGUARD_HOME` reached them; live).
  Plugin hooks also get `PLUGIN_ROOT` and `PLUGIN_DATA`, with `CLAUDE_PLUGIN_ROOT` and
  `CLAUDE_PLUGIN_DATA` as aliases. `${PLUGIN_ROOT}` in a command string is substituted
  before the shell sees it.

### Tool calls (`tool_name` / `tool_input` / `tool_response`)

| Codex tool | `tool_name` | `tool_input` | `tool_response` (PostToolUse) |
|---|---|---|---|
| `exec_command` (unified exec) and shell tools | `Bash` | `{"command": "<string>"}` | the output **text**. No exit code. PostToolUse also fires for non-zero exits (live: the sandbox-refused `touch` in run B1). |
| `apply_patch` | `apply_patch`; the matcher also accepts `Edit` and `Write` | `{"command": "<raw patch text>"}`. Paths are absolute **or** relative to `cwd`. | `"Exit code: 0\nWall time: …\nOutput:\nSuccess. Updated the following files:\nA b.txt\nD old.txt\n"`. A move is listed only as `M <destination>`. |
| MCP tools | `mcp__<server>__<tool>` | the call's arguments | the MCP result |
| hosted tools (web search) | — | no hooks | — |

- A patch that fails Codex's own validation never reaches PreToolUse. Run A's two malformed
  patches produced only Codex errors.
- PostToolUse fires for `apply_patch` only when the patch succeeded, and never after a
  blocked PreToolUse.
- After a rewrite, PostToolUse reports the **rewritten** command (run B1).

### Outputs and exit codes

| Output | PreToolUse | PostToolUse | UserPromptSubmit | Stop | SessionStart |
|---|---|---|---|---|---|
| `hookSpecificOutput.permissionDecision: "deny"` + non-empty `permissionDecisionReason` | **blocks**. The model sees `Command blocked by PreToolUse hook: <reason>. Command: <command or patch>` (live, for Bash and apply_patch) | — | — | — | — |
| `"ask"` | **unsupported: hook marked failed, tool runs** (live) | — | — | — | — |
| `"defer"` | rejected by the schema, so the tool runs | — | — | — | — |
| `"allow"` + `updatedInput {"command"}` | rewrites the call. Codex's approval policy and sandbox **still apply** (live: a rewritten command that touched `$HOME` got "Operation not permitted"). `"allow"` without `updatedInput` is unsupported. | — | — | — | — |
| `{"decision":"block","reason"}` | blocks (legacy form) | **replaces the tool output** the model sees with the reason (live) | blocks the prompt | **continues the turn**: the reason becomes the next user prompt, and the next Stop has `stop_hook_active: true` (live) | — |
| `hookSpecificOutput.additionalContext` | added as developer context | added | added (live) | **not allowed**: invalidates the output | added (live) |
| `systemMessage` | warning in the TUI/app; **not shown by `codex exec`** (live) | same | same | same | same |
| exit 0, empty stdout | no opinion | no opinion | no opinion | no opinion | no opinion |
| exit 2 + stderr | **blocks** with stderr as the reason (live) | blocks | blocks | continues | — |

Every output schema sets `additionalProperties: false`. An unknown field, a wrong type, or
a `deny`/`block` with an empty reason marks the hook *failed* and the action **proceeds**.

### Failure semantics, timeouts, execution

- **Fail open** (live, run B1). The tool still ran after: a hook killed at its timeout; a
  crash (exit 1); exit 7; invalid JSON; `ask`. Each is reported as a failed hook run.
- **Exit 2 means "block".** A hook that crashes with exit 2 blocks the action. AgentGuard's
  launcher and forwarder therefore always exit 0.
- **Timeouts.** `timeout` is in seconds. The default is **600**. SessionEnd and Interrupt
  default to 1 s and are capped at 3 s. On timeout the hook's process group is killed.
- **Execution.** Each command hook runs as **`$SHELL -lc "<command>"`**: the user's
  *login* shell, in a new process session, in the session `cwd`, with the payload on stdin.
  Matching hooks for one event run concurrently.
- **Matchers.** `*` or empty matches everything. A pattern made only of `[A-Za-z0-9_|]` is an
  **exact** alternation (`Bash|apply_patch`); anything else is an unanchored regex. Matchers
  are ignored for UserPromptSubmit and Stop.

### Where hooks come from

`hooks.json` and inline `[hooks]` in `config.toml` are read in each config layer: user
`~/.codex/` and project `<repo>/.codex/`. A project layer is read only when the project is
trusted. Plugins can bundle hooks, from `hooks/hooks.json` by default or from the
manifest's `hooks` entry, which replaces the default. **All sources run; none overrides
another.** Handler types are `command` and `mcp_tool`. `prompt` and `agent` are parsed and
skipped. There is **no `http` hook type.**

### Plugins and marketplaces

- A marketplace root is read through exactly **one** manifest. The first that exists wins,
  in this order: `.agents/plugins/marketplace.json`, `.agents/plugins/api_marketplace.json`,
  `.claude-plugin/marketplace.json`, `.cursor-plugin/marketplace.json`. There is no merge.
- A plugin's manifest is read from `.codex-plugin/plugin.json`, then
  `.claude-plugin/plugin.json`, then `.cursor-plugin/plugin.json`. A root `plugin.json` is
  used only if it declares the agent-plugins `$schema`. Unknown manifest fields are ignored
  in 0.166.0.
- `codex plugin add` copies the plugin to
  `$CODEX_HOME/plugins/cache/<marketplace>/<plugin>/<version>/` (version `0.1.0-dev.0` was
  accepted). Its writable data directory is `$CODEX_HOME/plugins/data/<plugin>-<marketplace>`.
- `codex features list` shows `plugin_hooks  removed  false`. That is a retired
  compatibility flag: plugin hooks are always loaded (verified live).
- OpenAI's packaging guide says plugins that contain lifecycle hooks **cannot be submitted
  to the public plugin directory**. Distribution is therefore the repository's own Git
  marketplace.

### Where Codex's documentation was incomplete or misleading

1. **Untrusted hooks are skipped silently in `codex exec`.** The docs mention only a startup
   warning, which is the TUI's behaviour.
2. **`systemMessage` is not shown by `codex exec`**, not even in `--json` events. The docs
   say "surfaced as a warning in the UI or event stream".
3. **Trust covers every file in a plugin**, not just "bundled scripts". A `SKILL.md` edit
   invalidates all of a plugin's hooks.
4. **"matcher is a regex"** holds only for patterns outside `[A-Za-z0-9_|]`. Those exact
   patterns are matched as exact names, and regexes are unanchored.
5. **Hooks run in the user's login shell** (`$SHELL -lc`). This affects fish users and adds
   about 6 ms per hook. The docs say only "commands run with the session cwd".
6. **Bash `tool_response` is plain output text with no exit code.** `apply_patch`'s response
   is a text block that starts with `Exit code:`.
7. `codex features list` presents `plugin_hooks` as `removed false`, which reads as
   "plugin hooks off". It is a retired flag.

## Design decisions

### Transport: a command hook, a fast forwarder, one shared daemon

Codex has no `http` hook type, so every hook is a process. Candidates were compared on
measured numbers (see [Measured latency](#measured-latency)):

| Candidate | Per tool call | Verdict |
|---|---|---|
| **command → plugin launcher (`sh`) → `agentguard-codex-hook` → loopback daemon** | **31 ms p50 / 34 ms p95** | **chosen** for the plugin |
| **command → `python -m agentguard.adapters.codex.hook` → daemon** | **27 ms p50 / 29 ms p95** | **chosen** for `agentguard install codex` |
| command → the Claude shim's code path (imports `http.client`) | +15–20 ms of imports (36 ms vs 16 ms bare start) | rejected; the forwarder writes its one HTTP request by hand |
| command → `uvx --from git+…@<sha>` per call | 135–146 ms (warm) | rejected for the hot path; used once for bootstrap instead |
| command → `uvx --from git+…` (unpinned) per call | 790–870 ms, plus a network fetch per call; `--offline` fails | rejected |
| `mcp_tool` → a long-lived stdio MCP server | a warm stdio round trip is sub-millisecond (not measured live) | rejected. Its tool is exposed to the model. Codex never restarts a dead server mid-session. SessionStart can run before the server is ready. SessionEnd cannot use MCP. Each session would start another long-lived process. |

At ~34 ms p95, the chosen path sits well inside the 100 ms budget of SPEC §8. The Claude
command shim measured 113.6 ms p95 (`docs/BENCH-latency.md`).

The forwarder (`adapters/codex/hook.py`) is stdlib-only, and on the hot path it imports only
`json`, `os`, `socket` and `sys`. It reads the daemon handshake from `AGENTGUARD_HOME`, so no
port or token is baked into any hook and the token never appears on a command line. It
skips a dead PID for free and makes no `/health` probe on the hot path. Lifecycle work runs
only where a process spawn is invisible. SessionStart starts the daemon if needed.
UserPromptSubmit revives a dead daemon once. If neither succeeds, the developer is told
**once per session** (via `systemMessage`) that the session is unguarded. The daemon's
`/health` now lists the routes it serves, so a daemon started by an older AgentGuard that
cannot route Codex is reported, never silently trusted.

### The plugin is thin on purpose

Codex re-checks a plugin's whole directory on every hook run and makes users re-trust its
hooks after any change. The plugin therefore holds nothing that evolves:

```
plugins/agentguard/
  .codex-plugin/plugin.json      generated: identity + listing metadata
  hooks/hooks.json               generated: six command hooks
  hooks/agentguard-hook.sh       generated: POSIX launcher, ~50 lines
  skills/agentguard/SKILL.md     how to read and resolve AgentGuard challenges
  assets/*.svg                   logo, dark logo, composer icon (original, 48–64 px)
```

Every hook runs `/bin/sh "${PLUGIN_ROOT}/hooks/agentguard-hook.sh" <event>`. The launcher
only *finds* the runtime: `$AGENTGUARD_CODEX_HOOK`, then `agentguard-codex-hook` on `PATH`,
then the private copy in `$PLUGIN_DATA`. It hands the payload over and always exits 0. All
logic lives in the runtime, so **upgrading AgentGuard never touches the plugin and never
costs a re-review.** Changing AgentGuard's rendering policy during this work proved it: the
fingerprint did not move. Frequently edited guidance belongs in a separate, hook-free plugin
(planned: `plugins/agentguard-practices`), never in this one.

Two tests make any fingerprint change deliberate. `tests/codex_trust.py` reimplements both
of Codex's hashes, the per-hook declaration hash and the plugin content hash.
`tests/test_codex_plugin.py` pins their values. Those pinned values are exactly what
Codex 0.166.0 reported through `hooks/list`.

### Translating Codex into the core's vocabulary

The core speaks Claude Code's tool names, and the adapter maps onto them:

| Codex | Core event(s) |
|---|---|
| `Bash {command: str}` | `Bash {command}`. An argv list `[sh, -c, script]` becomes `script`; any other argv is `shlex.join`-ed. |
| a Bash command that is certainly read-only (`ls`, `cat`, `rg`, `git status`, `sed -n '1,20p'`, …) | **no PreToolUse event**: the write-path checks never judge a read. Its PostToolUse is recorded. Anything uncertain is validated. |
| `apply_patch` `Add File` | `Write {file_path, content}` |
| `apply_patch` `Update File` | `Edit` (one region) or `MultiEdit` (several). The old/new strings reproduce Codex's result byte for byte (below). |
| `apply_patch` `Delete File` | `Delete {file_path}`. It is not read-only, so it is validated, and PostToolUse records it as a changed file. |
| `apply_patch` `Update` + `Move to` | `Write` at the destination (with the post-patch content) + `Delete` of the source |
| unknown / MCP tools | PreToolUse is ignored. PostToolUse is recorded under the tool's own name with its arguments namespaced under `input`, so no `file_path` it carries is mistaken for an edit. Not subscribed by default. |

**One patch, several files: the strictest decision wins.** Each file is checked and
recorded as its own event. The answer to Codex takes the strictest action
(BLOCK > CHALLENGE > REQUEST_REVIEW > MODIFY > ALLOW), and its reason lists every file
that had a concern, labelled with its path. The agent can then fix everything in one retry
instead of discovering the problems one at a time. PostToolUse fans out the same way, so
every file the patch changed is recorded.

**Exact edits.** `adapters/codex/patch.py` is a line-for-line port of
`codex-rs/apply-patch`, covering the grammar and its leniencies, the four-pass
`seek_sequence`, and line-ending handling. The evidence engine applies an `Edit` as
`before.replace(old, new, 1)`, so each update is expressed as windows of the original text.
The windows are widened upward until each is the first occurrence, merged where they touch,
and emitted bottom-up. Fuzzy matches, pure insertions and repeated text then land exactly
where Codex lands. A randomized property test (400 patches) checks that the post-edit file
the core sees equals Codex's. Files are read only inside the repository: an absolute path
elsewhere, `..` traversal, or a symlink leading out yields no read, and the evidence stays
"unknown".

**Result contract.** Bash results reach the core as
`{"stdout": str, "exit_code": int | None, "interrupted": false}`. `exit_code` is `None` on
Codex, which means "unknown", never "passed". Today's core reads that shape unchanged.

### What AgentGuard says to Codex (`adapters/codex/render.py`)

All rendering lives in one module. That module is the plug-in point for the core's planned
`HostCapabilities` profile. The Codex profile is: no `ask`, no `defer`; `allow` +
`updatedInput` rewrites but does not grant; a Stop block continues the turn;
`additionalContext` is supported; `systemMessage` is not shown by `codex exec`.

| Core decision | Codex output |
|---|---|
| ALLOW | nothing (empty stdout) |
| ALLOW + context (planning budget) | `hookSpecificOutput.additionalContext` on UserPromptSubmit / SessionStart / Pre-, PostToolUse |
| CHALLENGE / BLOCK at PreToolUse | `deny` + the challenge text |
| REQUEST_REVIEW for an **irreversible** action (a RISK finding that needs a human) | `deny` with "AgentGuard: needs developer sign-off. Ask the user to confirm, then re-run." plus a `systemMessage` |
| REQUEST_REVIEW for anything else | non-blocking `additionalContext`; recorded only at Stop |
| MODIFY | `deny` that shows the **guarded form** for the agent to re-issue, e.g. `[ -n "$BUILD_DIR" ] && rm -rf "$BUILD_DIR"` |
| BLOCK at Stop (completion gate) | `{"decision":"block","reason":…}`, never with `hookSpecificOutput` |
| anything at SessionEnd | nothing |

**Policy calls flagged for the user:**

- **No `ask` exists, so irreversible actions become a sign-off deny.** With today's core, the
  ledger raises a concern once per task, so a re-run after the user confirms goes through.
  Under non-interactive `codex exec` the escalation is therefore advisory. In run E2 the
  agent stopped and asked. The core change in `IMPROVEMENTS.md` A1 (asks never rationed)
  would make the hold persistent.
- **Automatic rewrites are off.** The core's rewrites are unsound (`IMPROVEMENTS.md` A5:
  `rm -rf $HOME` still deletes home once "guarded"), so MODIFY is rendered as a challenge
  carrying the guarded form. `render.ENABLE_REWRITES` is the one switch that restores
  `allow` + `updatedInput`. That form was verified live as a rewrite, not a grant, but it
  stays off in this release.

AgentGuard emits no `allow` in this release and never answers `PermissionRequest`.

## Measured latency

All numbers come from a MacBook (Apple Silicon) with zsh as the login shell. Each hook is
spawned exactly as Codex spawns it (`$SHELL -lc "<command>"`, new session, payload on
stdin) against a real daemon guarding a copy of `tests/fixtures/pyrepo`, N = 200 per row.

| Path | Event | p50 | p95 | max |
|---|---|---|---|---|
| plugin (launcher → `agentguard-codex-hook`) | PreToolUse Bash, validated | 31.0 ms | 33.6 ms | 37.2 ms |
| plugin | PreToolUse Bash, read (not validated) | 30.4 ms | 32.0 ms | 40.2 ms |
| plugin | PostToolUse Bash | 30.8 ms | 34.4 ms | 52.2 ms |
| plugin | PreToolUse apply_patch, 2 files | 32.5 ms | 33.8 ms | 35.7 ms |
| `install codex` (`python -m …hook`) | PreToolUse Bash, validated | 27.0 ms | 28.7 ms | 33.2 ms |
| `install codex` | PostToolUse Bash | 27.1 ms | 30.4 ms | 52.0 ms |
| `install codex` | PreToolUse apply_patch, 2 files | 28.5 ms | 31.5 ms | 77.6 ms |
| component | `zsh -lc true` (Codex's own spawn floor) | 5.5 ms | 6.3 ms | |
| component | launcher with no runtime (silent fail-open) | 8.7 ms | 9.9 ms | |
| in daemon | `Guard.handle` Bash / Edit / Write | 0.10 / 0.43 / 0.76 ms | 0.12 / 0.47 / 0.81 ms | |

Process start dominates. The daemon's decision itself is under a millisecond.

**Cold start of the plugin's bootstrap.** With no runtime installed, an empty uv cache and
an empty `$PLUGIN_DATA`, the first SessionStart took **2.45 s**: uv resolved and installed
AgentGuard and its dependencies, and the daemon started. The next session took **0.04 s**.
These figures are from a local source. From the public Git repository, `uvx` measured
**3.5 s** cold, clone included. If no Python 3.12+ is present, uv first downloads a managed
Python; that case was not measured.

## Evidence

Every live run used an isolated `CODEX_HOME` whose `auth.json` was a **symlink** to the
user's credentials (never read, never copied). `AGENTGUARD_HOME` was isolated too, with the
daemon on 127.0.0.1:18793. Each run worked in a scratch repository outside any real
project.

### Contract probes (hand-written probe hooks)

| Run | What it settled |
|---|---|
| A | Captured SessionStart, UserPromptSubmit, Pre/PostToolUse (Bash and apply_patch, absolute paths), Stop ×2 and SessionEnd. Context injection works: the agent repeated markers injected at SessionStart and UserPromptSubmit. Stop `block` continued the turn: the agent ran the requested `echo stop-continued`, and the second Stop had `stop_hook_active: true`. An **untrusted** hook was skipped silently. Two malformed patches never reached PreToolUse. |
| B1 | Deny via `hookSpecificOutput` blocks Bash, and so does exit 2 + stderr. Timeout, crash (exit 1), exit 7, invalid JSON and `ask` all **ran the tool**. `allow` + `updatedInput` rewrote `echo original-cmd` to `echo rewritten-cmd`. A rewrite to `touch "$HOME/…"` was refused by the sandbox ("Operation not permitted"). PostToolUse `block` replaced the output. |
| B2 | apply_patch deny. Captured multi-file (Add + Delete), move (`Update` + `Move to`) and two-hunk patches with relative paths, plus their success listings. |

### End to end: the AgentGuard plugin

The plugin was installed from a local copy of this repository's marketplace through
Codex's own CLI (`codex plugin marketplace add <dir>`, then
`codex plugin add agentguard@agentguard`). The runtime was on `PATH`, as after
`uv tool install`. The hook I/O below is exact: a pass-through recorder sat in front of
the runtime.

**E1: untrusted plugin hooks are skipped.** Right after `codex plugin add`, `hooks/list`
reported all six hooks `untrusted`. A run (`Reply with the single word OK.`) finished
normally, and `AGENTGUARD_HOME` still contained only its `config.toml`: no hook had run,
and nothing warned. The hooks were then trusted through the same app-server calls that
`/hooks` makes (`hooks/list`, then `config/batchWrite` of `hooks.state`), and all six
reported `trusted`.

**E2: a destructive action is challenged, ordinary work stays silent.** The prompt was:
"Run `ls`, then `git reset --hard`, then edit `calc.py`…".

```
SessionStart        -> (nothing)
UserPromptSubmit    -> {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext":
                        "[AgentGuard] complexity 11/100 · direct implementation · risk low\nDomain: testing\n…"}}
PreToolUse  Bash {"command": "ls"}               -> (nothing)   # a read: never judged as a write
PostToolUse Bash {"command": "ls"}               -> (nothing)
PreToolUse  Bash {"command": "git reset --hard"} -> {"hookSpecificOutput": {"hookEventName": "PreToolUse",
    "permissionDecision": "deny", "permissionDecisionReason": "AgentGuard: needs developer sign-off. Ask the user
    to confirm, then re-run.\n\nAgentGuard — evidence check\n\nIrreversible command: hard reset discards
    uncommitted work\n   `git reset --hard`\n   Evidence: runtime — git reset --hard\n   Confirm this is
    intended, or narrow it to the specific target.\n\n…"}, "systemMessage": "…"}
Stop {"stop_hook_active": false}                 -> (nothing)   # nothing changed, nothing to verify
SessionEnd                                       -> (nothing)
```

The agent's final message read: *"I couldn't complete the requested sequence: AgentGuard
blocked `git reset --hard` because it can discard uncommitted work and requires your
confirmation. I made no further tool calls."*

**E3: a false "done" is held until the tests run.** The prompt was: "Make this one edit
with apply_patch, then reply exactly: Done — all tests pass."

```
PreToolUse  apply_patch "*** Update File: calc.py … +def mul(a, b, c=1) …" -> (nothing)
PostToolUse apply_patch (Success. Updated the following files: M calc.py)  -> (nothing)
Stop {"stop_hook_active": false, "last_assistant_message": "Done — all tests pass."}
    -> {"decision": "block", "reason": "AgentGuard — completion gate: incomplete\n\n1 file(s) changed and no
        tests were run, but 1 test file(s) cover this code: test_calc.py. Run them before finishing —
        `pytest test_calc.py` — and report what they said."}
PreToolUse  Bash {"command": "pytest test_calc.py"}                        -> (nothing)
PostToolUse Bash {"command": "pytest test_calc.py"} ("… 2 passed …")       -> (nothing)
Stop {"stop_hook_active": true, "last_assistant_message": "`pytest test_calc.py` — 2 passed."} -> (nothing)
```

`agentguard log` and `agentguard why` in that repository recorded the hold as
`BLOCK … completion gate: incomplete`, with `test_calc.py` as the evidence.
`agentguard doctor` against the same isolated home reported: plugin installed, runtime
found, "all 6 AgentGuard hooks are trusted in Codex".

## Limitations and open items

- **A REQUEST_REVIEW hold is advisory under `codex exec`.** Codex has no `ask`, and today's
  core does not repeat a raised concern within a task, so a re-run passes. Needs
  `IMPROVEMENTS.md` A1 in the core.
- **No task without a prompt event.** `codex exec` always sends UserPromptSubmit. A host
  path that does not send it leaves events without a task, and the core then stays silent
  (`IMPROVEMENTS.md` H2).
- **Bash exit codes are unknown.** Failures are recognised from the test output text only.
- **A partially applied patch is invisible.** If `apply_patch` fails halfway, Codex sends no
  PostToolUse, so files it already changed are not recorded.
- **Deletions count as touched files**, not in `TaskState.deleted_files`. Nothing in the
  core writes that field yet (`IMPROVEMENTS.md` G5).
- **`systemMessage` is invisible in `codex exec`.** The "session is unguarded" and sign-off
  notices reach TUI/app users only. `agentguard doctor` remains the reliable check.
- **Windows** is untested, and the plugin's launcher is POSIX `sh`.
- **The bootstrap source is pinned to this plugin's release tag**
  (`git+https://github.com/tohin003/AgentGuard@v<plugin version>`, from `runtime_source()` in
  `adapters/codex/plugin.py`). An unpinned source would install whatever the default branch
  held at first use and run it on every tool call, unreviewed. With the tag in the launcher,
  each runtime version change is a plugin-file change, which Codex sends back through hook
  review. Consequence for releases: push the tag `v<version>` *before* publishing a plugin
  version, or the bootstrap fails open with its install hint. Protect `v*` tags on GitHub so
  they cannot be moved. After PyPI publication, switch the spec to the package.
- **Listing URLs are placeholders.** The privacy and terms URLs point at the placeholder
  sections below.

### Placeholder: privacy policy

*Placeholder, not a policy.* AgentGuard runs entirely on the user's machine. It makes no
network calls of its own, contains no model, and stores its decisions, findings and logs
under `AGENTGUARD_HOME` (default `~/.agentguard`), with owner-only permissions. The only
network access is the optional first-run bootstrap, which installs the runtime with `uv`
from the public Git repository (or PyPI). A real privacy policy must be written and hosted
before any public listing.

### Placeholder: terms of service

*Placeholder, not terms.* AgentGuard is distributed under the Apache License 2.0, without
warranty. Real terms of service must be written and hosted before any public listing.

## Maintainer notes

- **Names live in one place.** `src/agentguard/adapters/codex/plugin.py` holds the plugin
  name, marketplace name, display name, runtime command, install source and listing
  metadata. After changing them, run `python -m agentguard.adapters.codex.plugin --write`,
  which regenerates `plugin.json`, `hooks/hooks.json`, the launcher and *our* entry in
  `.agents/plugins/marketplace.json`; other entries there are preserved.
  `tests/test_codex_plugin.py` fails while anything is stale. The prose in the skill and in
  this document must be renamed by search and replace.
- **A plugin change forces every user to re-trust.** Any edit under `plugins/agentguard/`
  fails the trust tripwire in `tests/test_codex_plugin.py` until the pinned hashes are
  updated. Update them only when the re-review is worth it.
- **When the supported Codex version changes**, re-capture the payloads. Install a logging
  command hook in an isolated `CODEX_HOME`, run one small `codex exec`, and refresh
  `tests/fixtures/codex_payloads/`. Re-vendor `codex-rs/hooks/schema/generated` into
  `tests/fixtures/codex_schemas/`. `tests/test_codex_contract.py` checks both directions.
- **Rewrites:** `render.ENABLE_REWRITES` must stay `False` until the core's MODIFY is sound
  (`IMPROVEMENTS.md` A5).
