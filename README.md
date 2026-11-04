# Truthstone (previously named AgentGuard)

**A reliability and reasoning control layer for AI coding agents.**

Truthstone attaches to an existing coding agent — Claude Code today, with an adapter path for
Cursor, Codex, and custom agents —
and makes that agent's mistakes hard to execute. It does not replace the agent, and it does
not contain an LLM of its own.

> The host provides intelligence. Truthstone provides discipline.

<!-- rename-tool: keep-begin renamed-note -->
## Renamed from AgentGuard

Truthstone was previously named AgentGuard. Installs made under the old name keep
working:

- **Settings.** Every `AGENTGUARD_*` environment variable still applies when its
  `TRUTHSTONE_*` counterpart is unset (`AGENTGUARD_HOME`, `AGENTGUARD_DISABLE`, `AGENTGUARD_OBSERVE`).
- **Data.** An existing `~/.agentguard` directory stays in use until `~/.truthstone`
  exists; `truthstone doctor` prints the command that moves it.
- **Hooks.** Hooks written by `agentguard install` are recognised:
  `truthstone install` replaces them and `truthstone uninstall` removes them, so nothing
  runs twice.
- **Names.** The package, the commands and the plugins carry the new name
  (`truthstone`, `truthstone-hook`, ...). Remove a plugin installed under the old name
  and add the new one.
<!-- rename-tool: keep-end -->

## What it does

| | |
|---|---|
| **Grounds claims in evidence** | The agent says it will call `UserRepository.get_active_users()`. Truthstone asks the repository whether that exists. If it doesn't, the agent is challenged with the file as evidence. |
| **Sizes planning to the task** | "Rename `getUser`" stays three steps. "Introduce distributed session caching" is *allowed* to become a deep architectural investigation. Truthstone is a proportionality system, not an anti-complexity system. |
| **Watches scope** | "Fix login validation" that starts editing 17 unrelated files gets challenged. |
| **Refuses to rubber-stamp "Done"** | Completion is a claim like any other, and has to be backed by tests that actually ran. |
| **Stays quiet** | Deterministic checks on the hot path, sub-100ms, no output. Like ABS: invisible until it isn't. |

## What it is not

It has no LLM. When a judgement needs real reasoning, Truthstone doesn't think — it hands
the problem back to the host agent as a challenge, and the host's own intelligence resolves
it. That is the entire architecture: **bring your own brain**.

It also never grants permissions. It can stay silent, object, or escalate to you — but it
will not approve something on your behalf.

## Status

The Claude Code integration is usable today, with deterministic evidence checks, proportional
planning, scope validation, verified completion, local telemetry, and hardened fail-open daemon
lifecycle. Current measured performance and detector coverage are in
[`docs/BENCH-final.md`](docs/BENCH-final.md). See [`PROGRESS.md`](PROGRESS.md) for phase detail.

## Install (development)

### Requirements

- Python 3.12 or newer
- Git (used for repository evidence when the project is a Git checkout)
- Claude Code with hooks enabled
- `uv` is recommended for installation, but the package can also be installed with any
  Python packaging workflow that supports editable installs

Put `truthstone` on your PATH. `--editable` means it tracks this source tree, so changes
take effect without reinstalling:

```bash
uv tool install --editable /path/to/Truthstone
```

Then, **from the repository you want guarded**:

```bash
cd /path/to/your-project
truthstone install claude --project   # -> ./.claude/settings.local.json (gitignored)
truthstone daemon start               # optional: SessionStart does this too
truthstone doctor                     # confirm everything is wired
```

`--project` attaches Truthstone to that repository only. Use `--global` instead to attach
to every project, which writes to `~/.claude/settings.json`.

Running it as `uv run truthstone …` only works from inside this repository, because that
form uses the project's own virtualenv.

### First Use

1. Install the hooks from the repository you want to protect.
2. Run `truthstone doctor` and fix any reported configuration or port conflict.
3. Start Claude Code in that repository. `SessionStart` starts the local daemon when needed;
   `truthstone daemon start` is useful when you want to start it before opening Claude.
4. Work normally. Truthstone is silent for ordinary safe events and returns a challenge,
   review request, narrowed input, or completion-gate hold only when its deterministic checks
   find something worth surfacing.

For a global installation, replace `--project` with `--global`. Project installation writes
`.claude/settings.local.json`; global installation writes `~/.claude/settings.json`. The
installer is idempotent and removes only hooks marked as Truthstone-owned.

