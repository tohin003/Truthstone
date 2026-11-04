"""The Codex plugin's identity, and the generator for its machine-read files.

Every user-facing identifier of the Codex plugin lives in the constants below: the plugin
and marketplace names, the display name, the runtime's command and the install source. The
files Codex reads are *generated* from them, so a rename is a one-line change followed by

    python -m agentguard.adapters.codex.plugin --write

and ``tests/test_codex_plugin.py`` fails until the checked-in files match.

Generated (do not edit by hand):

* ``plugins/agentguard/.codex-plugin/plugin.json`` — manifest, incl. the listing metadata;
* ``plugins/agentguard/hooks/hooks.json`` — the hooks (same specs as
  ``agentguard install codex``, see ``install.HOOK_SPECS``);
* ``plugins/agentguard/hooks/agentguard-hook.sh`` — the launcher every hook runs;
* the ``agentguard`` entry of ``.agents/plugins/marketplace.json`` (other entries in that
  file belong to other plugins and are preserved).

Hand-written: ``skills/agentguard/SKILL.md`` and ``assets/*.svg``.

Why the plugin is this thin
---------------------------
Codex binds hook trust to the plugin's *contents*: every file under the plugin root is
hashed, and any change forces the developer to review the hooks again
(``codex-rs/hooks/src/engine/plugin_fingerprint.rs``). So the plugin carries no logic that
evolves. Its hooks run a POSIX launcher that only locates the AgentGuard runtime — an
installed ``agentguard-codex-hook``, or a private copy it installs once into Codex's
per-plugin data directory — and AgentGuard upgrades never touch the plugin.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agentguard.adapters.codex.install import build_hooks

# -- identity: change these, then regenerate ---------------------------------------
PLUGIN_NAME = "agentguard"
MARKETPLACE_NAME = "agentguard"
DISPLAY_NAME = "AgentGuard"
DEVELOPER_NAME = "AgentGuard"
REPOSITORY_URL = "https://github.com/tohin003/AgentGuard"
LICENSE = "Apache-2.0"
CATEGORY = "Developer Tools"
# The runtime the hooks call, and where the launcher installs it from when it is missing.
# "Works today" source: the public Git repository, pinned to the release tag of this very
# plugin version. An unpinned source would install whatever the default branch holds at the
# moment and run it on every tool call, which no one approved; Codex's hook trust covers the
# plugin's files, so pinning the tag in the launcher puts every runtime version change through
# that review. Releases must push the tag `v<version>` (see docs/CODEX.md). Once on PyPI this
# becomes the package spec, e.g. "agentguard==0.1.0".
RUNTIME_COMMAND = "agentguard-codex-hook"


def runtime_source(version: str | None = None) -> str:
    return f"git+{REPOSITORY_URL}@v{plugin_version(version)}"

PLUGIN_DIR = Path("plugins") / PLUGIN_NAME
MARKETPLACE_FILE = Path(".agents") / "plugins" / "marketplace.json"
LAUNCHER = "hooks/agentguard-hook.sh"

# No real pages exist yet. These resolve to clearly-labelled placeholder sections in
# docs/CODEX.md and are listed as open items there.
PRIVACY_POLICY_URL = f"{REPOSITORY_URL}/blob/master/docs/CODEX.md#placeholder-privacy-policy"
TERMS_OF_SERVICE_URL = f"{REPOSITORY_URL}/blob/master/docs/CODEX.md#placeholder-terms-of-service"

SHORT_DESCRIPTION = "Evidence checks for agent work"
DESCRIPTION = (
    "Deterministic, LLM-free reliability layer for Codex. It grounds the agent's claims in "
    "repository evidence, sizes planning to the task, watches scope, and holds an unverified "
    "'done' until tests back it. Silent unless it has evidence."
)
LONG_DESCRIPTION = (
    "AgentGuard sits beside Codex through lifecycle hooks and checks what the agent is about "
    "to do against the repository itself: symbols that do not exist, edits that wander far "
    "outside the task, irreversible shell commands, and a finished turn whose changes no test "
    "has exercised. When it finds evidence of a problem it hands the evidence back to Codex as "
    "a challenge, so the agent's own reasoning fixes it. Otherwise it says nothing.\n\n"
    "It has no model of its own and makes no network calls: everything runs in a local daemon "
    "on 127.0.0.1, with decisions recorded under ~/.agentguard. It never grants permissions — "
    "it can only stay silent, object, or ask for your confirmation — and if it is unavailable "
    "Codex simply continues unguarded.\n\n"
    "Requires the AgentGuard runtime (Python 3.12+). If it is not installed, the plugin installs "
    "a private copy with uv on first use, or tells you how to install it. Codex runs plugin "
    "hooks only after you review and trust them in /hooks. Works in the Codex CLI and in local "
    "threads of the ChatGPT desktop app; hooks do not run in the IDE extension, web, mobile or "
    "cloud tasks."
)
DEFAULT_PROMPTS = (
    "Explain why AgentGuard blocked my last action and how to resolve it",
    "Check whether AgentGuard is guarding this repository and fix the setup",
    "Summarize what AgentGuard has caught in this project this week",
)
CAPABILITIES = ("Read",)
BRAND_COLOR = "#0F766E"
KEYWORDS = (
    "reliability",
    "guardrails",
    "hooks",
    "verification",
    "testing",
    "evidence",
    "scope",
    "code-review",
)
SKILLS_DIR = "./skills/"
LOGO = "./assets/agentguard-logo.svg"
LOGO_DARK = "./assets/agentguard-logo-dark.svg"
COMPOSER_ICON = "./assets/agentguard-icon.svg"


def plugin_version(version: str | None = None) -> str:
    """PEP 440 package version -> the SemVer string the plugin manifest carries."""
    if version is None:
        from agentguard import __version__ as version
    for marker, label in ((".dev", "dev"), ("rc", "rc"), ("a", "alpha"), ("b", "beta")):
        head, sep, tail = version.partition(marker)
        if sep and tail.isdigit() and head and head[-1].isdigit():
            return f"{head}-{label}.{tail}"
    return version


RUNTIME_SOURCE = runtime_source()
INSTALL_HINT = f"uv tool install {RUNTIME_SOURCE}"


def launcher_command(spec_arg: str) -> str:
    # `${PLUGIN_ROOT}` is substituted by Codex before the shell sees it; the hook's trust
    # hash is computed over this unsubstituted form, so it is stable across install paths.
    return f'/bin/sh "${{PLUGIN_ROOT}}/{LAUNCHER}" {spec_arg}'


def hooks_document() -> dict[str, Any]:
    return {
        "description": f"{DISPLAY_NAME}: reliability checks for Codex. Generated; see {REPOSITORY_URL}.",
        "hooks": build_hooks(lambda spec: launcher_command(spec.arg)),
    }


def manifest(version: str | None = None) -> dict[str, Any]:
    return {
        "name": PLUGIN_NAME,
        "version": plugin_version(version),
        "description": DESCRIPTION,
        "author": {"name": DEVELOPER_NAME, "url": REPOSITORY_URL},
        "homepage": REPOSITORY_URL,
        "repository": REPOSITORY_URL,
        "license": LICENSE,
        "keywords": list(KEYWORDS),
        "skills": SKILLS_DIR,
        "hooks": "./hooks/hooks.json",
        # Hooks call local programs: desktop-only, never a cloud-only listing.
        "requires_local_executor": True,
        "interface": {
            "displayName": DISPLAY_NAME,
            "shortDescription": SHORT_DESCRIPTION,
            "longDescription": LONG_DESCRIPTION,
            "developerName": DEVELOPER_NAME,
            "category": CATEGORY,
            "capabilities": list(CAPABILITIES),
            "websiteURL": REPOSITORY_URL,
            "privacyPolicyURL": PRIVACY_POLICY_URL,
            "termsOfServiceURL": TERMS_OF_SERVICE_URL,
            "defaultPrompt": list(DEFAULT_PROMPTS),
            "brandColor": BRAND_COLOR,
            "composerIcon": COMPOSER_ICON,
            "logo": LOGO,
            "logoDark": LOGO_DARK,
            "screenshots": [],
        },
    }


def marketplace_entry() -> dict[str, Any]:
    return {
        "name": PLUGIN_NAME,
        "source": {"source": "local", "path": f"./{PLUGIN_DIR.as_posix()}"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": CATEGORY,
    }


def marketplace_document(existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Upsert our entry; every other plugin entry in the marketplace is left as it was."""
    doc = dict(existing or {})
    doc["name"] = MARKETPLACE_NAME
    doc.setdefault("interface", {"displayName": DISPLAY_NAME})
    others = [
        entry
        for entry in doc.get("plugins") or []
        if not (isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME)
    ]
    doc["plugins"] = [marketplace_entry(), *others]
    return doc


