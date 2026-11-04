---
name: agentguard
description: "Resolve AgentGuard challenges. Use when a tool call was blocked by a PreToolUse hook mentioning AgentGuard, when AgentGuard kept the turn open (completion gate), or when the user asks whether AgentGuard is guarding this repository or what it has caught."
---

# AgentGuard

AgentGuard is a deterministic checker attached to this Codex session through hooks. It has
no model of its own and never grants permissions. It only speaks when it has evidence: it
then blocks a tool call or keeps the turn open, and its reason starts with "AgentGuard".

## When a tool call is blocked

The reason names the evidence: a file and line, a missing symbol, or the files involved.
Read it, then act on the evidence. Arguing with it does not help.

- **Evidence** (a symbol, method, file or package that does not exist): check the cited
  file, then use the real name, create the thing first, or explain why it exists.
- **Scope** (files the request does not reach): explain the connection to the user, or
  split the unrelated work out. Do not quietly keep going.
- **Needs the developer's confirmation** (an irreversible command such as a force push, a
  hard reset or a recursive delete): stop and ask the user. Run it again only if they
  confirm. Never reword the command to get around the check.
- **Several files in one patch**: each file is listed with its own concern. Fix them all
  before retrying.

AgentGuard raises the same concern only once per task. If you have a real reason to
proceed after addressing it, say so plainly and continue.

## When the turn is kept open

The completion gate holds a "done" that the evidence does not support. Typical cases: the
changed code no longer parses, the tests you ran are failing, or tests cover the change but
none were run. Do what the reason asks (usually run the named tests), then report the
actual result. Do not claim success you have not observed.

## Checking on AgentGuard

Run these in the repository:

- `agentguard doctor`: is it installed, running, and are its Codex hooks trusted?
- `agentguard log -n 20`: recent decisions. `agentguard why <id>` shows the evidence
  behind one decision.
- `agentguard report -d 7`: what it observed in this project this week.
- `agentguard census`: which agent failure modes actually occurred, after observe-only mode.

Codex runs plugin hooks only after the user trusts them in `/hooks`. If `doctor` says hooks
need review, tell the user; do not try to change trust yourself.
