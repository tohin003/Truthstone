"""The Codex plugin package: generated in sync, within listing limits, thin, and stable.

Codex re-verifies a plugin's whole directory on every hook run and makes users re-trust
the hooks after *any* change, so the last two tests here pin the hook declarations and the
plugin's content fingerprint. They fail on every change to the plugin — on purpose: the
fix is to update the pinned value, knowing that every user will be asked to review
Truthstone's hooks again.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

from tests.codex_trust import declaration_hashes, plugin_content_hash
from truthstone import __version__
from truthstone.adapters.codex import plugin
from truthstone.adapters.codex.install import HOOK_SPECS

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / plugin.PLUGIN_DIR
LAUNCHER = PLUGIN / plugin.LAUNCHER


def manifest() -> dict:
    return json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())


def hooks_file() -> dict:
    return json.loads((PLUGIN / "hooks" / "hooks.json").read_text())


class TestGenerated:
    def test_checked_in_files_match_the_generator(self):
        stale = plugin.check(REPO)
        assert stale == [], f"run: python -m truthstone.adapters.codex.plugin --write  ({stale})"

    def test_version_follows_the_package(self):
        assert manifest()["version"] == plugin.plugin_version(__version__)
        assert plugin.plugin_version("0.1.0.dev0") == "0.1.0-dev.0"
        assert plugin.plugin_version("1.2.0rc1") == "1.2.0-rc.1"
        assert plugin.plugin_version("1.2.0") == "1.2.0"

    def test_hooks_match_the_installer_specs(self):
        hooks = hooks_file()["hooks"]
        assert set(hooks) == {spec.event for spec in HOOK_SPECS}
        for spec in HOOK_SPECS:
            (group,) = hooks[spec.event]
            assert group.get("matcher") == spec.matcher
            (handler,) = group["hooks"]
            assert handler["command"] == f'/bin/sh "${{PLUGIN_ROOT}}/{plugin.LAUNCHER}" {spec.arg}'
            assert handler["timeout"] == spec.timeout


class TestManifest:
    def test_identity(self):
        data = manifest()
        assert data["name"] == plugin.PLUGIN_NAME
        assert data["license"] == "Apache-2.0"
        assert data["homepage"] == data["repository"] == "https://github.com/tohin003/Truthstone"
        assert data["author"] == {
            "name": "Tohin Majumder",
            "email": "tohin1400@gmail.com",
            "url": "https://github.com/tohin003",
        }
        assert data["interface"]["developerName"] == "Tohin Majumder"
        assert data["skills"] == "./skills/"
        assert data["hooks"] == "./hooks/hooks.json"
        assert data["requires_local_executor"] is True
        assert "mcpServers" not in data  # this design uses no MCP server

    def test_listing_metadata_is_within_the_published_limits(self):
        ui = manifest()["interface"]
        assert len(ui["displayName"]) <= 30
        assert len(ui["shortDescription"]) <= 30
        assert len(ui["longDescription"]) <= 4000
        assert len(ui["developerName"]) <= 80
        assert len(ui["capabilities"]) <= 20 and all(len(c) <= 120 for c in ui["capabilities"])
        prompts = ui["defaultPrompt"]
        assert 1 <= len(prompts) <= 3 and len(set(prompts)) == len(prompts)
        assert all(len(p) <= 128 and "@" not in p for p in prompts)
        for key in ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"):
            assert ui[key].startswith("https://")
        # The real legal pages, as GitHub file URLs to files that exist here.
        blob = "https://github.com/tohin003/Truthstone/blob/master/"
        pages = (("supportURL", "SUPPORT"), ("privacyPolicyURL", "PRIVACY"), ("termsOfServiceURL", "TERMS"))
        for key, page in pages:
            assert ui[key] == f"{blob}docs/legal/{page}.md"
            assert (REPO / ui[key][len(blob) :]).is_file()

    def test_brand_color_has_enough_contrast_against_white(self):
        color = manifest()["interface"]["brandColor"]
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", color)

        def luminance(hex_color: str) -> float:
            channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        assert (1.05) / (luminance(color) + 0.05) >= 2.0

    @pytest.mark.parametrize("key", ["composerIcon", "logo", "logoDark"])
    def test_icons_exist_and_are_square_svgs_of_at_least_48px(self, key):
        path = PLUGIN / manifest()["interface"][key]
        text = path.read_text()
        width = float(re.search(r'width="([\d.]+)"', text).group(1))
        height = float(re.search(r'height="([\d.]+)"', text).group(1))
        box = [float(v) for v in re.search(r'viewBox="([^"]+)"', text).group(1).split()]
        assert width == height >= 48
        assert box[2] == box[3] >= 48

    def test_skill_has_frontmatter(self):
        text = (PLUGIN / "skills" / "truthstone" / "SKILL.md").read_text()
        front = text.split("---")[1]
        assert re.search(r"^name: truthstone$", front, re.MULTILINE)
        assert re.search(r"^description: ", front, re.MULTILINE)


class TestPackage:
    def test_contains_only_what_it_should(self):
        files = sorted(str(p.relative_to(PLUGIN)) for p in PLUGIN.rglob("*") if p.is_file())
        # Sorted here too, so the expectation survives a product rename reordering names.
        assert files == sorted(
            [
                ".codex-plugin/plugin.json",
                "LICENSE",
                "README.md",
                "SECURITY.md",
                "assets/truthstone-icon.svg",
                "assets/truthstone-logo-dark.svg",
                "assets/truthstone-logo.svg",
                "hooks/truthstone-hook.sh",
                "hooks/hooks.json",
                "skills/truthstone/SKILL.md",
            ]
        )

    def test_nothing_codex_cannot_fingerprint(self):
        for path in PLUGIN.rglob("*"):
            assert not path.is_symlink(), f"Codex skips every hook of a plugin with a symlink: {path}"

    def test_is_not_mistaken_for_a_claude_plugin(self):
        assert not (PLUGIN / ".claude-plugin").exists()

    def test_marketplace_points_at_the_plugin(self):
        data = json.loads((REPO / plugin.MARKETPLACE_FILE).read_text())
        assert data["name"] == plugin.MARKETPLACE_NAME
        (entry,) = [p for p in data["plugins"] if p["name"] == plugin.PLUGIN_NAME]
        assert entry["source"] == {"source": "local", "path": "./plugins/truthstone"}
        assert entry["policy"] == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
        assert entry["category"]
        assert (REPO / entry["source"]["path"]).is_dir()

    def test_marketplace_upsert_keeps_other_plugins(self):
        other = {"name": "truthstone-practices", "source": {"source": "local", "path": "./plugins/x"}}
        doc = plugin.marketplace_document({"name": "old", "plugins": [other, {"name": "truthstone"}]})
        assert doc["plugins"] == [plugin.marketplace_entry(), other]


# The re-trust tripwire. Updating these values means every user re-reviews the hooks.
# These are the exact `currentHash` values Codex 0.166.0 reported for this plugin through
# `hooks/list` (declaration/content), so the reimplementation itself is pinned to Codex.
# Re-pinned 2026-11-04 for README.md, LICENSE, SECURITY.md, the git-work-tree gate and the
# publisher details (declarations unchanged); confirm via Codex hooks/list before release.
# rename-tool: re-pinned for Truthstone by scripts/rename_product.py; confirm via Codex hooks/list.
EXPECTED_DECLARATIONS = {
    "session_start:0:0": "sha256:16dff026e1a8d1e64802603624e8b79a31721cd548267e454c61785e61eb44f1",
    "user_prompt_submit:0:0": "sha256:84136a898ae55a7db4af13318f1a7d1cb886b9887902badeb965c2cee8c56aea",
    "pre_tool_use:0:0": "sha256:8e34a6c4ab1b9a5e5d785285ecc32db85edb80f9f58f2f40e39e36f42d23c759",
    "post_tool_use:0:0": "sha256:6254bde8d350bdbf215877c616473c8c749e8888467b48186c658331e8c345fb",
    "stop:0:0": "sha256:b2931aa1e2dff91be51fbf1b04d762ea66ae745aeedb8add18bd0b18f61a7a4c",
    "session_end:0:0": "sha256:d4b915624c939d7eb8f1e2514f3108fcef452f9a079dc1f89aa0ecb34a01d681",
}
EXPECTED_PLUGIN_FINGERPRINT = "sha256:eae7b0c655ec2893849f7498a2a7aafd9600366ae3d6ca1e9f7e71816f78de20"

RETRUST = (
    "This changes what Codex fingerprints, so every user will have to review and trust "
    "Truthstone's hooks again in /hooks. If that is intended, update the pinned value."
)


class TestTrustTripwire:
    def test_hook_declarations_are_pinned(self):
        assert declaration_hashes(hooks_file()) == EXPECTED_DECLARATIONS, RETRUST

    def test_plugin_fingerprint_is_pinned(self):
        assert plugin_content_hash(PLUGIN) == EXPECTED_PLUGIN_FINGERPRINT, RETRUST


# -- the launcher ---------------------------------------------------------------------


def write_exe(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def launch(
    event: str, tmp: Path, stdin: str = '{"hook_event_name":"PreToolUse"}', cwd: Path | None = None, **env
) -> subprocess.CompletedProcess:
    """Run the launcher as Codex does, by default in a git work tree (the project gate)."""
    base = {"PATH": f"{tmp / 'bin'}:/usr/bin:/bin", "HOME": str(tmp), "PLUGIN_DATA": str(tmp / "data")}
    base.update({k: v for k, v in env.items() if v is not None})
    for key in [k for k, v in env.items() if v is None]:
        base.pop(key, None)
    if cwd is None:
        cwd = tmp / "work"
        (cwd / ".git").mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        ["/bin/sh", str(LAUNCHER), event],
        input=stdin.encode(), capture_output=True, env=base, cwd=cwd, timeout=30,
    )


FAKE_RUNTIME = 'printf "%s|" "$1"; cat; exit "${FAKE_EXIT:-0}"\n'


class TestLauncher:
    def test_is_valid_posix_sh(self):
        assert subprocess.run(["/bin/sh", "-n", str(LAUNCHER)], capture_output=True).returncode == 0
        assert os.access(LAUNCHER, os.X_OK)

    def test_hands_event_and_payload_to_the_runtime_on_path(self, tmp_path):
        write_exe(tmp_path / "bin" / plugin.RUNTIME_COMMAND, FAKE_RUNTIME)
        result = launch("pre-tool-use", tmp_path, stdin='{"x":1}')
        assert (result.returncode, result.stdout) == (0, b'pre-tool-use|{"x":1}')

    def test_never_exits_2_even_when_the_runtime_does(self, tmp_path):
        write_exe(tmp_path / "bin" / plugin.RUNTIME_COMMAND, FAKE_RUNTIME)
        result = launch("pre-tool-use", tmp_path, FAKE_EXIT="2")
        assert result.returncode == 0  # Codex would read 2 as "block this tool call"

    def test_explicit_override_wins(self, tmp_path):
        write_exe(tmp_path / "bin" / plugin.RUNTIME_COMMAND, 'printf "path"\n')
        override = write_exe(tmp_path / "custom" / "runner", 'printf "override"\n')
        assert launch("stop", tmp_path, TRUTHSTONE_CODEX_HOOK=str(override)).stdout == b"override"

    def test_private_runtime_in_plugin_data(self, tmp_path):
        write_exe(tmp_path / "data" / "runtime" / "bin" / plugin.RUNTIME_COMMAND, 'printf "private"\n')
        assert launch("stop", tmp_path).stdout == b"private"

    def test_disabled_runs_nothing(self, tmp_path):
        write_exe(tmp_path / "bin" / plugin.RUNTIME_COMMAND, 'printf "ran"\n')
        result = launch("session-start", tmp_path, TRUTHSTONE_DISABLE="1")
        assert (result.returncode, result.stdout) == (0, b"")

    def test_no_runtime_warns_once_at_session_start_and_is_silent_otherwise(self, tmp_path):
        result = launch("session-start", tmp_path)
        assert result.returncode == 0
        message = json.loads(result.stdout)["systemMessage"]
        assert "UNGUARDED" in message and plugin.INSTALL_HINT in message
        quiet = launch("pre-tool-use", tmp_path)
        assert (quiet.returncode, quiet.stdout) == (0, b"")

    def test_bootstraps_a_private_runtime_once_with_uv(self, tmp_path):
        log = tmp_path / "uv-calls"
        runtime = f'"$UV_TOOL_BIN_DIR/{plugin.RUNTIME_COMMAND}"'
        write_exe(
            tmp_path / "bin" / "uv",
            f'echo "$* stdin=$(cat)" >> "{log}"\n'
            'mkdir -p "$UV_TOOL_BIN_DIR"\n'
            f"cat > {runtime} <<'EOF'\n"
            "#!/bin/sh\n"
            'printf "boot|%s|" "$1"; cat\n'
            "EOF\n"
            f"chmod +x {runtime}\n",
        )
        first = launch("session-start", tmp_path, stdin='{"s":1}')
        assert (first.returncode, first.stdout) == (0, b'boot|session-start|{"s":1}')
        calls = log.read_text().splitlines()
        assert len(calls) == 1
        assert f"tool install --quiet --reinstall {plugin.RUNTIME_SOURCE}" in calls[0]
        assert calls[0].endswith("stdin=")  # uv must never swallow the hook payload
        assert (tmp_path / "data" / "runtime" / "source").read_text() == plugin.RUNTIME_SOURCE

        launch("session-start", tmp_path)
        assert len(log.read_text().splitlines()) == 1  # installed once, then reused

        launch("session-start", tmp_path, TRUTHSTONE_SOURCE="truthstone==9.9.9")
        assert len(log.read_text().splitlines()) == 2  # a new source re-installs

    def test_bootstrap_can_be_refused(self, tmp_path):
        write_exe(tmp_path / "bin" / "uv", 'echo called > "$HOME/uv-called"\n')
        result = launch("session-start", tmp_path, TRUTHSTONE_NO_BOOTSTRAP="1")
        assert not (tmp_path / "uv-called").exists()
        assert "UNGUARDED" in json.loads(result.stdout)["systemMessage"]

    def test_an_installed_runtime_is_never_replaced_by_the_bootstrap(self, tmp_path):
        write_exe(tmp_path / "bin" / plugin.RUNTIME_COMMAND, 'printf "installed"\n')
        write_exe(tmp_path / "bin" / "uv", 'echo called > "$HOME/uv-called"\n')
        assert launch("session-start", tmp_path).stdout == b"installed"
        assert not (tmp_path / "uv-called").exists()

    def test_outside_a_git_work_tree_it_does_nothing(self, tmp_path):
        """The project gate: no runtime call, no install, not even the missing-runtime
        notice, for every event."""
        elsewhere = tmp_path / "not-a-repository"
        elsewhere.mkdir()
        if any((parent / ".git").exists() for parent in [elsewhere, *elsewhere.parents]):
            pytest.skip("the temporary directory is itself inside a git work tree")
        write_exe(tmp_path / "bin" / "uv", 'echo called > "$HOME/uv-called"\n')
        for event in sorted(spec.arg for spec in HOOK_SPECS):
            result = launch(event, tmp_path, cwd=elsewhere)
            assert (result.returncode, result.stdout, result.stderr) == (0, b"", b""), event
        write_exe(tmp_path / "bin" / plugin.RUNTIME_COMMAND, 'printf "ran"\n')
        assert launch("pre-tool-use", tmp_path, cwd=elsewhere).stdout == b""
        assert not (tmp_path / "uv-called").exists()

    def test_a_subdirectory_of_a_work_tree_is_inside_the_gate(self, tmp_path):
        write_exe(tmp_path / "bin" / plugin.RUNTIME_COMMAND, FAKE_RUNTIME)
        nested = tmp_path / "work" / "src" / "pkg"
        nested.mkdir(parents=True)
        (tmp_path / "work" / ".git").write_text("gitdir: /elsewhere/worktrees/work\n")  # a linked worktree
        result = launch("stop", tmp_path, stdin="{}", cwd=nested)
        assert result.stdout == b"stop|{}"


def _lean(tmp: Path, script: str = 'printf "lean:%s|" "$*"; cat\n') -> Path:
    """What SessionStart leaves in $PLUGIN_DATA/lean: a forwarder and the Python to run it
    (here a stand-in "python" that shows the arguments it was given)."""
    lean = tmp / "data" / "lean"
    python = write_exe(lean / "py", script)
    (lean / "run.py").write_text("# the forwarder's runner\n")
    (lean / "python").write_text(f"{python}\n")
    return lean


class TestLauncherHotPath:
    """WP9: tool calls, Stop and SessionEnd go to the lean forwarder with -I -S, when there is one."""

    @pytest.mark.parametrize("event", ["pre-tool-use", "post-tool-use", "stop", "session-end"])
    def test_forwarding_events_run_the_lean_forwarder_isolated(self, tmp_path, event):
        write_exe(tmp_path / "bin" / plugin.RUNTIME_COMMAND, FAKE_RUNTIME)
        lean = _lean(tmp_path)
        result = launch(event, tmp_path, stdin='{"x":1}')
        budget = "2" if event == "session-end" else "4"
        assert result.returncode == 0
        assert result.stdout == f"lean:-I -S {lean / 'run.py'} --timeout {budget}|{{\"x\":1}}".encode()

    @pytest.mark.parametrize("event", ["session-start", "user-prompt-submit"])
    def test_lifecycle_events_still_run_the_runtime(self, tmp_path, event):
        write_exe(tmp_path / "bin" / plugin.RUNTIME_COMMAND, FAKE_RUNTIME)
        _lean(tmp_path)
        assert launch(event, tmp_path, stdin="{}").stdout == f"{event}|{{}}".encode()

    def test_an_explicit_runtime_is_honoured_for_every_event(self, tmp_path):
        """The benchmark's hook timer, or a developer's own runner, sees every hook."""
        _lean(tmp_path)
        override = write_exe(tmp_path / "custom" / "runner", 'printf "override"\n')
        assert launch("pre-tool-use", tmp_path, TRUTHSTONE_CODEX_HOOK=str(override)).stdout == b"override"

    def test_anything_missing_falls_through_to_the_runtime(self, tmp_path):
        write_exe(tmp_path / "bin" / plugin.RUNTIME_COMMAND, FAKE_RUNTIME)
        lean = _lean(tmp_path)
        (lean / "python").write_text(f"{tmp_path / 'gone' / 'python'}\n")  # the runtime was removed
        assert launch("stop", tmp_path, stdin="{}").stdout == b"stop|{}"
        (lean / "run.py").unlink()
        assert launch("pre-tool-use", tmp_path, stdin="{}").stdout == b"pre-tool-use|{}"

    def test_a_failing_forwarder_never_exits_2(self, tmp_path):
        _lean(tmp_path, "exit 2\n")  # e.g. Python's own "can't open file" status
        assert launch("pre-tool-use", tmp_path).returncode == 0

    def test_outside_a_work_tree_the_hot_path_does_nothing_either(self, tmp_path):
        _lean(tmp_path)
        outside = tmp_path / "plain"
        outside.mkdir()
        result = launch("pre-tool-use", tmp_path, cwd=outside)
        assert (result.returncode, result.stdout) == (0, b"")


class TestDocuments:
    """README.md, SECURITY.md and LICENSE: generated, so they say what the launcher does."""

    def test_readme_discloses_what_the_plugin_does(self):
        text = (PLUGIN / "README.md").read_text()
        for disclosure in (
            "codex plugin marketplace add tohin003/Truthstone",
            f"codex plugin add {plugin.PLUGIN_NAME}@{plugin.MARKETPLACE_NAME}",
            "/hooks",
            "Review hooks",
            plugin.RUNTIME_SOURCE,
            plugin.INSTALL_HINT,
            "Python Package Index",
            "TRUTHSTONE_NO_BOOTSTRAP=1",
            "TRUTHSTONE_DISABLE=1",
            "git work tree",
            "127.0.0.1",
            "bearer token",
            "~/.truthstone",
            "270 days",
            f"codex plugin remove {plugin.PLUGIN_NAME}@{plugin.MARKETPLACE_NAME}",
            "IDE extension",
            plugin.DEVELOPER_NAME,
            plugin.SUPPORT_EMAIL,
            plugin.PRIVACY_POLICY_URL,
        ):
            assert disclosure in text, disclosure

    def test_security_policy_and_license(self):
        security = (PLUGIN / "SECURITY.md").read_text()
        assert plugin.SUPPORT_EMAIL in security and "Report a vulnerability" in security
        assert (PLUGIN / "LICENSE").read_text() == (REPO / "LICENSE").read_text()
