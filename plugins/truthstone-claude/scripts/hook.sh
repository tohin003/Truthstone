#!/bin/sh
# Truthstone: the hook script for every Claude Code event except SessionStart.
#
#   sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" <event>
#
#   prompt         UserPromptSubmit
#   pre-tool       PreToolUse          (edit, shell and MCP tools: see hooks/hooks.json)
#   post-tool      PostToolUse
#   tool-failure   PostToolUseFailure
#   stop           Stop
#   session-end    SessionEnd
#
# It hands the hook's JSON payload (stdin) to the Truthstone runtime that
# scripts/session-start.sh installed in the plugin's data directory, and prints the
# runtime's answer. It installs, downloads and updates nothing, and contacts no host
# itself. The runtime sends the payload only to Truthstone's own daemon on 127.0.0.1,
# with a local bearer token, and never grants a permission.
#
# It exits 0 with no output, and does nothing else, when:
#   - neither the current directory nor the project directory is inside a git work tree
#     (the project gate below: Truthstone guards work in git repositories only);
#   - Truthstone is switched off for this session (TRUTHSTONE_DISABLE=1);
#   - the runtime is not installed (yet).
# After that, every failure also ends in exit 0 with no output (fail open): a problem in
# Truthstone never blocks Claude. README.md describes everything the plugin does.

# rename-tool: keep-begin former-settings (settings under a former product name still apply)
[ -n "${TRUTHSTONE_DISABLE:-}" ] || [ -z "${AGENTGUARD_DISABLE+x}" ] || TRUTHSTONE_DISABLE=$AGENTGUARD_DISABLE
# rename-tool: keep-end

# The forwarder's time budget in seconds: always below the hook's timeout in
# hooks/hooks.json, so Truthstone gives up before Claude Code does.
case ${1:-} in
pre-tool | post-tool | tool-failure) budget=4 ;;
stop) budget=9 ;;
session-end) budget=1 ;; # Claude Code allows all SessionEnd hooks 1.5 s in total
prompt) budget=0 ;;
*) exit 0 ;;
esac

# Switched off for this session.
case ${TRUTHSTONE_DISABLE:-} in
1 | [Tt][Rr][Uu][Ee] | [Yy][Ee][Ss] | [Oo][Nn]) exit 0 ;;
esac

# The project gate. Truthstone guards work in git repositories only: unless the current
# directory or the project directory is inside a git work tree (it, or a folder above it,
# has a .git entry), do nothing.
in_work_tree() {
	d=$1
	case $d in /*) ;; *) return 1 ;; esac
	while :; do
		[ -e "$d/.git" ] && return 0
		[ -n "$d" ] || return 1
		d=${d%/*}
	done
}
in_work_tree "$PWD" || in_work_tree "${CLAUDE_PROJECT_DIR:-}" || exit 0

# The runtime that scripts/session-start.sh installed. Until it is complete, do nothing.
data=${CLAUDE_PLUGIN_DATA:-}
py=$data/runtime/bin/python
[ -n "$data" ] && [ -x "$py" ] && [ -r "$data/forward.py" ] && [ -r "$data/runtime.ready" ] || exit 0

if [ "$budget" = 0 ]; then
	# Once per prompt: revive the daemon if it died, say once if this session is
	# unguarded, then forward the prompt.
	exec "$py" -I -m truthstone.adapters.claude_code.plugin prompt
fi
# Once per tool call: the lean forwarder (no site-packages, builtin modules only).
exec "$py" -I -S "$data/forward.py" --timeout "$budget"
