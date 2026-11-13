# Truthstone for Codex

Truthstone (previously named AgentGuard) is a local, deterministic reliability layer for Codex. It has no
model of its own. Through Codex lifecycle hooks it checks what the agent is about to do
against your repository: symbols that do not exist, edits that wander far outside the task,
irreversible shell commands, and a finished turn whose changes no test has exercised. When
it finds evidence of a problem, it hands that evidence back to Codex so the agent's own
reasoning can fix it. Otherwise it says nothing. It never grants a permission, and if it is
unavailable, Codex simply continues unguarded.

It works only inside git repositories. Elsewhere its hooks do nothing at all.

Publisher: Tohin Majumder (tohin1400@gmail.com). Licence: Apache-2.0. Source: https://github.com/tohin003/Truthstone

## Install

    codex plugin marketplace add tohin003/Truthstone
    codex plugin add truthstone@truthstone

Then trust the hooks. Codex runs a plugin's hooks only after you review them: run `/hooks`
in the Codex CLI, or use **Review hooks** in the ChatGPT desktop app. Codex asks again
whenever any file in the plugin changes.

It runs in the Codex CLI and in local threads of the ChatGPT desktop app. Codex does not run
plugin hooks in the Codex IDE extension, in ChatGPT on the web or on mobile, or in cloud
tasks, so Truthstone does nothing there.

## What it runs, sends and fetches

All of it runs on your machine, with your user permissions. Every hook runs one short POSIX
script, `hooks/truthstone-hook.sh`, with the event's name. The script exits at once, doing nothing, when
the session's directory is not inside a git work tree, or when `TRUTHSTONE_DISABLE=1` is
set. Otherwise it hands the event to the Truthstone runtime: `$TRUTHSTONE_CODEX_HOOK` if you
set it, else `truthstone-codex-hook` on your `PATH`, else a private copy in the plugin's data folder.

- **Session start** (`SessionStart`): if no runtime is found, installs the private copy
  (below). Starts Truthstone's local helper process, and says once if the session is
  unguarded.
- **Every prompt you send** (`UserPromptSubmit`): records the task, and may add a short
  planning note to Codex's context.
- **Before shell commands and patches** (`PreToolUse` on `Bash` and `apply_patch`): checks
  the call against your repository and the task. Usually it says nothing. Otherwise it hands
  Codex a challenge with its evidence. For an irreversible action it denies the call until
  you confirm, because Codex has no permission prompt that hooks can use.
- **After those calls** (`PostToolUse`): records what changed and any test results it can
  see.
- **End of each turn** (`Stop`): the completion gate. If files changed and no passing test
  run was seen, it holds the turn once, with the reason and the command to run.
- **Session end** (`SessionEnd`): closes the session record.

**The native forwarder.** At session start the runtime also compiles the small C program that
hands tool calls, Stop and SessionEnd to its helper process (`forward_native.c`, shipped with
the runtime), with your C compiler (`cc`), into the plugin's data folder, once per version.
Those events then skip Python's start-up. Without a compiler nothing is compiled and Python
does the same job.

**The one-time download.** At session start, if no runtime is found, `uv` is available and
`TRUTHSTONE_NO_BOOTSTRAP` is not set, the script installs a private copy into the plugin's
data folder, never onto your `PATH`:

    uv tool install --reinstall git+https://github.com/tohin003/Truthstone@v0.2.0

That fetches this plugin's own release from GitHub, and the runtime's dependencies from the
Python Package Index; `uv` downloads a CPython 3.12 or later interpreter only if you have no
usable Python. The installer's output goes to `install.log` in that folder. It installs
again only when the plugin's pinned source changes. Once Truthstone is published on PyPI,
the runtime will come from there instead. Nothing else is downloaded, and nothing is ever
uploaded.

**No download.** Set `TRUTHSTONE_NO_BOOTSTRAP=1` and install the runtime yourself:

    uv tool install git+https://github.com/tohin003/Truthstone@v0.2.0

That puts `truthstone-codex-hook` on your `PATH`, which the script uses first.

