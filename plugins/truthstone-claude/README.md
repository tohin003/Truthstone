# Truthstone for Claude Code

Truthstone (previously named AgentGuard) is a local, deterministic reliability layer for
Claude Code. It has no model of its own. It watches what the agent does through Claude
Code hooks and does three things:

- **Grounds claims in evidence.** It checks the agent's edits and statements against your
  repository, and hands back anything that does not match, with the files and lines it
  checked.
- **Sends risky or out-of-scope actions back to you.** Before a destructive or
  out-of-scope edit, shell command or MCP tool call runs, it asks you through Claude
  Code's own permission prompt, with its reason. Sometimes it proposes a narrower command
  for you to approve instead. It never approves anything on your behalf.
- **Holds an unverified "done".** When a turn ends after files changed and no passing test
  run was seen, its completion gate holds the turn once and names the test command to
  run. If the turn still ends unverified, it tells you.

It works only inside git repositories. Elsewhere its hooks do nothing at all. If anything
is missing or broken, Truthstone gets out of the way: Claude Code behaves as if it were not
installed, and Truthstone tells you once that the session is unguarded.

Publisher: Tohin Majumder. Licence: Apache-2.0. Source:
https://github.com/tohin003/Truthstone

## Install

In Claude Code, add the marketplace and install the plugin:

    /plugin marketplace add tohin003/Truthstone
    /plugin install truthstone@truthstone

Then start a new session inside a git repository. The first such session installs the
Truthstone runtime (next section), which needs `uv` and `git`.

## What it runs, sends and fetches

All of it runs on your machine, with your user permissions. Every hook runs one of two
shell scripts in this plugin's `scripts/` folder, and each script first checks that the
current directory or the project directory is inside a git work tree. If neither is, the
hook exits at once and does nothing.

| When | Hook | What Truthstone does |
|---|---|---|
| Session start, resume or `/clear` | `SessionStart` runs `scripts/session-start.sh` | The first time, and after each plugin update, it installs the runtime (below). It starts Truthstone's local helper process and checks for a duplicate settings-based install. If it cannot run, it tells you once. |
| Every prompt you send | `UserPromptSubmit` runs `scripts/hook.sh` | It passes the prompt to the local helper, which records the task and may add a short planning note to Claude's context. The note is visible in the transcript. It also checks that guarding is healthy. |
| Before Edit, Write, MultiEdit, NotebookEdit, Bash, PowerShell and MCP tool calls | `PreToolUse` runs `scripts/hook.sh` | It checks the call against your repository and the task. Usually it says nothing. Otherwise it adds a note for Claude, or asks you to confirm through Claude Code's permission prompt with its reason. In non-interactive runs (`claude -p`) nobody can answer, so Claude Code denies the call. |
| After those tool calls | `PostToolUse` runs `scripts/hook.sh` | It records what changed and any test results it can see, and tells Claude when a claim does not match the evidence. |
| After a failed Bash or PowerShell command | `PostToolUseFailure` runs `scripts/hook.sh` | It records the failure, for example a failing test run. |
| End of each turn | `Stop` runs `scripts/hook.sh` | The completion gate: if files changed and no passing test run was seen, it holds the turn once, with the reason and the command to run. It reads Claude's last message for this and does not store it. |
| Session end | `SessionEnd` runs `scripts/hook.sh` | It closes the session record. |

**The one-time download.** `scripts/session-start.sh` is the only part of the plugin that
installs anything. On the first session in a git repository, and after each plugin update,
it creates a virtual environment in the plugin's data folder with `uv` and installs into
it:

- the Truthstone runtime, from release tag `v<plugin version>` (for this release `v0.2.0`)
  of https://github.com/tohin003/Truthstone, fetched with `git`. Once Truthstone is
  published on PyPI, the runtime will come from there instead;
- its dependencies (pydantic, typer, fastapi, uvicorn, pyyaml and what they need), from the
  Python Package Index;
- a CPython 3.12 or later interpreter, which `uv` downloads only if you have no usable
  Python.

The installer's output is kept in `install.log` in the plugin's data folder. Nothing else
is downloaded, and nothing is ever uploaded.

**The local helper process.** The runtime starts a small HTTP server that listens only on
127.0.0.1. It accepts a request only with a random bearer token, which Truthstone creates
on your machine and keeps in `~/.truthstone/daemon.json` with owner-only permissions. The
per-tool hooks send each hook payload there and nowhere else, and drop any answer that
would grant a permission. Truthstone has no server of its own anywhere, no telemetry and no
analytics. It never reads Claude Code transcripts, Claude's memory or your other
conversations. At session start it reads Claude Code's settings files only to detect a
duplicate install.

**What reaches Claude.** When Truthstone has something to say (a challenge, the reason for
a permission prompt, a planning note, a completion-gate hold), that text becomes part of
your Claude Code conversation, which Claude Code handles like everything else in the
session.

## Your data

Truthstone keeps its records on your computer, in a SQLite database at
`~/.truthstone/truthstone.db` (or under `TRUTHSTONE_HOME` if you set it). Nothing is sent
to the publisher or to anyone else. It stores:

