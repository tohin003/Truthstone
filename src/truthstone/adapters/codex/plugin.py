"""The Codex plugin's identity, and the generator for its machine-read files.

Every user-facing identifier of the Codex plugin lives in the constants below: the plugin
and marketplace names, the display name, the runtime's command and the install source. The
files Codex reads are *generated* from them, so a rename is a one-line change followed by

    python -m truthstone.adapters.codex.plugin --write

and ``tests/test_codex_plugin.py`` fails until the checked-in files match.

Generated (do not edit by hand):

* ``plugins/truthstone/.codex-plugin/plugin.json`` — manifest, incl. the listing metadata;
* ``plugins/truthstone/hooks/hooks.json`` — the hooks (same specs as
  ``truthstone install codex``, see ``install.HOOK_SPECS``);
* ``plugins/truthstone/hooks/truthstone-hook.sh`` — the launcher every hook runs;
* ``plugins/truthstone/README.md`` — what the plugin runs, sends, fetches and stores;
* ``plugins/truthstone/SECURITY.md`` — the security contract and how to report a problem;
* ``plugins/truthstone/LICENSE`` — a copy of the repository's Apache-2.0 licence;
* the ``truthstone`` entry of ``.agents/plugins/marketplace.json`` (other entries in that
  file belong to other plugins and are preserved).

Hand-written: ``skills/truthstone/SKILL.md`` and ``assets/*.svg``.

Why the plugin is this thin
---------------------------
Codex binds hook trust to the plugin's *contents*: every file under the plugin root is
hashed, and any change forces the developer to review the hooks again
(``codex-rs/hooks/src/engine/plugin_fingerprint.rs``). So the plugin carries no logic that
evolves. Its hooks run a POSIX launcher that only locates the Truthstone runtime — an
installed ``truthstone-codex-hook``, or a private copy it installs once into Codex's
per-plugin data directory — and Truthstone upgrades never touch the plugin.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from truthstone import names
from truthstone.adapters.codex.install import build_hooks

# -- identity: change these, then regenerate ---------------------------------------
PLUGIN_NAME = "truthstone"
MARKETPLACE_NAME = "truthstone"
DISPLAY_NAME = "Truthstone"
# The publisher, as the publisher asked to be listed.
DEVELOPER_NAME = "Tohin Majumder"
DEVELOPER_URL = "https://github.com/tohin003"
SUPPORT_EMAIL = "tohin1400@gmail.com"
REPOSITORY_URL = "https://github.com/tohin003/Truthstone"
LICENSE = "Apache-2.0"
CATEGORY = "Developer Tools"
# The runtime the hooks call, and where the launcher installs it from when it is missing.
# "Works today" source: the public Git repository, pinned to the release tag of this very
# plugin version. An unpinned source would install whatever the default branch holds at the
# moment and run it on every tool call, which no one approved; Codex's hook trust covers the
# plugin's files, so pinning the tag in the launcher puts every runtime version change through
# that review. Releases must push the tag `v<version>` (see docs/CODEX.md). Once on PyPI this
# becomes the package spec, e.g. "truthstone==0.1.0".
RUNTIME_COMMAND = "truthstone-codex-hook"


def runtime_source(version: str | None = None) -> str:
    return f"git+{REPOSITORY_URL}@v{plugin_version(version)}"

PLUGIN_DIR = Path("plugins") / PLUGIN_NAME
MARKETPLACE_FILE = Path(".agents") / "plugins" / "marketplace.json"
LAUNCHER = "hooks/truthstone-hook.sh"

# The repository's own legal pages (docs/legal), as plain GitHub file URLs.
PRIVACY_POLICY_URL = f"{REPOSITORY_URL}/blob/master/docs/legal/PRIVACY.md"
TERMS_OF_SERVICE_URL = f"{REPOSITORY_URL}/blob/master/docs/legal/TERMS.md"
SUPPORT_URL = f"{REPOSITORY_URL}/blob/master/docs/legal/SUPPORT.md"

SHORT_DESCRIPTION = "Evidence checks for agent work"
DESCRIPTION = (
    "Deterministic, LLM-free reliability layer for Codex. It grounds the agent's claims in "
    "repository evidence, sizes planning to the task, watches scope, and holds an unverified "
    "'done' until tests back it. Silent unless it has evidence."
)
LONG_DESCRIPTION = (
    "Truthstone (previously named AgentGuard) sits beside Codex through lifecycle hooks and checks what the "
    "agent is about to do against the repository itself: symbols that do not exist, edits that wander far "
    "outside the task, irreversible shell commands, and a finished turn whose changes no test "
    "has exercised. When it finds evidence of a problem it hands the evidence back to Codex as "
    "a challenge, so the agent's own reasoning fixes it. Otherwise it says nothing.\n\n"
    "It has no model of its own and makes no network calls while it works: everything runs in a "
    "local daemon on 127.0.0.1, with decisions recorded under ~/.truthstone. It never grants "
    "permissions — it can only stay silent, object, or ask for your confirmation — and if it is "
    "unavailable Codex simply continues unguarded. It works only inside git repositories; "
    "elsewhere its hooks do nothing.\n\n"
    "Requires the Truthstone runtime (Python 3.12+). If it is not installed, the plugin installs "
    "a private copy with uv on first use, from the GitHub release that matches the plugin, or "
    "tells you how to install it; set TRUTHSTONE_NO_BOOTSTRAP=1 to skip that download. Codex "
    "runs plugin hooks only after you review and trust them in /hooks. Works in the Codex CLI and "
    "in local threads of the ChatGPT desktop app; hooks do not run in the IDE extension, web, "
    "mobile or cloud tasks."
)
DEFAULT_PROMPTS = (
    "Explain why Truthstone blocked my last action and how to resolve it",
    "Check whether Truthstone is guarding this repository and fix the setup",
    "Summarize what Truthstone has caught in this project this week",
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
LOGO = "./assets/truthstone-logo.svg"
LOGO_DARK = "./assets/truthstone-logo-dark.svg"
COMPOSER_ICON = "./assets/truthstone-icon.svg"


def plugin_version(version: str | None = None) -> str:
    """PEP 440 package version -> the SemVer string the plugin manifest carries."""
    if version is None:
        from truthstone import __version__ as version
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
        "author": {"name": DEVELOPER_NAME, "email": SUPPORT_EMAIL, "url": DEVELOPER_URL},
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
            "supportURL": SUPPORT_URL,
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
# {display} for Codex: hook launcher. GENERATED by truthstone.adapters.codex.plugin -- do not edit.
#
# Codex runs every {display} hook as:  /bin/sh "${{PLUGIN_ROOT}}/{launcher}" <event>
# with the hook payload on stdin. This script only finds the {display} runtime and hands the
# payload to it; all logic lives in the runtime, so upgrading {display} never changes this
# plugin (Codex makes you re-trust a plugin's hooks whenever any of its files change).
#
# Lookup order: $TRUTHSTONE_CODEX_HOOK, then `{command}` on PATH, then a private copy in
# Codex's per-plugin data directory ($PLUGIN_DATA), which the session-start hook installs
# with uv on first use (set TRUTHSTONE_NO_BOOTSTRAP=1 to prevent that).
#
# It does nothing at all outside a git work tree, and when TRUTHSTONE_DISABLE is set.
# It always exits 0. Codex reads exit code 2 as "block this", and a launcher problem must
# never block the developer's work.

{former_settings}event="${{1:-}}"
case "${{TRUTHSTONE_DISABLE:-}}" in 1|true|TRUE|True|yes|on) exit 0 ;; esac

# The project gate. {display} guards work in git repositories only: unless the session's
# directory is inside a git work tree (it, or a folder above it, has a .git entry), do
# nothing: no runtime, no install, no output.
d="$PWD"
case "$d" in /*) ;; *) exit 0 ;; esac
until [ -e "$d/.git" ]; do
  [ -n "$d" ] || exit 0
  d="${{d%/*}}"
done

runtime_source="${{TRUTHSTONE_SOURCE:-{source}}}"
private="${{PLUGIN_DATA:-}}/runtime"
runner=""
if [ -n "${{TRUTHSTONE_CODEX_HOOK:-}}" ] && [ -x "$TRUTHSTONE_CODEX_HOOK" ]; then
  runner="$TRUTHSTONE_CODEX_HOOK"
elif command -v {command} >/dev/null 2>&1; then
  runner="{command}"
elif [ -n "${{PLUGIN_DATA:-}}" ] && [ -x "$private/bin/{command}" ]; then
  runner="$private/bin/{command}"
fi

if [ "$event" = "session-start" ] && [ -n "${{PLUGIN_DATA:-}}" ] && [ -z "${{TRUTHSTONE_NO_BOOTSTRAP:-}}" ] \\
  && {{ [ "$runner" = "$private/bin/{command}" ] || [ -z "$runner" ]; }} \\
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
    fields = {
        "notice": notice,
        "display": DISPLAY_NAME,
        "launcher": LAUNCHER,
        "command": RUNTIME_COMMAND,
        "source": RUNTIME_SOURCE,
        "hint": INSTALL_HINT,
    }
    script = LAUNCHER_TEMPLATE.format(former_settings="", **fields)
    # After a product rename, settings made under the former name keep working; until then
    # this is empty and the launcher (and so the plugin's trust hash) is unchanged.
    former_settings = names.shell_fallbacks(script)
    return LAUNCHER_TEMPLATE.format(former_settings=former_settings, **fields) if former_settings else script


README_TEMPLATE = """# {display} for Codex

