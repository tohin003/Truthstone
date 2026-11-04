---
name: doctor
description: Check Truthstone's runtime, daemon and hooks for this project, and say how to fix anything that is wrong.
license: Apache-2.0
disable-model-invocation: true
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/command.sh" *)
---

## Truthstone plugin

!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/command.sh" plugin "${CLAUDE_PLUGIN_DATA}" status`

## Full check

!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/command.sh" cli "${CLAUDE_PLUGIN_DATA}" doctor`

Summarize this for the user in a few lines. Start with whether this session is guarded.
Then, for each problem (lines marked ✗ or !), say what it means and give the exact fix.
Do not run other commands unless the user asks.
