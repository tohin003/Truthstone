---
name: "off"
description: Turn AgentGuard off. The plugin stays installed but decides nothing until /agentguard:on. Applies to every Claude Code session on this machine.
license: Apache-2.0
disable-model-invocation: true
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" *)
---

!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" plugin "${CLAUDE_PLUGIN_DATA}" off`

Tell the user the result above in one or two lines. Mention that `/agentguard:on` turns
it back on, and that `AGENTGUARD_DISABLE=1 claude` switches it off for a single session
instead.