{display}{previously} is a local, deterministic reliability layer for Codex. It has no
model of its own. Through Codex lifecycle hooks it checks what the agent is about to do
against your repository: symbols that do not exist, edits that wander far outside the task,
irreversible shell commands, and a finished turn whose changes no test has exercised. When
it finds evidence of a problem, it hands that evidence back to Codex so the agent's own
reasoning can fix it. Otherwise it says nothing. It never grants a permission, and if it is
unavailable, Codex simply continues unguarded.

It works only inside git repositories. Elsewhere its hooks do nothing at all.

Publisher: {developer} ({email}). Licence: Apache-2.0. Source: {repo}

## Install

    codex plugin marketplace add {slug}
    codex plugin add {plugin}@{marketplace}

Then trust the hooks. Codex runs a plugin's hooks only after you review them: run `/hooks`
in the Codex CLI, or use **Review hooks** in the ChatGPT desktop app. Codex asks again
whenever any file in the plugin changes.

It runs in the Codex CLI and in local threads of the ChatGPT desktop app. Codex does not run
plugin hooks in the Codex IDE extension, in ChatGPT on the web or on mobile, or in cloud
tasks, so {display} does nothing there.

## What it runs, sends and fetches

All of it runs on your machine, with your user permissions. Every hook runs one short POSIX
script, `{launcher}`, with the event's name. The script exits at once, doing nothing, when
the session's directory is not inside a git work tree, or when `TRUTHSTONE_DISABLE=1` is
set. Otherwise it hands the event to the {display} runtime: `$TRUTHSTONE_CODEX_HOOK` if you
set it, else `{command}` on your `PATH`, else a private copy in the plugin's data folder.

