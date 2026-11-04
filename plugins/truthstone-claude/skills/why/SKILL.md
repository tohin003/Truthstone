---
name: why
description: Explain one Truthstone (previously named AgentGuard) decision — every finding and piece of evidence behind it.
license: Apache-2.0
disable-model-invocation: true
argument-hint: "<decision-id>"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/command.sh" *)
---

The user wants this Truthstone decision explained: "$ARGUMENTS".

If that is a decision id or a prefix of one (letters, digits and hyphens only), run
`sh "${CLAUDE_PLUGIN_ROOT}/scripts/command.sh" cli "${CLAUDE_PLUGIN_DATA}" why <id>`.
Pass the id exactly as given; never pass anything else on that command line.

Then explain it in plain words: what Truthstone objected to, the evidence it cited, and
whether that evidence holds when you look at the cited files yourself.

If no id was given, run
`sh "${CLAUDE_PLUGIN_ROOT}/scripts/command.sh" cli "${CLAUDE_PLUGIN_DATA}" log -n 10`
and ask which decision they mean.