**The local helper process.** The runtime starts a small HTTP server that listens only on
127.0.0.1. It accepts a request only with a random bearer token, which Truthstone creates on
your machine and keeps in `~/.truthstone/daemon.json` with owner-only permissions. Hook
payloads go there and nowhere else. Truthstone has no server of its own anywhere, no
telemetry and no analytics. It does not read your Codex transcripts or other conversations.

**What reaches Codex.** When Truthstone has something to say, that text becomes part of your
Codex conversation, which Codex handles like everything else in the session.

## Your data

Truthstone keeps its records on your computer, in a SQLite database at
`~/.truthstone/truthstone.db` (or under `TRUTHSTONE_HOME` if you set it). Nothing is sent to
the publisher or to anyone else. It stores:

- each repository's path, and its remote address with any credentials removed;
- session records: identifiers, start and end times;
- task records: the first 2,000 characters of each prompt that starts a task, and the task
  details Truthstone extracted from it;
- tool calls and their inputs (shell commands, patches), with each text value shortened to
  200 characters and each record to 4,000 characters;
- Truthstone's decisions and findings, with the files and lines it checked;
- which test commands ran, and a summary of their outcome;
- timings and counts that measure Truthstone's own behaviour.

The helper process writes its own warnings and errors to `~/.truthstone/daemon.log`.

**How long it is kept.** Truthstone deletes old records automatically when a session ends,
at most once every six hours:

| Record | Kept for |
|---|---|
| Tool calls | 14 days |
| Decisions and their findings | 30 days |
| Test results | 60 days |
| Timings and counts | 90 days |
| Sessions and tasks, including the prompt text | 270 days after the session ends |

A session that never ended cleanly is not deleted automatically, so its session and task
records stay until you delete them. When the disk is nearly full, or the database outgrows
its size limit, all periods are cut to a quarter. You can change each period in
`~/.truthstone/config.toml`, and you can delete `~/.truthstone` at any time to erase
everything. A coming release is planned to store less prompt text. Full privacy policy:
https://github.com/tohin003/Truthstone/blob/master/docs/legal/PRIVACY.md

## Switch it off

- **For one session:** start Codex with `TRUTHSTONE_DISABLE=1`. Every hook then exits at
  once without recording anything.
- **On this machine:** `truthstone off`, and `truthstone on` to resume. The `truthstone`
  command comes with the runtime: on your `PATH` if you installed it yourself, otherwise in
  the `bin` folder of the private copy.

## Uninstall

    codex plugin remove truthstone@truthstone

Then delete `~/.truthstone` to remove Truthstone's records, and the plugin's data folder
(`$CODEX_HOME/plugins/data/truthstone-truthstone`, usually under `~/.codex`) if Codex left
it behind; it holds the private runtime. The helper process keeps running until you restart
your computer, or until you run `truthstone daemon stop`.

## Requirements

- The Codex CLI, or local threads of the ChatGPT desktop app.
- `uv` (https://docs.astral.sh/uv/getting-started/installation/) and `git`, unless you
  install the runtime yourself; Python 3.12 or later, which `uv` can provide.
- macOS or Linux. Windows is untested.

## Security

- **Never grants permissions.** Truthstone can stay silent, object, or hold an action for
  your confirmation. It never approves anything on your behalf.
- **Fails open.** If Truthstone is missing or broken, Codex works as if it were not
  installed. The script always exits 0, because Codex reads exit code 2 as "block this".
- **Runs no code from the repository it guards.** Its Python processes run isolated.
- **Reviewed by you.** Codex runs these hooks only after you trust them, and asks again
  after any change to this plugin's files.

Report a vulnerability privately through GitHub's private vulnerability reporting
(https://github.com/tohin003/Truthstone/security), or by email to tohin1400@gmail.com. See `SECURITY.md`.

## Support and policies

- Questions and bugs: https://github.com/tohin003/Truthstone/issues, or tohin1400@gmail.com.
- Support: https://github.com/tohin003/Truthstone/blob/master/docs/legal/SUPPORT.md
- Privacy policy: https://github.com/tohin003/Truthstone/blob/master/docs/legal/PRIVACY.md
- Terms of use: https://github.com/tohin003/Truthstone/blob/master/docs/legal/TERMS.md
