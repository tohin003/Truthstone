#!/bin/sh
# Truthstone: the /truthstone:* commands. Only the plugin's command skills run this
# script, when you type one of those commands; no hook runs it.
#
#   sh "${CLAUDE_PLUGIN_ROOT}/scripts/command.sh" cli <data-dir> <args>     the truthstone CLI:
#                                                                          doctor, log, why, report
#   sh "${CLAUDE_PLUGIN_ROOT}/scripts/command.sh" plugin <data-dir> <args>  plugin status, on, off
#
# The skills pass the plugin's data directory as an argument, because Claude Code
# substitutes ${CLAUDE_PLUGIN_DATA} into a skill's text but does not export it to the
# commands a skill runs. This script installs and downloads nothing: without a runtime it
# says how to get one. It always exits 0, because a non-zero status would abort the
# command before you see its output.

# rename-tool: keep-begin former-settings (settings under a former product name still apply)
[ -n "${TRUTHSTONE_NO_BOOTSTRAP:-}" ] || [ -z "${AGENTGUARD_NO_BOOTSTRAP+x}" ] || TRUTHSTONE_NO_BOOTSTRAP=$AGENTGUARD_NO_BOOTSTRAP
[ -n "${TRUTHSTONE_UV:-}" ] || [ -z "${AGENTGUARD_UV+x}" ] || TRUTHSTONE_UV=$AGENTGUARD_UV
# rename-tool: keep-end

PRODUCT="Truthstone"
PACKAGE="truthstone"
MODULE="truthstone.adapters.claude_code"
SOURCE_TEMPLATE="git+https://github.com/tohin003/Truthstone@v{version}"
UV_HELP="https://docs.astral.sh/uv/getting-started/installation/"

kind=${1:-}
data=${2:-}
case $kind in
cli | plugin) [ $# -ge 2 ] && shift 2 ;;
*) exit 0 ;;
esac
root=${CLAUDE_PLUGIN_ROOT:-$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)}

in_work_tree() {
	d=$1
	case $d in /*) ;; *) return 1 ;; esac
	while :; do
		[ -e "$d/.git" ] && return 0
		[ -n "$d" ] || return 1
		d=${d%/*}
	done
}

has_uv() {
	if [ -n "${TRUTHSTONE_UV+set}" ]; then
		[ -x "$TRUTHSTONE_UV" ]
		return
	fi
	for candidate in "$(command -v uv 2>/dev/null)" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" \
		/opt/homebrew/bin/uv /usr/local/bin/uv; do
		[ -n "$candidate" ] && [ -x "$candidate" ] && return 0
	done
	return 1
}

py="$data/runtime/bin/python"
if [ -z "$data" ] || [ ! -x "$py" ] || [ ! -r "$data/runtime.ready" ]; then
	printf '%s runtime is not installed yet.\n' "$PRODUCT"
	version=$(sed -n 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*$/\1/p' \
		"$root/.claude-plugin/plugin.json" 2>/dev/null | head -n 1)
	source=$(printf '%s\n' "$SOURCE_TEMPLATE" | sed "s/{version}/${version:-<version>}/g")
	if [ -n "${TRUTHSTONE_NO_BOOTSTRAP:-}" ]; then
		printf 'TRUTHSTONE_NO_BOOTSTRAP is set, so the plugin downloads and installs nothing.\n'
		printf 'Install the runtime yourself, then start a new session:  uv tool install %s\n' "$source"
	else
		printf 'It installs at the start of a Claude Code session in a git repository.\n'
		[ -r "$data/install.log" ] && printf 'Last installer output (%s):\n' "$data/install.log" &&
			tail -n 20 "$data/install.log"
		has_uv || printf 'uv was not found. Install it (%s), then start a new session.\n' "$UV_HELP"
	fi
	exit 0
fi

if [ "$kind" = plugin ] && ! in_work_tree "$PWD"; then
	printf '%s is idle here: %s is not inside a git work tree, so its hooks do nothing.\n' "$PRODUCT" "$PWD"
fi
if [ "$kind" = cli ]; then
	TRUTHSTONE_PLUGIN_DATA=$data "$(dirname -- "$py")/$PACKAGE" "$@" 2>&1
else
	CLAUDE_PLUGIN_DATA=$data "$py" -I -m "$MODULE.plugin" "$@" 2>&1
fi
status=$?
# A non-zero status would abort the slash command that ran this; report it instead.
[ "$status" -eq 0 ] || printf '(exit status %s)\n' "$status"
exit 0