- **Session start** (`SessionStart`): if no runtime is found, installs the private copy
  (below). Starts {display}'s local helper process, and says once if the session is
  unguarded.
- **Every prompt you send** (`UserPromptSubmit`): records the task, and may add a short
  planning note to Codex's context.
- **Before shell commands and patches** (`PreToolUse` on `Bash` and `apply_patch`): checks
  the call against your repository and the task. Usually it says nothing. Otherwise it hands
  Codex a challenge with its evidence. For an irreversible action it denies the call until
  you confirm, because Codex has no permission prompt that hooks can use.
- **After those calls** (`PostToolUse`): records what changed and any test results it can
  see.
- **End of each turn** (`Stop`): the completion gate. If files changed and no passing test
  run was seen, it holds the turn once, with the reason and the command to run.
- **Session end** (`SessionEnd`): closes the session record.

**The one-time download.** At session start, if no runtime is found, `uv` is available and
`TRUTHSTONE_NO_BOOTSTRAP` is not set, the script installs a private copy into the plugin's
data folder, never onto your `PATH`:

    uv tool install --reinstall {source}

That fetches this plugin's own release from GitHub, and the runtime's dependencies from the
Python Package Index; `uv` downloads a CPython 3.12 or later interpreter only if you have no
usable Python. The installer's output goes to `install.log` in that folder. It installs
again only when the plugin's pinned source changes. Once {display} is published on PyPI,
the runtime will come from there instead. Nothing else is downloaded, and nothing is ever
uploaded.