- each repository's path, and its remote address with any credentials removed;
- session records: identifiers, start and end times;
- task records: the first 2,000 characters of each prompt that starts a task, and the
  task details Truthstone extracted from it;
- tool calls and their inputs (file paths, edits, shell commands), with each text value
  shortened to 200 characters and each record to 4,000 characters;
- Truthstone's decisions and findings, with the files and lines it checked;
- which test commands ran, and a summary of their outcome;
- timings and counts that measure Truthstone's own behaviour.

The helper process writes its own warnings and errors to `~/.truthstone/daemon.log`, and
your settings live in `~/.truthstone/config.toml`.

**How long it is kept.** Truthstone deletes old records automatically when a session ends,
at most once every six hours:

| Record | Kept for |
|---|---|
| Tool calls | 14 days |
| Decisions and their findings | 30 days |
| Test results | 60 days |
| Timings and counts | 90 days |
| Sessions and tasks, including the prompt text | 270 days after the session ends |

A session that never ended cleanly (for example, Claude Code was killed before its
`SessionEnd` hook ran) is not deleted automatically, so its session and task records stay
until you delete them. When the disk is nearly full, or the database outgrows its size
limit, all periods are cut to a quarter.
You can change each period in `~/.truthstone/config.toml`, and you can delete
`~/.truthstone` at any time to erase everything. A coming release is planned to store less
prompt text; this page will change when it does.

## Switch it off, or skip the download

- **Off on this machine:** `/truthstone:off`, and `/truthstone:on` to resume.
- **Off for one session:** start Claude Code with `TRUTHSTONE_DISABLE=1`. Every hook then
  exits at once without recording anything. `TRUTHSTONE_OBSERVE=1` records without saying
  anything to Claude.
- **No download:** set `TRUTHSTONE_NO_BOOTSTRAP=1` before starting Claude Code. The plugin
  then downloads and installs nothing. Install the runtime yourself:

      uv tool install git+https://github.com/tohin003/Truthstone@v0.2.0

  (or `pipx install` with the same source). At session start the plugin finds `truthstone`
  on your `PATH` or in `~/.local/bin` and uses that runtime, without writing into it. If it
  finds none, it tells you once how to install it, and the session runs unguarded.

## Commands

You type these; Claude cannot run them on its own.

- `/truthstone:doctor`: is this session guarded? Runtime, helper process and hook checks,
  with fixes.
- `/truthstone:log [n]`: recent decisions in this project.
- `/truthstone:why <id>`: the findings and evidence behind one decision.
- `/truthstone:report [days]`: what Truthstone did in this project.
- `/truthstone:off` and `/truthstone:on`: stop or resume guarding on this machine.

The plugin also has a skill that Claude loads only when Truthstone feedback appears, so it
knows how to read and resolve it.

## Uninstall

    /plugin uninstall truthstone@truthstone

Claude Code then deletes the plugin and its data folder, which holds the runtime.
Truthstone's records in `~/.truthstone` are kept, because a command-line install may share
them; delete that folder yourself to remove them. The helper process keeps running until
you restart your computer. To stop it sooner, run `truthstone daemon stop` from the
runtime's `bin` folder, inside the data folder that `/truthstone:doctor` shows (usually
`~/.claude/plugins/data/truthstone-truthstone/runtime/bin`).

## Requirements

- Claude Code in a local session: the terminal, an IDE extension, or the desktop app's
  Code tab. Plugins do not run in cloud sessions.
- `uv` (https://docs.astral.sh/uv/getting-started/installation/) and `git`, unless you
  install the runtime yourself.
- Python 3.12 or later. `uv` uses one you already have, or downloads one the first time.
- Network access on the first session, and after each update, for the download above.
- macOS or Linux. Windows is not supported yet.

## Security

- **Never grants permissions.** No hook answer approves a tool call or skips your approval
  prompt; the forwarder drops any answer that would, even one from an impostor on the port.
- **Fails open, never silently.** If Truthstone is missing or broken, Claude Code works as
  if it were not installed, and you are told once that the session is unguarded.
- **Runs no code from the repository it guards.** Its Python processes run isolated
  (`python -I`), so a repository's own modules are never imported.
- **No MCP servers and no telemetry.** The plugin holds only readable text files (three
  shell scripts, the hook list, the skills, this README, the licence and the security
  policy) and its icon.

Report a vulnerability privately through GitHub's private vulnerability reporting
(https://github.com/tohin003/Truthstone/security), or by email to tohin1400@gmail.com. See
`SECURITY.md`.

## Support and policies

- Questions and bugs: https://github.com/tohin003/Truthstone/issues, or
  tohin1400@gmail.com.
- Privacy policy: https://github.com/tohin003/Truthstone/blob/master/docs/legal/PRIVACY.md
- Terms of use: https://github.com/tohin003/Truthstone/blob/master/docs/legal/TERMS.md
- Design notes: https://github.com/tohin003/Truthstone/blob/master/docs/CLAUDE-PLUGIN.md
