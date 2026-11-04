#!/bin/sh
# Truthstone — Claude Code plugin launcher.
#
# hooks/hooks.json and the /truthstone:* commands run this file:
#
#   hook.sh session-start            SessionStart: install or upgrade the runtime when
#                                    needed, start the daemon, forward the event
#   hook.sh prompt                   UserPromptSubmit: health check, then forward
#   hook.sh cli <data-dir> <args>    /truthstone:* commands: the truthstone CLI
#   hook.sh plugin <data-dir> <args> /truthstone:* commands: plugin status and switches
#
# The per-tool hooks (PreToolUse, PostToolUse, PostToolUseFailure, Stop, SessionEnd) do not
# come through here: hooks.json runs the runtime's forwarder directly, because a second
# shell costs ~3.5 ms on every tool call. They depend only on the data-directory layout
# this script maintains:
#
#   $CLAUDE_PLUGIN_DATA/runtime/        a uv virtualenv with Truthstone installed
#   $CLAUDE_PLUGIN_DATA/forward.py      link to that runtime's hot-path forwarder
#   $CLAUDE_PLUGIN_DATA/runtime.ready   the source the runtime was built from, written last
#
# The plugin is deliberately thin: all guarding logic lives in the Truthstone Python
# package. An Truthstone release changes the plugin's version, never this file.
#
# Contract with Claude Code: exit 0, and print nothing unless Truthstone has something to
# say. Never exit 2 — that would block the agent, and a launcher problem is never a
# finding. If the runtime cannot be installed, the session runs unguarded and the
# developer is told once, at session start, exactly what to do.

# rename-tool: keep-begin former-settings (settings under a former product name still apply)
[ -n "${TRUTHSTONE_DISABLE:-}" ] || [ -z "${AGENTGUARD_DISABLE+x}" ] || TRUTHSTONE_DISABLE=$AGENTGUARD_DISABLE
[ -n "${TRUTHSTONE_INSTALL_WAIT:-}" ] || [ -z "${AGENTGUARD_INSTALL_WAIT+x}" ] || TRUTHSTONE_INSTALL_WAIT=$AGENTGUARD_INSTALL_WAIT
[ -n "${TRUTHSTONE_RUNTIME_SPEC:-}" ] || [ -z "${AGENTGUARD_RUNTIME_SPEC+x}" ] || TRUTHSTONE_RUNTIME_SPEC=$AGENTGUARD_RUNTIME_SPEC
[ -n "${TRUTHSTONE_UV:-}" ] || [ -z "${AGENTGUARD_UV+x}" ] || TRUTHSTONE_UV=$AGENTGUARD_UV
# rename-tool: keep-end

# ---- names: a product rename edits this block, plugin.json and marketplace.json -------
PRODUCT="Truthstone"
PACKAGE="truthstone"
MODULE="truthstone.adapters.claude_code"
# The runtime the plugin installs. {version} is this plugin's own version (plugin.json),
# so the runtime always matches the plugin release that ships it. Once Truthstone is on
# PyPI this becomes:  SOURCE_TEMPLATE="truthstone=={version}"
SOURCE_TEMPLATE="git+https://github.com/tohin003/Truthstone@v{version}"
UV_INSTALL="curl -LsSf https://astral.sh/uv/install.sh | sh"
# ---------------------------------------------------------------------------------------

kind=${1:-}
root=${CLAUDE_PLUGIN_ROOT:-$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)}
data=${CLAUDE_PLUGIN_DATA:-}

off() {
	case ${TRUTHSTONE_DISABLE:-} in
	1 | [Tt][Rr][Uu][Ee] | [Yy][Ee][Ss] | [Oo][Nn]) return 0 ;;
	esac
	return 1
}

# Sets $py and $spec when a complete runtime is present.
read_ready() {
	[ -n "$data" ] || return 1
	py="$data/runtime/bin/python"
	[ -x "$py" ] && [ -r "$data/forward.py" ] && [ -r "$data/runtime.ready" ] || return 1
	IFS= read -r spec <"$data/runtime.ready" || [ -n "$spec" ]
}

# A JSON systemMessage: shown to the developer, never added to Claude's context.
say() {
	msg=$(printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr '\n\t' '  ')
	printf '{"systemMessage": "%s"}\n' "$msg"
}