**No download.** Set `TRUTHSTONE_NO_BOOTSTRAP=1` and install the runtime yourself:

    {hint}

That puts `{command}` on your `PATH`, which the script uses first.

**The local helper process.** The runtime starts a small HTTP server that listens only on
127.0.0.1. It accepts a request only with a random bearer token, which {display} creates on
your machine and keeps in `~/.truthstone/daemon.json` with owner-only permissions. Hook
payloads go there and nowhere else. {display} has no server of its own anywhere, no
telemetry and no analytics. It does not read your Codex transcripts or other conversations.

**What reaches Codex.** When {display} has something to say, that text becomes part of your
Codex conversation, which Codex handles like everything else in the session.

## Your data

{display} keeps its records on your computer, in a SQLite database at
`~/.truthstone/truthstone.db` (or under `TRUTHSTONE_HOME` if you set it). Nothing is sent to
the publisher or to anyone else. It stores:

- each repository's path, and its remote address with any credentials removed;
- session records: identifiers, start and end times;
- task records: the first 2,000 characters of each prompt that starts a task, and the task
  details {display} extracted from it;
- tool calls and their inputs (shell commands, patches), with each text value shortened to
  200 characters and each record to 4,000 characters;
- {display}'s decisions and findings, with the files and lines it checked;
- which test commands ran, and a summary of their outcome;
- timings and counts that measure {display}'s own behaviour.

The helper process writes its own warnings and errors to `~/.truthstone/daemon.log`.

**How long it is kept.** {display} deletes old records automatically when a session ends,
at most once every six hours:

| Record | Kept for |
|---|---|
| Tool calls | 14 days |
| Decisions and their findings | 30 days |
| Test results | 60 days |
| Timings and counts | 90 days |
| Sessions and tasks, including the prompt text | 270 days after the session ends |

A session that never ended cleanly is not deleted automatically, so its session and task
records stay until you delete them. When the disk is nearly full, or the database outgrows
its size limit, all periods are cut to a quarter. You can change each period in
`~/.truthstone/config.toml`, and you can delete `~/.truthstone` at any time to erase
everything. A coming release is planned to store less prompt text. Full privacy policy:
{privacy}

## Switch it off

- **For one session:** start Codex with `TRUTHSTONE_DISABLE=1`. Every hook then exits at
  once without recording anything.
- **On this machine:** `truthstone off`, and `truthstone on` to resume. The `truthstone`
  command comes with the runtime: on your `PATH` if you installed it yourself, otherwise in
  the `bin` folder of the private copy.

## Uninstall

    codex plugin remove {plugin}@{marketplace}

Then delete `~/.truthstone` to remove {display}'s records, and the plugin's data folder
(`$CODEX_HOME/plugins/data/{plugin}-{marketplace}`, usually under `~/.codex`) if Codex left
it behind; it holds the private runtime. The helper process keeps running until you restart
your computer, or until you run `truthstone daemon stop`.

## Requirements