Truthstone's daemon is deliberately bound to IPv4 loopback (`127.0.0.1`) and authenticates
each hook with a local bearer token. Its database, token, handshake, lifecycle markers and
logs are kept under `TRUTHSTONE_HOME` (default `~/.truthstone`) with owner-only permissions.
The daemon does not accept remote connections. If the config file is malformed or contains
an unsafe value, hooks use safe defaults and `truthstone doctor` reports the configuration
problem so it can be corrected rather than silently running with an unexpected setup.

### Turning it off

```bash
truthstone off                  # stays installed, decides nothing
truthstone on
TRUTHSTONE_DISABLE=1 claude     # off for one session
truthstone uninstall claude --project   # remove the hooks entirely
```

`uninstall` removes only what Truthstone added; any hooks you wrote yourself are left
alone.

`off` and `on` change the persisted setting and take effect after the daemon is restarted.
For a one-session switch, use `TRUTHSTONE_DISABLE=1 claude`. To remove the integration
entirely, run `truthstone uninstall claude --project` (or `--global`).

### Daily Commands

```bash
truthstone doctor                 # installation, daemon, storage, and port checks
truthstone daemon status          # whether the authenticated daemon is answering
truthstone daemon start           # start it in the background
truthstone daemon stop            # stop it safely
truthstone log -n 20              # recent decisions and latency
truthstone why <decision-id>      # findings and evidence behind one decision
truthstone report -d 7            # project observations over the last week
truthstone db stats               # database size, retention, and disk state
```

Repository inspection is available without starting Claude:

```bash
truthstone index                  # build and summarize the repository index
truthstone find-symbol UserRepository
truthstone explain src/app.py
```

`truthstone doctor` is the first diagnostic to run. It checks Python/Git, safe daemon
configuration, private storage, hook installation, and whether the loopback port is occupied
by another process. The daemon listens only on `127.0.0.1` and authenticates hook requests
with a local bearer token.

### Seeing what it did

```bash
truthstone log            # recent decisions
truthstone why <id>       # the evidence behind one decision
truthstone db stats       # what is stored, and how much room is left
```

### Observe-only, and the failure-mode census

Truthstone can run as a pure sensor: every check still runs and every finding is still
recorded, but nothing reaches the agent — no challenges, no completion gate, not even the
injected planning budget.

```bash
truthstone observe on     # record everything, say nothing
# ... a week of ordinary work ...
truthstone census         # which of SPEC §3's 17 failure modes actually occurred
truthstone observe off
```

This exists because the benchmark found that the failure Truthstone was best at detecting —
hallucinated references — is one current models essentially no longer commit. Rather than
guess again at which failure to target, the census counts. **While observe-only is on,
Truthstone guards nothing**; that is the price of measuring an unguarded agent. Method and
caveats: [`docs/CENSUS.md`](docs/CENSUS.md). The historical detector study is
[`docs/BENCH-mutation.md`](docs/BENCH-mutation.md); the current release snapshot is
[`docs/BENCH-final.md`](docs/BENCH-final.md).

### Configuration And Data

Truthstone stores its shared SQLite database, token, handshake, logs, and lifecycle files
under `TRUTHSTONE_HOME` (default `~/.truthstone`). Files are created with owner-only
permissions. Set `TRUTHSTONE_HOME` to an isolated directory for tests or a separate local
profile. `TRUTHSTONE_DISABLE=1` disables all decisions for one process; `TRUTHSTONE_OBSERVE=1`
runs the engines but suppresses everything sent back to the agent.

The daemon defaults to `127.0.0.1:8787`, which is embedded in the installed hook URL. If that
port is occupied, set a different loopback port in `~/.truthstone/config.toml` and reinstall
the hooks so the URL and daemon agree:

```toml
[daemon]
host = "127.0.0.1"
port = 8790
```

Do not bind the daemon to a network interface. Truthstone is designed as a local control
layer, not a remotely exposed service.

### What It Can And Cannot Prove

Truthstone can ground repository claims, challenge risky or out-of-scope actions, and stop a
false completion claim when the available evidence is insufficient. It does not contain an
LLM and does not replace the host agent's reasoning. Unknown or unsupported evidence is
treated conservatively as unknown, not as proof of failure.

