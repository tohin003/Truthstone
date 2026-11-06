---
name: truthstone
description: "Explains Truthstone hook messages (a blocked tool call or a held finish) and whether Truthstone is active."
---

# Truthstone

Truthstone is a deterministic checker attached to this Codex session through hooks. It has
no model of its own and never grants permissions. It only speaks when it has evidence: it
then blocks a tool call or keeps the turn open, and its reason starts with "Truthstone".

## When a tool call is blocked

The reason names the evidence: a file and line, a missing symbol, or the files involved.
Read it, then act on the evidence. Arguing with it does not help.

- **Evidence** (a symbol, method, file or package that does not exist): check the cited
  file, then use the real name, create the thing first, or explain why it exists.
- **Premise** (the request says a named thing already exists or works, and it does not): tell
  the user first. Then either build that very thing so it works as the request describes, and
  say you added it, or finish with "not done: <name> does not exist". Doing the job another way
  while the named thing stays missing is not done.
- **Scope** (files the request does not reach): explain the connection to the user, or
  split the unrelated work out. Do not quietly keep going.
- **Needs the developer's confirmation** (an irreversible command such as a force push, a
  hard reset or a recursive delete): stop and ask the user. Run it again only if they
  confirm. Never reword the command to get around the check.
- **Several files in one patch**: each file is listed with its own concern. Fix them all
  before retrying.

Truthstone raises the same concern only once per task. If you have a real reason to
proceed after addressing it, say so plainly and continue. Past a premise, continuing means
building the named thing itself, never a workaround around it.

## When the turn is kept open

The completion gate holds a "done" that the evidence does not support. Typical cases: the
changed code no longer parses, the tests you ran are failing, tests cover the change but
none were run, existing tests were edited under test pressure, or a thing the request said
already works still does not exist. Do what the reason asks (usually run the named tests),
then report the actual result. Do not claim success you have not observed.

## Checking on Truthstone

Run these in the repository:

- `truthstone doctor`: is it installed, running, and are its Codex hooks trusted?
- `truthstone log -n 20`: recent decisions. `truthstone why <id>` shows the evidence
  behind one decision.
- `truthstone report -d 7`: what it observed in this project this week.
- `truthstone census`: which agent failure modes actually occurred, after observe-only mode.

Codex runs plugin hooks only after the user trusts them in `/hooks`. If `doctor` says hooks
need review, tell the user; do not try to change trust yourself.