- The Codex CLI, or local threads of the ChatGPT desktop app.
- `uv` (https://docs.astral.sh/uv/getting-started/installation/) and `git`, unless you
  install the runtime yourself; Python 3.12 or later, which `uv` can provide.
- macOS or Linux. Windows is untested.

## Security

- **Never grants permissions.** {display} can stay silent, object, or hold an action for
  your confirmation. It never approves anything on your behalf.
- **Fails open.** If {display} is missing or broken, Codex works as if it were not
  installed. The script always exits 0, because Codex reads exit code 2 as "block this".
- **Runs no code from the repository it guards.** Its Python processes run isolated.
- **Reviewed by you.** Codex runs these hooks only after you trust them, and asks again
  after any change to this plugin's files.

Report a vulnerability privately through GitHub's private vulnerability reporting
({repo}/security), or by email to {email}. See `SECURITY.md`.

## Support and policies

- Questions and bugs: {repo}/issues, or {email}.
- Support: {support}
- Privacy policy: {privacy}
- Terms of use: {terms}
"""

SECURITY_TEMPLATE = """# Security policy

## Scope

This plugin runs code on your machine. Every hook runs `{launcher}`, a POSIX script that
does nothing outside a git work tree. Otherwise it hands the event to the {display} runtime:
an installed `{command}`, or a private copy that the session-start hook installs once with
`uv` into Codex's data folder for this plugin, from `{source}`. With
`TRUTHSTONE_NO_BOOTSTRAP=1` nothing is installed. The runtime talks only to its own daemon
on `127.0.0.1`, which authenticates every request with a bearer token stored owner-only
under `~/.truthstone`. Nothing is sent off the machine, and the plugin has no MCP servers.
`README.md` lists everything the plugin runs, sends, fetches and stores.

Codex runs these hooks only after you review and trust them in `/hooks`, and asks again
after any change to the plugin's files.

{display}'s safety contract, and so what counts as a vulnerability here:

- **It never grants permissions.** No hook output may approve a tool call on the user's
  behalf.
- **It fails open.** If {display} is broken or missing, Codex works as if it were not
  installed. It never blocks the agent because of its own failure, and the launcher never
  exits 2.
- **It never fails silently.** A session that is not guarded is told so.
- **It never runs code from the repository it guards.**
- **The daemon stays local.** It must be reachable only from `127.0.0.1`, and only with the
  token.
- **It does nothing outside a git work tree**, and installs nothing when told not to.

A break in any of these is a security issue. So is a way to reach or impersonate the daemon,
to read the token, or to make the launcher install something other than the pinned
{display} release.

## Reporting a vulnerability

Report vulnerabilities privately, not in a public issue:

- through GitHub's private vulnerability reporting for {repo}: open the **Security** tab and
  select **Report a vulnerability**; or
- by email to {developer}, {email}.

Other ways to reach the maintainer are listed at {support}.

## Supported versions

Only the latest release receives fixes. Update the plugin before you report a problem.
"""


def _previously() -> str:
    """The "(previously named X)" suffix after a rename, from the one registry of names."""
    return f" (previously named {names.FORMER[0][0]})" if names.FORMER else ""


def _document_fields() -> dict[str, str]:
    return {
        "display": DISPLAY_NAME,
        "previously": _previously(),
        "developer": DEVELOPER_NAME,
        "email": SUPPORT_EMAIL,
        "repo": REPOSITORY_URL,
        "slug": REPOSITORY_URL.removeprefix("https://github.com/"),
        "plugin": PLUGIN_NAME,
        "marketplace": MARKETPLACE_NAME,
        "launcher": LAUNCHER,
        "command": RUNTIME_COMMAND,
        "source": RUNTIME_SOURCE,
        "hint": INSTALL_HINT,
        "privacy": PRIVACY_POLICY_URL,
        "terms": TERMS_OF_SERVICE_URL,
        "support": SUPPORT_URL,
    }


def readme() -> str:
    """The plugin's README: everything it runs, sends, fetches and stores."""
    return README_TEMPLATE.format(**_document_fields())


def security_policy() -> str:
    return SECURITY_TEMPLATE.format(**_document_fields())


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def generated_files(repo_root: Path) -> dict[Path, str]:
    """Files this module owns outright -> their exact expected content."""
    root = repo_root / PLUGIN_DIR
    files = {
        root / ".codex-plugin" / "plugin.json": _dump(manifest()),
        root / "hooks" / "hooks.json": _dump(hooks_document()),
        root / LAUNCHER: launcher_script(),
        root / "README.md": readme(),
        root / "SECURITY.md": security_policy(),
    }
    licence = repo_root / "LICENSE"
    if licence.is_file():
        files[root / "LICENSE"] = licence.read_text(encoding="utf-8")
    return files


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

