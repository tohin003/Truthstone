# Privacy Policy

Last updated: 4 November 2026

This policy covers two pieces of software that {{PUBLISHER_NAME}} ("we") publishes from the GitHub repository https://github.com/tohin003/Truthstone:

- **Truthstone Practices**: a plugin made only of skills, which are written instructions for coding agents.
- **Truthstone (previously named AgentGuard)**: an open-source program that runs on your own computer and connects to coding agents through local hooks.

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

### What it stores, on your computer only

To check an agent's work, Truthstone keeps records in a local SQLite database, by default `~/.truthstone/truthstone.db`. It stores its settings in `~/.truthstone/config.toml`. The records are:

| Kind of record | What it contains |
|---|---|
| Projects | The path of each repository Truthstone has seen, and the repository's remote address with any embedded credentials removed |
| Sessions and tasks | Identifiers, timestamps, and the text of each task request given to the agent |
| Events | The agent's tool calls and their arguments, such as file paths, file edits and shell commands |
| Decisions and findings | What Truthstone concluded about each event, with references to the files and lines it checked |
| Verification results | Which test commands ran, and a summary of their outcome |
| Usage metrics | Timings and counts that measure Truthstone's own behaviour, for example hook latency and the number of decisions |

A small file, `~/.truthstone/daemon.json`, holds the address and a random access token for Truthstone's local helper process.

### Purpose

The records are used only on your computer, for three purposes:

- to check the agent's claims and changes against your repository
- to show you why Truthstone decided what it did, for example with `truthstone log` or `truthstone why`
- to produce reports that you run yourself, such as `truthstone census`

### Who receives it

No one. Truthstone contains no telemetry or analytics. Its only network connection is to its own helper process on your computer's loopback interface (127.0.0.1).

Messages that Truthstone gives your agent become part of the agent's conversation. Your agent provider processes that conversation under its own privacy policy.

### How long it is kept

By default, records are deleted automatically after these periods:

| Record | Kept for |
|---|---|
| Events | 14 days |
| Decisions | 30 days |
| Verification results | 60 days |
| Usage metrics | 90 days |
| Session and task summaries | 270 days |

Findings are deleted together with the decisions and tasks they belong to. You can change each period in `~/.truthstone/config.toml`.

### Your controls

- **Delete everything.** Remove the `~/.truthstone` directory, or the directory that the `TRUTHSTONE_HOME` environment variable points to.
- **Turn it off.**
  - Run `truthstone off`.
  - For a single session, set `TRUTHSTONE_DISABLE=1`. Every hook then returns immediately without recording anything.
- **Uninstall.** Remove the Truthstone plugin from your agent product. For a Claude Code settings install, run `truthstone uninstall`.
- **Inspect.** The database is an ordinary SQLite file that you can open and read.

## 3. When you contact us

When you open a GitHub issue, email {{SUPPORT_EMAIL}} or report a security problem, we receive what you choose to send. This is usually your name or username, your email address and your message. Please don't include secrets, credentials or other people's personal data.

- **Purpose.** We use it to reply to you and to fix the problem you report.
- **Who receives it.** Only the people who maintain the project. GitHub processes issues under the GitHub Privacy Statement.
- **How long it is kept.**
  - Emails: up to 12 months after the conversation ends, then deleted.
  - Public GitHub issues: they stay public until you or we delete them.
- **Your controls.** Email {{SUPPORT_EMAIL}} to ask what we hold about you, or to have it deleted.

## Children

Neither piece of software is directed at children under 13. We do not knowingly collect personal data from anyone, including children.

## Changes to this policy

We publish any change at this address with a new "Last updated" date. Material changes are also noted in the repository's release notes.

## Contact

{{PUBLISHER_NAME}}: {{SUPPORT_EMAIL}}, https://github.com/tohin003/Truthstone
