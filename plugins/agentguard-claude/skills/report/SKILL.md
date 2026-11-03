---
name: report
description: Summarize what AgentGuard has done in this project over the last week — decisions, what it caught, completion-gate holds and overhead.
license: Apache-2.0
disable-model-invocation: true
argument-hint: "[days]"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" *)
---

!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" cli "${CLAUDE_PLUGIN_DATA}" report -d 7`

Show the report above to the user, then add a two-line reading of it: how often
AgentGuard intervened and what it caught. These are observations, not proof of effect;
do not describe them as an improvement.

The user asked for: "$ARGUMENTS". If that is a number of days other than 7, run
`sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" cli "${CLAUDE_PLUGIN_DATA}" report -d <days>`
with that number (digits only) and show that output instead.