The current final measurements are in [`docs/BENCH-final.md`](docs/BENCH-final.md): the
installed HTTP hook measured 1.60 ms p95, and the repository mutation benchmark reached
98.0% recall with 100% precision on 400 seeded nonexistent references. These are detector and
latency measurements, not a causal guarantee for every real agent session. A paired live
control/guarded run is required to measure outcome improvement.

## Frequently Asked Questions

### When is Truthstone useful in everyday agent work?

Truthstone is most useful when an agent can move quickly but its assumptions or “done” claims
need an independent check. Typical examples include:

- refactors and renames where a stale symbol, import, or call site can be missed;
- bug fixes where the agent starts changing files outside the requested scope;
- migrations and dependency changes where manifests, configuration, and tests must agree;
- shell commands that are destructive, irreversible, unusually broad, or risky;
- multi-file changes where the agent should run relevant tests before finishing;
- unfamiliar repositories where the agent needs repository-grounded context instead of guesses;
- long sessions or concurrent sessions where task history and touched-file state must stay
  separate.

For a simple read or a routine safe edit, Truthstone normally stays silent. It adds discipline
around the edges of an agent's workflow rather than interrupting every action.

### Does it work with Claude Code today?

Yes. Claude Code is the supported built-in adapter today:

```bash
truthstone install claude --project
truthstone doctor
```

The adapter uses Claude Code hook events, a local authenticated HTTP daemon for the hot path,
and a small command shim for session startup and health checks.

### Does it support Codex, Cursor, or my own coding agent?

Not as prebuilt adapters yet. The reliability engine itself is agent-agnostic; only the edge
adapter knows a host's event and response format. Built-in adapters for other hosts can be
added without rewriting the repository index, evidence engine, scope checks, or completion
gate.

### Can I build a custom adapter?

Yes. A custom adapter should:

1. Translate the host's lifecycle, prompt, tool-call, tool-result, stop, and session-end
   payloads into `truthstone.core.events.AgentEvent`.
2. Translate `truthstone.core.models.Decision` back into the host's native allow/deny/ask/
   block/context format.

The Claude implementation is the reference at
[`src/truthstone/adapters/claude_code/translate.py`](src/truthstone/adapters/claude_code/translate.py).
The normalized core is exposed through `Guard.handle(event)`, so an adapter can be a hook,
MCP server, CLI wrapper, IDE extension, or another local transport.

### Can it protect agents powered by any LLM?

Potentially, yes, if the host exposes a way to observe tool calls and return a decision or
context before or after execution. Truthstone does not call an LLM or depend on a provider
SDK; the same deterministic core can sit beside Claude, OpenAI-compatible agents, local
models, or a custom orchestration loop. Per host, you must implement the transport, event
translation, and response semantics.

It cannot add protection to a black-box chat UI that exposes no tool or lifecycle hooks. In
that case, integrate at the tool executor, MCP, CLI, or gateway boundary.

### Can I customize Truthstone for my workflow?

Yes. Common customization points are:

- `Settings` and `config.toml` for daemon, latency, retention, disk, and challenge limits;
- repository exclusion and language/index settings;
- validator and evidence rules for project-specific commands or conventions;
- adapter code for custom tools, event names, and response formats;
- telemetry and census detectors for organization-specific failure modes.

Keep the core safety invariants intact: unknown evidence should remain unknown, path checks
must stay confined to the workspace, persistence must never be required for a decision, and
hooks should fail open if the guard is unavailable. Run the full test suite after changing an
adapter or validator.

### Does customization require adding an LLM?

No. Truthstone deliberately has no internal LLM. You can add a separate policy engine or
model outside the core if desired, but the default system remains deterministic, local,
inspectable, and independent of any model provider.

### Can it run in CI or outside an interactive coding session?

The core `Guard` and repository index can be used from Python or a wrapper process, and the
CLI includes repository inspection and benchmark commands. The polished installation path is
Claude Code hooks; a CI, IDE, MCP, or Codex integration should provide a corresponding
adapter and choose whether findings block, request review, or are only recorded.

### Development

From this repository:

```bash
uv sync
.venv/bin/pytest -q
.venv/bin/ruff check src tests
.venv/bin/python -m compileall -q src tests
```

The project intentionally has no LLM/provider SDK dependency. Claude Code is the current
built-in adapter; Cursor and Codex adapters are not shipped yet, but the normalized adapter
interface is ready for them.

## License

Apache-2.0
