#!/bin/sh
# Truthstone: the SessionStart hook. This is the plugin's only install step.
#
#   sh "${CLAUDE_PLUGIN_ROOT}/scripts/session-start.sh"
#
# 1. The project gate. Outside a git work tree it does nothing at all: no install, no
#    daemon, no output.
# 2. The runtime. Truthstone's logic is a Python package that is not part of this
#    plugin. The first time, and after each plugin update, this script installs it into
#    the plugin's data directory with uv:
#        uv venv "$CLAUDE_PLUGIN_DATA/runtime"    (uv downloads CPython 3.12+ only if no
#                                                  usable Python is present)
#        uv pip install git+https://github.com/tohin003/Truthstone@v<plugin version>
#    The second command fetches that release from GitHub and its dependencies from the
#    Python Package Index. These are the plugin's only downloads, and nothing is ever
#    uploaded. The installer's output goes to "$CLAUDE_PLUGIN_DATA/install.log".
#    With TRUTHSTONE_NO_BOOTSTRAP=1 it downloads and installs nothing. It uses a runtime
#    you installed yourself (uv tool install ..., see README.md), or says how to get one.
# 3. It starts Truthstone's daemon on 127.0.0.1, checks for a duplicate settings-based
#    install, and forwards the event (python -m truthstone.adapters.claude_code.plugin).
#
# Contract with Claude Code: exit 0, and print nothing unless Truthstone has something to
# say, as a JSON systemMessage that the developer sees and Claude does not. Never exit 2:
# that would block the agent, and a problem in Truthstone is never a reason to. If the
# runtime cannot be installed, the session runs unguarded and the developer is told
# once, here, what to do.

# rename-tool: keep-begin former-settings (settings under a former product name still apply)
[ -n "${TRUTHSTONE_DISABLE:-}" ] || [ -z "${AGENTGUARD_DISABLE+x}" ] || TRUTHSTONE_DISABLE=$AGENTGUARD_DISABLE
[ -n "${TRUTHSTONE_INSTALL_WAIT:-}" ] || [ -z "${AGENTGUARD_INSTALL_WAIT+x}" ] || TRUTHSTONE_INSTALL_WAIT=$AGENTGUARD_INSTALL_WAIT
[ -n "${TRUTHSTONE_NO_BOOTSTRAP:-}" ] || [ -z "${AGENTGUARD_NO_BOOTSTRAP+x}" ] || TRUTHSTONE_NO_BOOTSTRAP=$AGENTGUARD_NO_BOOTSTRAP
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
UV_HELP="https://docs.astral.sh/uv/getting-started/installation/"
# ---------------------------------------------------------------------------------------

root=${CLAUDE_PLUGIN_ROOT:-$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)}
data=${CLAUDE_PLUGIN_DATA:-}

off() {
	case ${TRUTHSTONE_DISABLE:-} in
	1 | [Tt][Rr][Uu][Ee] | [Yy][Ee][Ss] | [Oo][Nn]) return 0 ;;
	esac
	return 1
}

# The no-download opt-out: any non-empty value, as in the Codex plugin's launcher.
no_bootstrap() {
	[ -n "${TRUTHSTONE_NO_BOOTSTRAP:-}" ]
}

