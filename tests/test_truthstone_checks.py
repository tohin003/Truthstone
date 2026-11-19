"""The hosted Truthstone checks server (services/truthstone-checks): each tool on one clean and
one flagged input, the size limit, the plain routes, and one MCP session over Streamable HTTP."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import truthstone_checks as checks

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

TEST_FILE = """import pytest
from app import add


def test_add():
    assert add(2, 2) == 4
    assert add(-1, 1) == 0


def test_sub():
    assert add(5, -3) == 2
"""


def call(name: str, arguments: dict):
    return asyncio.run(checks.mcp.call_tool(name, arguments))


def error(name: str, arguments: dict) -> str:
    """The message a rejected call returns (the protocol layer sends it as an is_error result)."""
    with pytest.raises(ToolError) as caught:
        call(name, arguments)
    return str(caught.value)


def test_shell_command_clean():
    result = call("check_shell_command", {"command": "git commit -m 'never git push --force' && ls -la"})
    assert result.structured_content == {"verdict": "clean", "findings": [], "safer_command": None}
    assert result.content[0].text.startswith("clean:")


def test_shell_command_flagged():
    result = call("check_shell_command", {"command": "git push --force origin main"})
    data = result.structured_content
    assert data["verdict"] == "review"
    assert data["findings"] == [
        {"severity": "critical", "rule": "force push to main", "matched": "git push --force origin main"}
    ]
    assert "force push to main" in result.content[0].text


def test_shell_command_offers_the_guarded_form():
    data = call("check_shell_command", {"command": 'rm -rf "$OUT_DIR"'}).structured_content
    assert data["verdict"] == "review"
    assert data["safer_command"] == '[ -n "$OUT_DIR" ] && rm -rf "$OUT_DIR"'


def test_test_edit_clean():
    after = TEST_FILE + "\n\ndef test_zero():\n    assert add(0, 0) == 0\n"
    data = call("check_test_edit", {"path": "tests/test_math.py", "before": TEST_FILE, "after": after})
    assert data.structured_content == {"verdict": "clean", "weakenings": []}


def test_test_edit_flagged():
    after = TEST_FILE.replace("def test_add", "@pytest.mark.skip(reason='flaky')\ndef test_add").replace(
        "    assert add(5, -3) == 2\n", "    pass\n"
    )
    data = call("check_test_edit", {"path": "tests/test_math.py", "before": TEST_FILE, "after": after})
    assert data.structured_content["verdict"] == "weakened"
    kinds = {(w["test"], w["kind"], w["always"]) for w in data.structured_content["weakenings"]}
    assert kinds == {("test_add", "skipped", True), ("test_sub", "fewer-assertions", False)}


def test_test_edit_unsupported_path():
    data = call("check_test_edit", {"path": "src/app.py", "before": "x = 1\n", "after": "x = 2\n"})
    assert data.structured_content["verdict"] == "unsupported"


def test_test_runs_verified():
    steps = [
        {"edited_file": "src/app.py"},
        {"command": "pytest", "exit_code": 0, "output": "===== 12 passed in 0.50s ====="},
    ]
    data = call("check_test_runs", {"steps": steps, "final_message": "Done, all tests pass."})
    assert data.structured_content["verdict"] == "verified"
    assert data.structured_content["overclaim"] is False


def test_test_runs_flagged_narrower_after_failure():
    steps = [
        {"edited_file": "src/app.py"},
        {
            "command": "pytest",
            "exit_code": 1,
            "output": "FAILED tests/test_app.py::test_add\n== 1 failed, 11 passed in 0.4s ==",
        },
        {"edited_file": "src/app.py"},
        {"command": "pytest tests/test_app.py::test_sub", "exit_code": 0, "output": "== 1 passed in 0.1s =="},
    ]
    data = call("check_test_runs", {"steps": steps, "final_message": "Fixed. All tests pass now."})
    assert data.structured_content["verdict"] == "unverified"
    assert data.structured_content["overclaim"] is True
    assert "narrower" in data.structured_content["reason"]


def test_test_runs_stale_and_failing():
    stale = call(
        "check_test_runs",
        {
            "steps": [
                {"command": "pytest", "exit_code": 0, "output": "== 3 passed in 0.1s =="},
                {"edited_file": "a.py"},
            ]
        },
    )
    assert stale.structured_content["verdict"] == "unverified"
    failing = call(
        "check_test_runs", {"steps": [{"edited_file": "a.js"}, {"command": "npm test", "exit_code": 1}]}
    )
    assert failing.structured_content["verdict"] == "failing"


def test_test_runs_step_needs_one_kind():
    assert "exactly one of" in error(
        "check_test_runs", {"steps": [{"command": "pytest", "edited_file": "a.py"}]}
    )


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("check_shell_command", {"command": "x" * (checks.MAX_TEXT + 1)}),
        ("check_test_edit", {"path": "tests/test_a.py", "before": "a" * 150_000, "after": "b" * 150_000}),
        (
            "check_test_runs",
            {
                "steps": [
                    {"command": "pytest", "output": "o" * 120_000},
                    {"command": "pytest", "output": "o" * 120_000},
                ]
            },
        ),
    ],
)
def test_size_limit(name, arguments):
    text = error(name, arguments)
    assert "200,000" in text or "200000" in text
    assert len(text) < 1000  # the error does not echo the input back


def test_every_tool_is_read_only_and_closed_world():
    tools = asyncio.run(checks.mcp.list_tools())
    assert [tool.name for tool in tools] == ["check_shell_command", "check_test_edit", "check_test_runs"]
    for tool in tools:
        hints = tool.annotations
        assert (hints.read_only_hint, hints.destructive_hint, hints.open_world_hint) == (True, False, False)
        assert tool.output_schema["type"] == "object"


def _session(monkeypatch) -> dict:
    """One MCP session against the ASGI app, over HTTP, with its lifespan running."""
    monkeypatch.setenv(checks.CHALLENGE_ENV, "token-123")
    seen: dict = {}

    async def run() -> None:
        async with checks.app.router.lifespan_context(checks.app):
            transport = httpx.ASGITransport(app=checks.app)
            async with httpx.AsyncClient(transport=transport, base_url="https://checks.example") as client:
                seen["root"] = await client.get("/")
                seen["challenge"] = await client.get("/.well-known/openai-apps-challenge")

                async def rpc(number: int, method: str, params: dict) -> dict:
                    body = {"jsonrpc": "2.0", "id": number, "method": method, "params": params}
                    response = await client.post("/mcp", json=body, headers=MCP_HEADERS)
                    assert response.status_code == 200, response.text
                    assert response.headers["content-type"].startswith("application/json")
                    return response.json()

                seen["init"] = await rpc(
                    1,
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "pytest", "version": "0"},
                    },
                )
                note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                assert (await client.post("/mcp", json=note, headers=MCP_HEADERS)).status_code == 202
                seen["list"] = await rpc(2, "tools/list", {})
                seen["shell"] = await rpc(
                    3, "tools/call", {"name": "check_shell_command", "arguments": {"command": "rm -rf /"}}
                )
                seen["edit"] = await rpc(
                    4,
                    "tools/call",
                    {
                        "name": "check_test_edit",
                        "arguments": {"path": "tests/test_math.py", "before": TEST_FILE},
                    },
                )
                seen["runs"] = await rpc(
                    5,
                    "tools/call",
                    {"name": "check_test_runs", "arguments": {"steps": [{"edited_file": "a.py"}]}},
                )

    asyncio.run(run())
    return seen


def test_end_to_end_over_streamable_http(monkeypatch):
    seen = _session(monkeypatch)
    assert seen["root"].status_code == 200 and "Truthstone checks" in seen["root"].text
    assert seen["challenge"].text == "token-123"
    init = seen["init"]["result"]
    assert init["serverInfo"]["name"] == "truthstone-checks"
    assert "check_shell_command" in init["instructions"]
    names = [tool["name"] for tool in seen["list"]["result"]["tools"]]
    assert names == ["check_shell_command", "check_test_edit", "check_test_runs"]
    assert seen["shell"]["result"]["structuredContent"]["verdict"] == "review"
    assert seen["edit"]["result"]["structuredContent"]["weakenings"][0]["kind"] == "file-deleted"
    assert seen["runs"]["result"]["structuredContent"]["verdict"] == "unverified"


def test_challenge_is_404_when_unset(monkeypatch):
    monkeypatch.delenv(checks.CHALLENGE_ENV, raising=False)

    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=checks.app)
        async with httpx.AsyncClient(transport=transport, base_url="https://checks.example") as client:
            return await client.get("/.well-known/openai-apps-challenge")

    assert asyncio.run(run()).status_code == 404
