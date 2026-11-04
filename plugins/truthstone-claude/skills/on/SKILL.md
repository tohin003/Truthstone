---
name: "on"
description: Turn Truthstone (previously named AgentGuard) back on after /truthstone:off. Applies to every Claude Code session on this machine.
license: Apache-2.0
disable-model-invocation: true
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" *)
---

!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" plugin "${CLAUDE_PLUGIN_DATA}" on`

Tell the user the result above in one line.