# The project gate, the same test as in scripts/hook.sh: 0 when $1 is inside a git work
# tree (it, or a folder above it, has a .git entry).
in_work_tree() {
	d=$1
	case $d in /*) ;; *) return 1 ;; esac
	while :; do
		[ -e "$d/.git" ] && return 0
		[ -n "$d" ] || return 1
		d=${d%/*}
	done
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

# Swap in the forwarder link and the ready marker, in that order. The forwarder is a
# link replaced by rename, because the per-tool hooks may be reading it right now.
mark_ready() {
	ln -sf "$1" "$data/forward.py.new" && mv -f "$data/forward.py.new" "$data/forward.py" &&
		printf '%s\n' "$2" >"$data/runtime.ready.new" && mv -f "$data/runtime.ready.new" "$data/runtime.ready"
}

# Install (or upgrade to) the runtime named by $want into "$data/runtime".
install_runtime() {
	if ! uv=$(find_uv); then
		say "$PRODUCT is not active: it installs its runtime with uv, and uv was not found. Install uv ($UV_HELP), then start a new Claude Code session. Until then this session is unguarded and nothing else changes."
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
	# A link to a runtime the developer installed (TRUTHSTONE_NO_BOOTSTRAP): drop the
	# link, never touch what it points to.
	[ -L "$venv" ] && rm -f "$venv"
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
	mark_ready "$src" "$want"
	release_lock
	read_ready || return 1
	[ -n "$previous" ] && restart="--restart-daemon"
	return 0
}

# The virtualenv of a runtime the developer installed: `truthstone` on PATH or in
# ~/.local/bin (uv tool install, pipx install), whose first line names its interpreter.
installed_runtime() {
	exe=$(command -v "$PACKAGE" 2>/dev/null) || exe=""
	[ -n "$exe" ] || exe="$HOME/.local/bin/$PACKAGE"
	[ -f "$exe" ] && [ -r "$exe" ] || return 1
	IFS= read -r line <"$exe" || return 1
	case $line in "#!/"*) ;; *) return 1 ;; esac
	interpreter=${line#??}
	interpreter=${interpreter%% *}
	found=${interpreter%/bin/*}
	[ -x "$found/bin/python" ] && [ -r "$found/pyvenv.cfg" ] || return 1
	printf '%s\n' "$found"
}

# TRUTHSTONE_NO_BOOTSTRAP: download and install nothing. Link the runtime the developer
# installed into the data directory, where the other hooks look for it.
use_installed_runtime() {
	if ! found=$(installed_runtime); then
		say "$PRODUCT is not active: TRUTHSTONE_NO_BOOTSTRAP is set, so the plugin downloads and installs nothing, and no $PRODUCT runtime was found ($PACKAGE on PATH or in ~/.local/bin). Install it yourself with:  uv tool install $want  — then start a new Claude Code session. Until then this session is unguarded and nothing else changes."
		return 1
	fi
	manual="manual:$found"
	if read_ready && [ "$spec" = "$manual" ]; then
		return 0
	fi
	src=$("$found/bin/python" -I -c "import $MODULE.forward as m; print(m.__file__)" 2>/dev/null)
	if [ -z "$src" ] || [ ! -r "$src" ]; then
		say "$PRODUCT is not active: the runtime installed in $found has no Claude Code support. Upgrade it with:  uv tool install --reinstall $want  — then start a new Claude Code session. Until then this session is unguarded and nothing else changes."
		return 1
	fi
	mkdir -p "$data" 2>/dev/null || return 1
	if ! claim_lock; then
		say "$PRODUCT is being set up by another session, so this session is unguarded. It will be active in your next session."
		return 1
	fi
	previous=""
	[ -r "$data/runtime.ready" ] && previous=1
	rm -f "$data/runtime.ready"
	if [ -L "$data/runtime" ]; then
		rm -f "$data/runtime"
	elif [ -e "$data/runtime" ]; then
		rm -rf "$data/runtime" # a runtime this plugin installed earlier
	fi
	ln -s "$found" "$data/runtime" && mark_ready "$src" "$manual"
	release_lock
	read_ready || return 1
	[ -n "$previous" ] && restart="--restart-daemon"
	return 0
}

off && exit 0
in_work_tree "$PWD" || in_work_tree "${CLAUDE_PROJECT_DIR:-}" || exit 0
[ -n "$data" ] || exit 0
if ! want=$(want_spec); then
	say "$PRODUCT could not read its plugin version, so this session is unguarded. Reinstall the plugin."
	exit 0
fi
restart=""
if no_bootstrap; then
	use_installed_runtime || exit 0
elif ! { read_ready && [ "$spec" = "$want" ]; }; then
	install_runtime || exit 0
fi
exec "$py" -I -m "$MODULE.plugin" session-start $restart