LAUNCHER_TEMPLATE = """#!/bin/sh
# {display} for Codex: hook launcher. GENERATED by agentguard.adapters.codex.plugin -- do not edit.
#
# Codex runs every {display} hook as:  /bin/sh "${{PLUGIN_ROOT}}/{launcher}" <event>
# with the hook payload on stdin. This script only finds the {display} runtime and hands the
# payload to it; all logic lives in the runtime, so upgrading {display} never changes this
# plugin (Codex makes you re-trust a plugin's hooks whenever any of its files change).
#
# Lookup order: $AGENTGUARD_CODEX_HOOK, then `{command}` on PATH, then a private copy in
# Codex's per-plugin data directory ($PLUGIN_DATA), which the session-start hook installs
# with uv on first use (set AGENTGUARD_NO_BOOTSTRAP=1 to prevent that).
#
# It always exits 0. Codex reads exit code 2 as "block this", and a launcher problem must
# never block the developer's work.

event="${{1:-}}"
case "${{AGENTGUARD_DISABLE:-}}" in 1|true|TRUE|True|yes|on) exit 0 ;; esac

runtime_source="${{AGENTGUARD_SOURCE:-{source}}}"
private="${{PLUGIN_DATA:-}}/runtime"
runner=""
if [ -n "${{AGENTGUARD_CODEX_HOOK:-}}" ] && [ -x "$AGENTGUARD_CODEX_HOOK" ]; then
  runner="$AGENTGUARD_CODEX_HOOK"
elif command -v {command} >/dev/null 2>&1; then
  runner="{command}"
elif [ -n "${{PLUGIN_DATA:-}}" ] && [ -x "$private/bin/{command}" ]; then
  runner="$private/bin/{command}"
fi

if [ "$event" = "session-start" ] && [ -n "${{PLUGIN_DATA:-}}" ] && [ -z "${{AGENTGUARD_NO_BOOTSTRAP:-}}" ] \\
  && [ "$runner" = "$private/bin/{command}" -o -z "$runner" ] \\
  && [ "$(cat "$private/source" 2>/dev/null)" != "$runtime_source" ] && command -v uv >/dev/null 2>&1; then
  # Install (or re-install, when the source changed) a private runtime. Never onto PATH,
  # never inside the plugin root. Output goes to a log, not to Codex.
  mkdir -p "$private" 2>/dev/null
  if UV_TOOL_DIR="$private/tools" UV_TOOL_BIN_DIR="$private/bin" \\
    uv tool install --quiet --reinstall "$runtime_source" </dev/null >>"$private/install.log" 2>&1; then
    printf '%s' "$runtime_source" >"$private/source"
  fi
  [ -x "$private/bin/{command}" ] && runner="$private/bin/{command}"
fi

if [ -z "$runner" ]; then
  if [ "$event" = "session-start" ]; then
    printf '%s\\n' '{notice}'
  fi
  exit 0
fi

"$runner" "$event"
exit 0
"""