want_spec() {
	if [ -n "${TRUTHSTONE_RUNTIME_SPEC:-}" ]; then
		printf '%s\n' "$TRUTHSTONE_RUNTIME_SPEC"
		return 0
	fi
	version=$(sed -n 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*$/\1/p' \
		"$root/.claude-plugin/plugin.json" 2>/dev/null | head -n 1)
	[ -n "$version" ] || return 1
	printf '%s\n' "$SOURCE_TEMPLATE" | sed "s/{version}/$version/g"
}

find_uv() {
	if [ -n "${TRUTHSTONE_UV+set}" ]; then
		# An explicit choice, honoured exactly (also how tests simulate "no uv").
		[ -x "$TRUTHSTONE_UV" ] && printf '%s\n' "$TRUTHSTONE_UV" && return 0
		return 1
	fi
	# Claude Desktop starts sessions with the PATH your login shell exported when the
	# app launched, so also look where the uv installer and package managers put it.
	for candidate in "$(command -v uv 2>/dev/null)" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" \
		/opt/homebrew/bin/uv /usr/local/bin/uv; do
		if [ -n "$candidate" ] && [ -x "$candidate" ]; then
			printf '%s\n' "$candidate"
			return 0
		fi
	done
	return 1
}

lock_held=""
claim_lock() {
	lock="$data/install.lock"
	waited=0
	while ! mkdir "$lock" 2>/dev/null; do
		# A lock left behind by a killed session expires.
		if [ -n "$(find "$lock" -prune -mmin +20 2>/dev/null)" ]; then
			rmdir "$lock" 2>/dev/null
			continue
		fi
		[ "$waited" -ge "${TRUTHSTONE_INSTALL_WAIT:-240}" ] && return 1
		sleep 1
		waited=$((waited + 1))
	done
	lock_held=1
	trap 'rmdir "$lock" 2>/dev/null' EXIT HUP INT TERM
	return 0
}

release_lock() {
	[ -n "$lock_held" ] && rmdir "$lock" 2>/dev/null
	lock_held=""
	trap - EXIT HUP INT TERM
}

# Install (or upgrade to) the runtime named by $want into "$data/runtime".
install_runtime() {
	if ! uv=$(find_uv); then
		say "$PRODUCT is not active: it installs its runtime with uv, and uv was not found. Install uv with:  $UV_INSTALL  — then start a new Claude Code session. Until then this session is unguarded and nothing else changes."
		return 1
	fi
	case $want in
	git+*)
		if ! command -v git >/dev/null 2>&1; then
			say "$PRODUCT is not active: it installs its runtime from GitHub with git, and git was not found. Install git (macOS: xcode-select --install), then start a new Claude Code session. Until then this session is unguarded and nothing else changes."
			return 1
		fi
		;;
	esac
	mkdir -p "$data" 2>/dev/null || return 1
	if ! claim_lock; then
		say "$PRODUCT is still being installed by another session, so this session is unguarded. It will be active in your next session."
		return 1
	fi
	# Another session may have finished the same install while this one waited.
	if read_ready && [ "$spec" = "$want" ]; then
		release_lock
		return 0
	fi
	previous=""
	[ -r "$data/runtime.ready" ] && previous=1
	log="$data/install.log"
	rm -f "$data/runtime.ready"
	venv="$data/runtime"
	editable=""
	case $want in
	/* | ./* | ../* | "~"*) editable=1 ;; # a local checkout: developing Truthstone itself
	esac
	{
		printf '%s installing %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$want"
		"$uv" venv --quiet --allow-existing --python '>=3.12' "$venv" &&
			"$uv" pip install --quiet --python "$venv/bin/python" \
				--reinstall-package "$PACKAGE" ${editable:+--editable} "$want" &&
			"$venv/bin/python" -I -c "import $MODULE.forward as m; print(m.__file__)" >"$data/forward.src"
	} </dev/null >>"$log" 2>&1
	status=$?
	src=$(cat "$data/forward.src" 2>/dev/null)
	rm -f "$data/forward.src"
	if [ "$status" -ne 0 ] || [ -z "$src" ] || [ ! -r "$src" ]; then
		release_lock
		say "$PRODUCT could not install its runtime ($want), so this session is unguarded. The installer's output is in $log — run /truthstone:doctor for help."
		return 1
	fi
	# A link, swapped in by rename: the per-tool hooks may be reading it right now.
	ln -sf "$src" "$data/forward.py.new" && mv -f "$data/forward.py.new" "$data/forward.py"
	printf '%s\n' "$want" >"$data/runtime.ready.new" && mv -f "$data/runtime.ready.new" "$data/runtime.ready"
	release_lock
	read_ready || return 1
	[ -n "$previous" ] && restart="--restart-daemon"
	return 0
}

case $kind in
prompt)
	off && exit 0
	read_ready || exit 0
	exec "$py" -I -m "$MODULE.plugin" prompt
	;;
session-start)
	off && exit 0
	[ -n "$data" ] || exit 0
	if ! want=$(want_spec); then
		say "$PRODUCT could not read its plugin version, so this session is unguarded. Reinstall the plugin."
		exit 0
	fi
	restart=""
	if ! { read_ready && [ "$spec" = "$want" ]; }; then
		install_runtime || exit 0
	fi
	exec "$py" -I -m "$MODULE.plugin" session-start $restart
	;;
cli | plugin)
	data=${2:-}
	[ $# -ge 2 ] && shift 2
	if ! read_ready; then
		printf '%s runtime is not installed yet: it installs at the start of a Claude Code session.\n' "$PRODUCT"
		[ -r "$data/install.log" ] && printf 'Last installer output (%s):\n' "$data/install.log" &&
			tail -n 20 "$data/install.log"
		find_uv >/dev/null || printf 'uv was not found. Install it with:  %s\n' "$UV_INSTALL"
		exit 0
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
	;;
*)
	exit 0
	;;
esac
