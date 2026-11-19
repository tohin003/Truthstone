"""The companion's OpenAI "With MCP" package (scripts/companion_package.py build-openai) and the
Claude-directory filter that keeps its MCP and review data out of Claude's variant."""

from __future__ import annotations

import json
import zipfile

import pytest
from scripts import claude_directory_branch, companion_package

MCP_URL = "https://checks.truthstone.invalid/mcp"
DEMO_URL = "https://demo.truthstone.invalid/walkthrough"


def build(tmp_path, *extra: str) -> int:
    return companion_package.main(
        ["build-openai", "--mcp-url", MCP_URL, "--demo-url", DEMO_URL, "--out", str(tmp_path), *extra]
    )


def test_build_writes_a_valid_portable_package(tmp_path, capsys):
    assert build(tmp_path) == 0
    (target,) = tmp_path.glob("truthstone-practices-*-with-mcp.zip")
    with zipfile.ZipFile(target) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("plugin.json"))
        servers = json.loads(archive.read("mcp.json"))
    assert {"plugin.json", "mcp.json", "skills/safe-shell/SKILL.md"} <= names
    assert not any(name.startswith((".codex-plugin/", ".claude-plugin/")) for name in names)
    assert servers["mcpServers"] == {
        "truthstone-checks": {
            "type": "streamable-http",
            "url": MCP_URL,
            "extensions": {"com.openai": {"auth": {"type": "none"}}},
        }
    }
    review = manifest["extensions"]["com.openai"]["review"]
    assert review["demo_recording_url"] == DEMO_URL
    assert [len(review["test_cases"][kind]) for kind in ("positive", "negative")] == [5, 3]
    assert "PASS" in capsys.readouterr().out


def test_build_refuses_without_urls(tmp_path):
    with pytest.raises(SystemExit):
        companion_package.main(["build-openai", "--out", str(tmp_path)])
    assert (
        companion_package.main(
            [
                "build-openai",
                "--mcp-url",
                "http://insecure/mcp",
                "--demo-url",
                DEMO_URL,
                "--out",
                str(tmp_path),
            ]
        )
        == 1
    )
    assert not list(tmp_path.glob("*.zip"))


def test_validation_rejects_a_broken_package(tmp_path):
    assert build(tmp_path) == 0
    (target,) = tmp_path.glob("*.zip")
    with zipfile.ZipFile(target) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["plugin.json"])
    manifest["extensions"]["com.openai"]["review"]["test_cases"]["positive"].pop()
    del manifest["extensions"]["com.openai"]["interface"]["supportURL"]
    members["plugin.json"] = json.dumps(manifest).encode()
    servers = json.loads(members["mcp.json"])
    servers["mcpServers"]["truthstone-checks"]["headers"] = {"Authorization": "x"}
    members["mcp.json"] = json.dumps(servers).encode()
    members["hooks/hooks.json"] = b"{}"
    broken = tmp_path / "broken.zip"
    companion_package.write_zip(broken, members)
    hit = companion_package.validate_openai_zip(broken).rules_hit()
    assert {"MCP-REVIEW", "MCP-LISTING-URLS", "MCP-CONFIG", "NO-HOOKS"} <= hit


def test_claude_variant_drops_mcp_and_review_data():
    plugin = claude_directory_branch.PLUGIN
    for path in ("mcp.json", ".mcp.json", "plugin.json", ".codex-plugin/plugin.json", "assets/logo.svg"):
        assert claude_directory_branch.dropped(f"{plugin}/{path}")
    for path in (".claude-plugin/plugin.json", "README.md", "skills/safe-shell/SKILL.md", "assets/logo.png"):
        assert not claude_directory_branch.dropped(f"{plugin}/{path}")
