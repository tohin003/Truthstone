"""Installs made under a former product name keep working (`truthstone.names`).

A rename (``scripts/rename_product.py``) records the old name in ``names.FORMER``. These
tests inject a synthetic former name, so they hold before any rename and after every one.
The last class repeats the key checks for each real former name, once there is one.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
from pathlib import Path

import pytest

from truthstone import names
from truthstone.adapters.claude_code import forward, protocol, settings_scan, shim
from truthstone.adapters.claude_code import install as claude_install
from truthstone.adapters.codex import hook as codex_hook
from truthstone.adapters.codex import install as codex_install
from truthstone.adapters.codex import plugin as codex_plugin
from truthstone.adapters.codex import status as codex_status
from truthstone.core import config

PRIOR = ("Priorname", "priorname", "PRIORNAME")


def var(key: str, spelling: tuple[str, str, str] | None = None) -> str:
    return f"{(spelling or (names.DISPLAY, names.SLUG, names.UPPER))[2]}_{key}"


@pytest.fixture
def prior(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str, str]:
    """A former name, newest, ahead of any real ones."""
    monkeypatch.setattr(names, "FORMER", (PRIOR, *names.FORMER))
    return PRIOR


@pytest.fixture
def bare_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prior) -> Path:
    """$HOME is an empty directory and no *_HOME variable, current or former, is set."""
    home = tmp_path / "user"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for name in names.variants(var("HOME")):
        monkeypatch.delenv(name, raising=False)
    return home


class TestSpellings:
    def test_without_former_names_there_is_one_variant(self, monkeypatch):
        monkeypatch.setattr(names, "FORMER", ())
        assert names.variants(f"X-{names.DISPLAY}") == [f"X-{names.DISPLAY}"]
        assert not names.written_under_former_name("anything", f"{names.SLUG}.adapters")

    def test_each_spelling_maps_to_the_same_spelling_of_the_former_name(self, prior):
        assert names.variants(f"X-{names.DISPLAY}")[:2] == [f"X-{names.DISPLAY}", "X-Priorname"]
        module = f"{names.SLUG}.adapters.codex.hook"
        assert names.variants(module)[1] == "priorname.adapters.codex.hook"
        assert names.variants(var("HOME"))[1] == "PRIORNAME_HOME"
        assert names.written_under_former_name("python -m priorname.adapters.codex.hook", module)
        # A former spelling elsewhere (say, a checkout directory) is not a former entry.
        assert not names.written_under_former_name(f"/src/Priorname/bin/python -m {module}", module)

    def test_one_pass_so_nothing_is_rewritten_twice(self):
        assert names._translate("ab-ba", ("a", "b", "c"), ("b", "a", "d")) == "ba-ab"

    def test_newest_former_name_first_and_no_duplicates(self, monkeypatch):
        older = ("Oldest", "oldest", "OLDEST")
        monkeypatch.setattr(names, "FORMER", (PRIOR, older, PRIOR))
        assert names.variants(names.SLUG) == [names.SLUG, "priorname", "oldest"]


class TestEnvironment:
    def test_the_current_name_wins(self, prior, monkeypatch):
        monkeypatch.setenv(var("DISABLE"), "0")
        monkeypatch.setenv(var("DISABLE", prior), "1")
        assert names.env(var("DISABLE")) == "0"
        assert not names.env_flag(var("DISABLE"))

    def test_the_former_name_is_the_fallback(self, prior, monkeypatch):
        monkeypatch.delenv(var("DISABLE"), raising=False)
        monkeypatch.setenv(var("DISABLE", prior), "yes")
        assert names.env_flag(var("DISABLE"))
        assert config.is_globally_disabled()
        assert codex_hook._disabled()

    def test_empty_counts_as_unset(self, prior, monkeypatch):
        monkeypatch.setenv(var("OBSERVE"), "")
        monkeypatch.setenv(var("OBSERVE", prior), "on")
        assert config.is_observe_only()

    def test_unset_everywhere(self, prior, monkeypatch):
        for name in names.variants(var("START_TIMEOUT")):
            monkeypatch.delenv(name, raising=False)
        assert names.env(var("START_TIMEOUT")) is None
        assert shim._start_timeout() == shim.DAEMON_START_TIMEOUT_S

    def test_a_former_setting_reaches_the_shim(self, prior, monkeypatch):
        monkeypatch.delenv(var("START_TIMEOUT"), raising=False)
        monkeypatch.setenv(var("START_TIMEOUT", prior), "3")
        assert shim._start_timeout() == 3.0

    def test_variables_outside_the_product_pass_through(self, prior):
        assert names.env("PATH") == os.environ["PATH"]

    def test_an_explicit_mapping(self, prior):
        assert names.env(var("HOME"), {var("HOME", prior): "/x"}) == "/x"


class TestDataDirectory:
    def test_fresh_install_uses_the_current_name(self, bare_home):
        expected = bare_home / f".{names.SLUG}"
        assert config.truthstone_home() == expected
        assert shim._home() == codex_hook._home() == str(expected)

    def test_an_existing_former_directory_is_used(self, bare_home):
        (bare_home / ".priorname").mkdir()
        assert config.truthstone_home() == bare_home / ".priorname"
        assert shim._home() == codex_hook._home() == str(bare_home / ".priorname")

    def test_once_the_current_directory_exists_it_wins(self, bare_home):
        (bare_home / ".priorname").mkdir()
        (bare_home / f".{names.SLUG}").mkdir()
        assert config.truthstone_home() == bare_home / f".{names.SLUG}"

    def test_explicit_settings_win_over_both(self, bare_home, tmp_path, monkeypatch):
        (bare_home / ".priorname").mkdir()
        monkeypatch.setenv(var("HOME", PRIOR), str(tmp_path / "pebble" / "guard"))
        assert config.truthstone_home() == tmp_path / "pebble" / "guard"
        monkeypatch.setenv(var("HOME"), str(tmp_path / "current"))
        assert config.truthstone_home() == tmp_path / "current"

    def test_the_database_keeps_its_former_file_name(self, prior, isolated_home):
        current = isolated_home / f"{names.SLUG}.db"
        assert config.database_path() == current
        (isolated_home / "priorname.db").write_bytes(b"")
        assert config.database_path() == isolated_home / "priorname.db"
        current.write_bytes(b"")
        assert config.database_path() == current

    def test_doctor_offers_the_move(self, bare_home):
        assert names.migration_notes({}) == []
        (bare_home / ".priorname").mkdir()
        (note,) = names.migration_notes({})
        assert str(bare_home / ".priorname") in note and f"mv {bare_home / '.priorname'}" in note
        assert str(bare_home / f".{names.SLUG}") in note

    def test_doctor_names_former_variables(self, bare_home):
        (note,) = names.migration_notes({var("OBSERVE", PRIOR): "1"})
        assert var("OBSERVE", PRIOR) in note and var("OBSERVE") in note
        assert names.migration_notes({var("OBSERVE", PRIOR): "1", var("OBSERVE"): "1"}) == []

    def test_per_workspace_state_directories_are_never_indexed(self, prior):
        excluded = config.IndexSettings().exclude_dirs
        assert f".{names.SLUG}" in excluded and ".priorname" in excluded


def as_prior(document: dict) -> dict:
    """What an install under the former name wrote: the same entries, spelled the old way."""
    return json.loads(names.as_former(json.dumps(document), PRIOR))


USER_HOOK = {"type": "command", "command": "echo mine", "timeout": 5}


class TestClaudeSettings:
    def test_reinstall_replaces_former_entries_instead_of_duplicating(self, prior, tmp_path):
        hooks = as_prior(claude_install.build_hook_config(python_exe="/usr/bin/python3"))
        hooks["Stop"][0]["hooks"].append(USER_HOOK)
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"hooks": hooks}))
        assert claude_install.is_installed(path)

        result, changed = claude_install.install(path, python_exe="/usr/bin/python3")
        assert changed
        text = json.dumps(result)
        assert "Priorname" not in text and "priorname" not in text
        assert USER_HOOK in [h for group in result["hooks"]["Stop"] for h in group["hooks"]]
        current = claude_install.build_hook_config(python_exe="/usr/bin/python3")
        for event, groups in current.items():
            ours = [g for g in result["hooks"][event] if claude_install._is_ours(g)]
            assert len(ours) == len(groups), event

    def test_uninstall_removes_former_entries_and_nothing_else(self, prior, tmp_path):
        hooks = as_prior(claude_install.build_hook_config(python_exe="/usr/bin/python3"))
        hooks["Stop"][0]["hooks"].append(USER_HOOK)
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"hooks": hooks}))
        result, changed = claude_install.uninstall(path)
        assert changed
        assert result == {"hooks": {"Stop": [{"hooks": [USER_HOOK]}]}}


class TestCodexHooks:
    def former_file(self, tmp_path: Path) -> Path:
        path = tmp_path / "hooks.json"
        document = {
            "description": codex_install.HOOKS_FILE_DESCRIPTION,
            "hooks": codex_install.build_hook_config(python_exe="/usr/bin/python3"),
        }
        path.write_text(json.dumps(as_prior(document)))
        return path

    def test_reinstall_replaces_former_entries(self, prior, tmp_path):
        path = self.former_file(tmp_path)
        assert codex_install.is_installed(path)
        result, changed = codex_install.install(path, python_exe="/usr/bin/python3")
        assert changed
        assert result["description"] == codex_install.HOOKS_FILE_DESCRIPTION
        assert result["hooks"] == codex_install.build_hook_config(python_exe="/usr/bin/python3")

    def test_uninstall_removes_a_file_that_only_held_former_entries(self, prior, tmp_path):
        path = self.former_file(tmp_path)
        _, changed = codex_install.uninstall(path)
        assert changed and not path.exists()

    def test_doctor_recognises_former_plugin_hooks(self, prior, tmp_path):
        assert codex_status._is_truthstone({"pluginId": names.as_former(codex_status.plugin_id(), prior)})
        command = f"/usr/bin/python3 -m {names.as_former(codex_install.HOOK_MODULE, prior)} stop"
        assert codex_status._is_truthstone({"command": command})
        assert not codex_status._is_truthstone({"command": "echo priorname"})

    def test_doctor_finds_the_former_plugin(self, prior, tmp_path):
        assert codex_status.former_plugin_ids(tmp_path) == []
        cache = tmp_path / "plugins" / "cache" / "priorname" / "priorname" / "1.0.0"
        cache.mkdir(parents=True)
        assert codex_status.former_plugin_ids(tmp_path) == ["priorname@priorname"]


def run_launcher(script: Path, tmp: Path, **env: str) -> subprocess.CompletedProcess:
    base = {"PATH": f"{tmp / 'bin'}:/usr/bin:/bin", "HOME": str(tmp), "PLUGIN_DATA": str(tmp / "data")}
    return subprocess.run(
        ["/bin/sh", str(script), "stop"], input=b"{}", capture_output=True, env={**base, **env}, timeout=30
    )


def executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


class TestCodexLauncher:
    def test_unchanged_until_there_is_a_former_name(self, monkeypatch):
        monkeypatch.setattr(names, "FORMER", ())
        assert "rename-tool" not in codex_plugin.launcher_script()

    def test_every_setting_it_reads_falls_back_to_the_former_name(self, prior, tmp_path):
        script = codex_plugin.launcher_script()
        for key in ("DISABLE", "SOURCE", "CODEX_HOOK", "NO_BOOTSTRAP"):
            assert f'[ -z "${{{var(key, prior)}+x}}" ] || {var(key)}=${var(key, prior)}' in script
        path = tmp_path / "launcher.sh"
        path.write_text(script)
        assert subprocess.run(["/bin/sh", "-n", str(path)], capture_output=True).returncode == 0

    def test_former_settings_take_effect(self, prior, tmp_path):
        path = tmp_path / "launcher.sh"
        path.write_text(codex_plugin.launcher_script())
        executable(tmp_path / "bin" / codex_plugin.RUNTIME_COMMAND, 'printf "path"\n')
        override = executable(tmp_path / "custom", 'printf "override"\n')
        assert run_launcher(path, tmp_path).stdout == b"path"
        assert run_launcher(path, tmp_path, **{var("CODEX_HOOK", prior): str(override)}).stdout == b"override"
        assert run_launcher(path, tmp_path, **{var("DISABLE", prior): "1"}).stdout == b""
        current_wins = {var("DISABLE"): "0", var("DISABLE", prior): "1"}
        assert run_launcher(path, tmp_path, **current_wins).stdout == b"path"

    def test_fallbacks_keep_unset_settings_unset(self, prior, tmp_path):
        """A script may test ``${NAME+set}``; a fallback must not make an unset name set."""
        body = f'if [ -n "${{{var("UV")}+set}}" ]; then echo "set:${var("UV")}"; else echo unset; fi\n'
        path = tmp_path / "probe.sh"
        path.write_text("#!/bin/sh\n" + names.shell_fallbacks(body) + body)
        assert run_launcher(path, tmp_path).stdout == b"unset\n"
        assert run_launcher(path, tmp_path, **{var("UV", prior): ""}).stdout == b"set:\n"
        assert run_launcher(path, tmp_path, **{var("UV", prior): "/x"}).stdout == b"set:/x\n"
        both = {var("UV"): "/new", var("UV", prior): "/x"}
        assert run_launcher(path, tmp_path, **both).stdout == b"set:/new\n"


class TestClaudePlugin:
    def test_a_former_session_switch_still_sets_the_mode(self, prior):
        assert protocol.session_mode_from_env({var("DISABLE", prior): "1"}) == "disabled"
        assert protocol.session_mode_from_env({var("OBSERVE", prior): "yes"}) == "observe"
        assert protocol.session_mode_from_env({var("DISABLE"): "0", var("DISABLE", prior): "1"}) == "guard"

    def test_a_former_name_s_plugin_counts_as_installed(self, prior, tmp_path):
        record = tmp_path / "plugins" / "installed_plugins.json"
        record.parent.mkdir(parents=True)
        record.write_text(json.dumps({"plugins": {"priorname@priorname": [{"scope": "user"}]}}))
        (install,) = settings_scan.plugin_installs({"CLAUDE_CONFIG_DIR": str(tmp_path)})
        assert install.plugin_id == "priorname@priorname"


class TestStandaloneForwarder:
    """``forward.py`` runs as ``python -I -S`` and cannot import `names`: it carries a copy
    of the registry and of the rules, which must not drift."""

    def test_it_records_the_same_former_names(self):
        assert forward.FORMER == names.FORMER

    def test_the_same_data_directory_rule(self, bare_home, monkeypatch):
        monkeypatch.setattr(forward, "FORMER", names.FORMER)
        assert forward.truthstone_home() == names.data_dir() == str(bare_home / f".{names.SLUG}")
        (bare_home / ".priorname").mkdir()
        assert forward.truthstone_home() == names.data_dir() == str(bare_home / ".priorname")
        (bare_home / f".{names.SLUG}").mkdir()
        assert forward.truthstone_home() == names.data_dir() == str(bare_home / f".{names.SLUG}")

    def test_former_settings_apply(self, prior, monkeypatch, tmp_path):
        monkeypatch.setattr(forward, "FORMER", names.FORMER)
        for name in names.variants(var("HOME")) + names.variants(var("DISABLE")):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv(var("HOME", prior), str(tmp_path / "old"))
        assert forward.truthstone_home() == names.data_dir() == str(tmp_path / "old")
        monkeypatch.setenv(var("DISABLE", prior), "1")
        stdin = io.StringIO("{}")
        assert forward.run([], stdin, io.StringIO()) == 0
        assert stdin.tell() == 0  # disabled before reading a byte


@pytest.mark.parametrize("spelling", names.FORMER, ids=lambda f: f[0])
class TestRealFormerNames:
    """After a real rename: the name it replaced still works."""

    def test_its_settings_still_apply(self, spelling, monkeypatch, tmp_path):
        for name in names.variants(var("HOME")):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv(var("HOME", spelling), str(tmp_path / "old-home"))
        assert config.truthstone_home() == tmp_path / "old-home"

    def test_its_hook_entries_are_still_ours(self, spelling):
        module = codex_install.HOOK_MODULE
        assert names.as_former(module, spelling) in names.variants(module)
        header = names.as_former(f"X-{names.DISPLAY}", spelling)
        assert claude_install._is_ours_hook({"type": "http", "headers": {header: "1"}})
