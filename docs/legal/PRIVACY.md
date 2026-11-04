# Privacy Policy

Last updated: 4 November 2026

This policy covers two pieces of software that Tohin Majumder ("we") publishes from the GitHub repository https://github.com/tohin003/Truthstone:

- **Truthstone Practices**: a plugin made only of skills, which are written instructions for coding agents.
- **Truthstone (previously named AgentGuard)**: an open-source program that runs on your own computer and connects to coding agents through local hooks. It is distributed as a Claude Code plugin, a Codex plugin and a command-line install.

It also explains what happens to the information you send when you contact us for support.

## Summary

- **We collect no personal data through either piece of software.** There are no accounts, no telemetry or analytics, no advertising identifiers and no tracking.
- **Truthstone Practices contains no code.** It cannot collect, store or send anything.
- **Truthstone stays on your computer.** It keeps its records there and never sends them to us or to anyone else.
- **Your agent provider handles your conversations.** That is the provider of the agent product you use, for example ChatGPT, Codex or Claude Code. Its own privacy policy covers them, and we never receive them.

## 1. Truthstone Practices (the skills plugin)

**Data collected: none.** The plugin is a set of text files: skill instructions, a manifest and icons. Installing it makes those instructions available to your agent. It contains no code that could run, opens no network connections, and does not request, read or transmit any data.

**What the agent does with the skills.** When your agent follows a skill, it uses tools your environment already provides, under your usual approval settings. For example, it may read files in your repository or run your project's tests. Those actions happen inside your agent product, and nothing from them is sent to us.

## 2. Truthstone (the local runtime)

### What it reads

Truthstone works only inside git repositories: the Claude Code and Codex plugins' hooks do nothing at all when the session is not in a git work tree. Inside one, it reads what your agent product passes to its hooks: the prompts you send, the agent's edit, shell and tool calls (with their inputs and results), and at the end of a turn the agent's last message. It reads your repository's files to check the agent's claims against them. At session start the Claude Code plugin also reads Claude Code's settings files, only to detect a duplicate installation. Truthstone does not read your agent's transcripts, its memory or your other conversations.

### What it stores, on your computer only

Truthstone keeps records in a local SQLite database, by default `~/.truthstone/truthstone.db` (or in the directory that the `TRUTHSTONE_HOME` environment variable names; an installation made under the former name keeps using `~/.agentguard` until you move it). It stores its settings in `~/.truthstone/config.toml`. The records are:

| Kind of record | What it contains |
|---|---|
| Projects | The path of each repository Truthstone has seen, and the repository's remote address with any embedded credentials removed |
| Sessions | Identifiers and the session's start and end times |
| Tasks | The first 2,000 characters of each prompt that starts a task, the task details Truthstone extracted from it (up to 4,000 characters), and timestamps |
| Events | The agent's tool calls and their inputs, such as file paths, file edits and shell commands. Each text value is shortened to 200 characters, and each record to 4,000 characters |
| Decisions and findings | What Truthstone concluded about each event, with references to the files and lines it checked |
| Verification results | Which test commands ran, and a summary of their outcome |
| Usage metrics | Timings and counts that measure Truthstone's own behaviour, for example hook latency and the number of decisions |

Two small files sit beside the database: `~/.truthstone/daemon.json` holds the address and a random access token for Truthstone's local helper process (readable by your user account only), and `~/.truthstone/daemon.log` holds that process's own warnings and errors. A plugin also keeps its copy of the runtime, and the runtime installer's output, in the data folder that your agent product gives it.

### Purpose

The records are used only on your computer, for three purposes:

- to check the agent's claims and changes against your repository
- to show you why Truthstone decided what it did, for example with `truthstone log` or `truthstone why`
- to produce reports that you run yourself, such as `truthstone report` or `truthstone census`

### Who receives it

No one. Truthstone contains no telemetry or analytics. While it works, its only network connection is to its own helper process on your computer's loopback interface (127.0.0.1), which accepts requests only with the access token.

**The one-time download.** Unless you opt out, the Claude Code and Codex plugins install the Truthstone runtime the first time they run in a git repository, and again after each plugin update. They download it with `uv` from the release tag that matches the plugin version on GitHub (https://github.com/tohin003/Truthstone), its dependencies from the Python Package Index, and, only if no suitable Python is installed, a Python interpreter. Nothing about you or your work is sent in these downloads; as with any download, GitHub and the Python Package Index see the request and your IP address. To opt out, set `TRUTHSTONE_NO_BOOTSTRAP=1` and install the runtime yourself.

Messages that Truthstone gives your agent become part of the agent's conversation. Your agent provider processes that conversation under its own privacy policy.

### How long it is kept

Truthstone deletes old records automatically when a session ends, at most once every six hours. By default:

| Record | Kept for |
|---|---|
| Events | 14 days |
| Decisions, with their findings | 30 days |
| Verification results | 60 days |
| Usage metrics | 90 days |
| Sessions and tasks, including the prompt text stored with each task | 270 days after the session ends |

Some records are kept longer:

- **Sessions that never ended cleanly.** If your agent product stops before Truthstone sees the session end (for example, it was killed or crashed), that session and its unfinished tasks, including their prompt text, are not deleted automatically. They stay until you delete them.
- **The helper process's log**, `~/.truthstone/daemon.log`, is not trimmed automatically.

When the disk is nearly full, or the database outgrows its size limit, every period above is cut to a quarter. You can change each period in `~/.truthstone/config.toml`.

A future release is planned to store less prompt text. We will update this policy when it ships.

### Your controls

- **Delete everything.** Remove the `~/.truthstone` directory, or the directory that the `TRUTHSTONE_HOME` environment variable points to.
- **Turn it off.**
  - Run `truthstone off`, or `/truthstone:off` in Claude Code.
  - For a single session, set `TRUTHSTONE_DISABLE=1`. Every hook then returns immediately without recording anything.
  - Outside git repositories, the plugins' hooks never run Truthstone at all.
- **Skip the download.** Set `TRUTHSTONE_NO_BOOTSTRAP=1`. The plugins then install nothing and use a runtime you installed yourself.
- **Uninstall.** Remove the Truthstone plugin from your agent product (in Claude Code, `/plugin uninstall truthstone@truthstone`; in Codex, `codex plugin remove truthstone@truthstone`). For a Claude Code settings install, run `truthstone uninstall claude`. Uninstalling does not delete `~/.truthstone`; delete it yourself.
- **Inspect.** The database is an ordinary SQLite file that you can open and read.

## 3. When you contact us

When you open a GitHub issue, email tohin1400@gmail.com or report a security problem, we receive what you choose to send. This is usually your name or username, your email address and your message. Please don't include secrets, credentials or other people's personal data.

- **Purpose.** We use it to reply to you and to fix the problem you report.
- **Who receives it.** Only the people who maintain the project. GitHub processes issues under the GitHub Privacy Statement, and email is delivered through our email provider.
- **How long it is kept.**
  - Emails: as long as we need them to handle your request and any follow-up. We delete them when you ask; they are not deleted on a fixed schedule.
  - Public GitHub issues: they stay public until you or we delete them.
- **Your controls.** Email tohin1400@gmail.com to ask what we hold about you, or to have it deleted.

## Children

Neither piece of software is directed at children, or at anyone under 18: they are tools for software developers. We do not knowingly collect personal data from anyone, including children.

## Changes to this policy

We publish any change at this address with a new "Last updated" date. Material changes are also noted in the repository's release notes.

## Contact

Tohin Majumder: tohin1400@gmail.com, https://github.com/tohin003/Truthstone