def missing_runtime_notice() -> str:
    """The JSON the launcher prints at session start when it has no runtime to call."""
    message = (
        f"{DISPLAY_NAME} is installed as a Codex plugin, but its runtime was not found, so this "
        f"session is UNGUARDED. Install it with: {INSTALL_HINT}  (or put {RUNTIME_COMMAND} on "
        "PATH), then start a new session."
    )
    return json.dumps({"systemMessage": message})


def launcher_script() -> str:
    notice = missing_runtime_notice()
    if "'" in notice:  # it is embedded in a single-quoted shell string
        raise ValueError("the missing-runtime notice must not contain a single quote")
    return LAUNCHER_TEMPLATE.format(
        notice=notice,
        display=DISPLAY_NAME,
        launcher=LAUNCHER,
        command=RUNTIME_COMMAND,
        source=RUNTIME_SOURCE,
        hint=INSTALL_HINT,
    )


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def generated_files(repo_root: Path) -> dict[Path, str]:
    """Files this module owns outright -> their exact expected content."""
    root = repo_root / PLUGIN_DIR
    return {
        root / ".codex-plugin" / "plugin.json": _dump(manifest()),
        root / "hooks" / "hooks.json": _dump(hooks_document()),
        root / LAUNCHER: launcher_script(),
    }


def _read_marketplace(repo_root: Path) -> dict[str, Any] | None:
    try:
        data = json.loads((repo_root / MARKETPLACE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def marketplace_is_current(repo_root: Path) -> bool:
    """The marketplace is shared with other plugins, so only *our* part is compared."""
    data = _read_marketplace(repo_root)
    if data is None or data.get("name") != MARKETPLACE_NAME:
        return False
    ours = [p for p in data.get("plugins") or [] if isinstance(p, dict) and p.get("name") == PLUGIN_NAME]
    return ours == [marketplace_entry()]


def check(repo_root: Path) -> list[str]:
    """Paths whose checked-in content differs from what would be generated."""
    stale = []
    for path, content in generated_files(repo_root).items():
        try:
            current = path.read_text(encoding="utf-8")
        except OSError:
            current = None
        if current != content:
            stale.append(str(path.relative_to(repo_root)))
    if not marketplace_is_current(repo_root):
        stale.append(str(MARKETPLACE_FILE))
    return stale


def write(repo_root: Path) -> list[str]:
    written = []
    for path, content in generated_files(repo_root).items():
        try:
            if path.read_text(encoding="utf-8") == content:
                continue
        except OSError:
            pass
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if path.suffix == ".sh":
            path.chmod(0o755)
        written.append(str(path.relative_to(repo_root)))
    if not marketplace_is_current(repo_root):
        market = repo_root / MARKETPLACE_FILE
        market.parent.mkdir(parents=True, exist_ok=True)
        market.write_text(_dump(marketplace_document(_read_marketplace(repo_root))), encoding="utf-8")
        written.append(str(MARKETPLACE_FILE))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--write", action="store_true", help="regenerate the plugin files")
    args = parser.parse_args(argv)
    if args.write:
        for path in write(args.root):
            print(f"wrote {path}")
        return 0
    stale = check(args.root)
    for path in stale:
        print(f"stale: {path}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())

