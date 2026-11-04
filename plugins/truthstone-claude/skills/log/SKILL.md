---
name: log
description: Show Truthstone's recent decisions in this project — what it allowed, challenged, sent for review or held.
license: Apache-2.0
disable-model-invocation: true
argument-hint: "[count]"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" *)
---

!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" cli "${CLAUDE_PLUGIN_DATA}" log -n 20`

Show the log above to the user as it is; it is already formatted.

The user asked for: "$ARGUMENTS". If that is a number other than 20, run
`sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" cli "${CLAUDE_PLUGIN_DATA}" log -n <number>`
with that number (digits only) and show that output instead.

Offer `/truthstone:why <id>` for any decision they want explained.
