---
name: "off"
description: Turn Truthstone (previously named AgentGuard) off. The plugin stays installed but decides nothing until /truthstone:on. Applies to every Claude Code session on this machine.
license: Apache-2.0
disable-model-invocation: true
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/command.sh" *)
---

!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/command.sh" plugin "${CLAUDE_PLUGIN_DATA}" off`

Tell the user the result above in one or two lines. Mention that `/truthstone:on` turns
it back on, and that `TRUTHSTONE_DISABLE=1 claude` switches it off for a single session
instead.
