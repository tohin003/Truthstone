"""Claude Code cells run every Bash command in Claude Code's own sandbox, and prove it.

Why: the observe-only arm deliberately does not block destructive commands, and Claude
cells keep the user's real ``HOME`` (the subscription sign-in lives in the login
keychain). Without a sandbox an agent's ``rm``, ``chmod`` or ``pip install --user`` would
act on the user's machine, and Bash could reach the network.

What every cell gets (``cell_settings``, passed with ``--settings``; profile ``PROFILE``):

* **Bash** runs under Claude Code's sandbox (Seatbelt on macOS): writes only inside the
  cell's repository and its own temp directory; no network at all (an empty allowlist,
  ``strictAllowlist``, no loopback, no Unix sockets); no unsandboxed retry
  (``allowUnsandboxedCommands: false``); and Claude Code refuses to start rather than run
  unsandboxed (``failIfUnavailable``). Reads of the benchmark's own material (the checkout
  with the hidden tests, the run directory, the work root with both arms' homes) and of
  credentials are denied; the task interpreter and Node stay readable. The product's and
  the harness's environment variables are unset for Bash (``credentials.envVars``), so an
  agent cannot even find the arm's home.
* **File tools** are not covered by the Bash sandbox (verified: a bare ``Write`` allow
  rule writes anywhere). So the plan never allows ``Edit``/``Write`` bare; each cell
  allows them for its own repository and temp directory only, by absolute path rules, and
  denies ``Read`` (hence Grep and Glob) on the same hidden paths. Under ``dontAsk``
  anything else is refused.
* **Hooks** are not sandboxed (verified): Truthstone's hooks and the harness's logging
  hook still reach their daemon on loopback and write their trace.

The proof is ``check``: the *real* pinned Claude Code binary, the *real* cell flags and
settings, and a scripted stand-in for the Anthropic API on loopback that replays tool
calls (Bash probes, a Write outside the cell, a Write inside it, a Read of a hidden
path). No model is called and no credential is used: the check runs with a scratch
``HOME`` and config directory and a dummy API key aimed at the loopback server.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from truthstone.bench.codex import homes, naming

# Bump on any change to cell_settings(); plans pin it, and the check proves the version.
PROFILE = "claude-bash-sandbox/v1"
# Tools a Claude plan may allow bare. The file-editing tools are allowed per cell, by path.
FILE_EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
# Credentials and the user's other agent homes: never readable from a cell.
SENSITIVE_HOME_PATHS = (
    ".ssh", ".aws", ".gnupg", ".docker", ".kube", ".netrc", ".npmrc", ".pypirc", ".git-credentials",
    ".codex", ".claude", ".claude.json", ".claude-work", ".claude-personal",
    f".{naming.PRODUCT}", ".agentguard", "Library/Keychains",
)  # fmt: skip
# ~/.config holds tokens (gh, vendor CLIs), but git reads ~/.config/git on every command and
# warns on each one when it is unreadable (verified): hide every entry except git's.
CONFIG_KEEP = frozenset({"git"})


# Unset for Bash: they would point an agent at its arm's home and the harness's trace.
HIDDEN_ENV = (
    naming.ENV_HOME,
    naming.ENV_RUNTIME_SPEC,
    naming.ENV_UV,
    naming.ENV_RECORD_DIR,
    naming.ENV_CODEX_HOOK,
    naming.ENV_NO_BOOTSTRAP,
)


@dataclass(frozen=True, slots=True)
class SandboxPaths:
    """What a study hides from its cells, and what it re-opens inside that."""

    deny_read: tuple[str, ...] = ()
    allow_read: tuple[str, ...] = ()
    hidden_env: tuple[str, ...] = HIDDEN_ENV

    @classmethod
    def for_study(
        cls, repo_root: Path, run_dir: Path, work_root: Path, readable: list[Path], home: Path | None = None
    ) -> SandboxPaths:
        home = home or Path.home()
        deny = [repo_root, run_dir, work_root, *_main_checkout(repo_root)]
        deny += [home / rel for rel in SENSITIVE_HOME_PATHS if os.path.lexists(home / rel)]
        config = home / ".config"
        if config.is_dir():
            deny += sorted(p for p in config.iterdir() if p.name not in CONFIG_KEEP)
        return cls(deny_read=_unique(deny), allow_read=_unique(readable))


def _unique(paths: list[Path]) -> tuple[str, ...]:
    out: list[str] = []
    for path in paths:
        text = str(Path(path).resolve())
        if text not in out:
            out.append(text)
    return tuple(out)


def _main_checkout(repo_root: Path) -> list[Path]:
    """A worktree's main checkout holds the same hidden tests: hide it too."""
    try:
        common = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return []
    if not common:
        return []
    main = Path(common).parent
    return [main] if main.resolve() != repo_root.resolve() else []


def plan_tools(tools: list[str] | tuple[str, ...]) -> list[str]:
    """The bare tools a sandboxed plan may allow (the file-editing ones are per cell)."""
    return [t for t in tools if t not in FILE_EDIT_TOOLS]


def bare_file_tools(tools: list[str] | tuple[str, ...]) -> list[str]:
    return [t for t in tools if t in FILE_EDIT_TOOLS]


def cell_settings(repo: Path, tmpdir: Path, paths: SandboxPaths) -> dict[str, Any]:
    """The ``--settings`` one cell runs under (profile ``PROFILE``)."""
    writable = [str(Path(repo).resolve()), str(Path(tmpdir).resolve())]
    return {
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "autoAllowBashIfSandboxed": True,
            "allowUnsandboxedCommands": False,
            "filesystem": {
                "allowWrite": [writable[1]],  # the repository (cwd) is writable by default
                "denyRead": list(paths.deny_read),
                "allowRead": list(paths.allow_read),
            },
            "network": {
                "allowedDomains": [],
                "strictAllowlist": True,
                "allowLocalBinding": False,
                "allowAllUnixSockets": False,
            },
            "credentials": {"envVars": [{"name": name, "mode": "deny"} for name in paths.hidden_env]},
        },
        "permissions": {
            "allow": [f"{tool}(/{root}/**)" for root in writable for tool in ("Edit", "Write")],
            "deny": [f"Read(/{path}/**)" for path in paths.deny_read] + ["WebFetch", "WebSearch"],
        },
    }


def write_cell_settings(path: Path, repo: Path, tmpdir: Path, paths: SandboxPaths) -> Path:
    path.write_text(json.dumps(cell_settings(repo, tmpdir, paths), indent=2) + "\n", encoding="utf-8")
    return path


def cell_env(tmpdir: Path) -> dict[str, str]:
    """Sandboxed Bash gets ``$TMPDIR`` under this directory (Claude Code appends a per-user part)."""
    return {"CLAUDE_CODE_TMPDIR": str(Path(tmpdir).resolve())}


# -- the proof: a scripted Anthropic API on loopback --------------------------------


class ScriptedAPI:
    """Replays a fixed list of assistant turns to Claude Code. Never a model.

    Each request's turn is the number of tool results it carries: turn *k* answers with
    ``turns[k]`` (tool calls), and after the last one with a final text. Requests without
    the Bash tool (Claude Code's side calls) get a short text. Hook posts (``/hook/<event>``)
    are counted. Request headers are never read, so no credential is ever handled.
    """

    def __init__(self, turns: list[list[dict]]):
        self.turns = turns
        self.results: list[dict] = []
        self.hooks: list[str] = []
        self.requests = 0
        self.lock = threading.Lock()
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                return

            def _json(self, code: int, payload: dict) -> None:
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                if self.path.startswith("/ping"):
                    self._json(200, {"pong": True})  # the loopback probe's target
                    return
                self._json(404, {"error": "not found"})

            def do_POST(self) -> None:
                length = int(self.headers.get("content-length") or 0)
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    body = {}
                if self.path.startswith("/hook/"):
                    with api.lock:
                        api.hooks.append(self.path.removeprefix("/hook/"))
                    self._json(200, {})
                    return
                if "count_tokens" in self.path:
                    self._json(200, {"input_tokens": 10})
                    return
                api.answer(self, body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> ScriptedAPI:
        self.thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.server.shutdown()
        self.server.server_close()

    def answer(self, handler: BaseHTTPRequestHandler, body: dict) -> None:
        tools = {t.get("name") for t in body.get("tools") or [] if isinstance(t, dict)}
        results = [
            c
            for m in body.get("messages") or []
            if isinstance(m, dict) and isinstance(m.get("content"), list)
            for c in m["content"]
            if isinstance(c, dict) and c.get("type") == "tool_result"
        ]
        with self.lock:
            self.requests += 1
            if results:
                self.results = results
        if "Bash" not in tools:
            blocks, stop = [{"type": "text", "text": "ok"}], "end_turn"
        elif len(results) < len(self.turns):
            blocks, stop = self.turns[len(results)], "tool_use"
        else:
            blocks, stop = [{"type": "text", "text": "Probe finished.\nFINAL: done"}], "end_turn"
        model = str(body.get("model") or "scripted")
        if not body.get("stream"):
            payload = {
                "id": "msg_scripted",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [b for b in blocks if b["type"] == "text"] or [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
            data = json.dumps(payload).encode()
            handler.send_response(200)
            handler.send_header("content-type", "application/json")
            handler.send_header("content-length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return
        handler.send_response(200)
        handler.send_header("content-type", "text/event-stream")
        handler.end_headers()
        for name, data in _sse_events(blocks, stop, model):
            handler.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())
            handler.wfile.flush()

    def result_text(self, tool_use_id: str) -> tuple[str, bool]:
        for block in self.results:
            if block.get("tool_use_id") == tool_use_id:
                content = block.get("content")
                if isinstance(content, list):
                    content = "\n".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
                return str(content or ""), bool(block.get("is_error"))
        return "", True


def _sse_events(blocks: list[dict], stop_reason: str, model: str) -> list[tuple[str, dict]]:
    start = {
        "id": "msg_scripted",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    events: list[tuple[str, dict]] = [("message_start", {"type": "message_start", "message": start})]
    for i, block in enumerate(blocks):
        if block["type"] == "text":
            opening = {"type": "text", "text": ""}
            delta = {"type": "text_delta", "text": block["text"]}
        else:
            opening = {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}
            delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
        events.append(
            ("content_block_start", {"type": "content_block_start", "index": i, "content_block": opening})
        )
        events.append(("content_block_delta", {"type": "content_block_delta", "index": i, "delta": delta}))
        events.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
    events.append(
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 5},
            },
        )
    )
    events.append(("message_stop", {"type": "message_stop"}))
    return events


def _tool(tool_id: str, name: str, **arguments: Any) -> list[dict]:
    return [{"type": "tool_use", "id": tool_id, "name": name, "input": arguments}]


def _hook_plugin(directory: Path, port: int, marker_dir: Path) -> Path:
    """A session plugin whose hooks post to the scripted API and touch a marker outside the cell."""
    (directory / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (directory / "hooks").mkdir(exist_ok=True)
    (directory / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "probe-hooks", "version": "0.0.1", "description": "sandbox check"}),
        encoding="utf-8",
    )
    script = directory / "hook.sh"
    script.write_text(
        "cat >/dev/null\n"
        f'touch "{marker_dir}/hook-$1"\n'
        f'curl -s -m 5 -X POST -d "{{}}" "http://127.0.0.1:{port}/hook/$1" >/dev/null 2>&1\n'
        "exit 0\n",
        encoding="utf-8",
    )

    def group(event: str) -> dict:
        entry: dict[str, Any] = {
            "hooks": [{"type": "command", "command": f"/bin/sh {script} {event}", "timeout": 15}]
        }
        if event in ("PreToolUse", "PostToolUse"):
            entry["matcher"] = "*"
        return entry

    hooks = {"hooks": {e: [group(e)] for e in ("SessionStart", "PreToolUse", "PostToolUse", "Stop")}}
    (directory / "hooks" / "hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
    return directory


@dataclass(slots=True)
class CheckResult:
    profile: str
    claude_version: str
    sandboxed: bool
    problems: list[str] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def check(
    claude_bin: str,
    work_root: Path,
    model: str = "claude-opus-5-5",
    permission_mode: str = "dontAsk",
    allowed_tools: tuple[str, ...] = (),
    sandboxed: bool = True,
    timeout_s: int = 240,
) -> CheckResult:
    """Run the real Claude Code binary, with a cell's flags and settings, against the
    scripted API, and check that the sandbox holds. No model call; no credential.

    ``sandboxed=False`` is the negative control: the same probe without the settings must
    see every escape succeed (it proves the probe can tell the difference).
    """
    from truthstone.bench.codex.claude import ISOLATION_FLAGS, claude_version  # no import cycle

    version = claude_version(claude_bin)
    result = CheckResult(PROFILE, version, sandboxed)
    root = homes.private_dir(work_root / homes.neutral_name("sandbox-check", time.time()))
    cell_parent = Path(tempfile.mkdtemp(prefix="k", dir="/private/tmp")).resolve()
    repo = homes.private_dir(cell_parent / "w")
    tmpdir = homes.private_dir(cell_parent / "t")
    sibling = homes.private_dir(cell_parent.parent / f"{cell_parent.name}-sibling")
    outside = homes.private_dir(root / "outside")
    hidden = homes.private_dir(root / "hidden")
    (hidden / "config.toml").write_text("observe_only = true\n", encoding="utf-8")
    readable = homes.private_dir(hidden / "readable")
    (readable / "ok.txt").write_text("readable\n", encoding="utf-8")
    scratch_home = homes.private_dir(root / "home")
    config = homes.private_dir(root / "config")
    markers = homes.private_dir(root / "markers")
    slash_tmp = Path("/tmp") / f"{cell_parent.name}-slash"
    # As in a real cell, the account's config directory is among the hidden paths: Claude
    # Code itself (not sandboxed) must keep working when its Bash cannot read it.
    paths = SandboxPaths(deny_read=_unique([hidden, config]), allow_read=_unique([readable]))
    secret_env = naming.ENV_HOME
    try:
        api = ScriptedAPI([])
        bash = (
            'touch inside.txt && echo "PROBE inside ok"\n'
            f'touch "$TMPDIR/probe.txt" && echo "PROBE tmpdir ok"\n'
            f'touch "{outside}/bash.txt" && echo "PROBE outside WROTE"\n'
            f'touch "{sibling}/bash.txt" && echo "PROBE sibling WROTE"\n'
            f'touch "{slash_tmp}" && echo "PROBE slash-tmp WROTE"\n'
            f'cat "{hidden}/config.toml" && echo "PROBE hidden READ"\n'
            f'cat "{readable}/ok.txt" && echo "PROBE readable ok"\n'
            f'[ -n "${secret_env}" ] && echo "PROBE env VISIBLE" || echo "PROBE env hidden"\n'
            'curl -sS -m 5 -o /dev/null https://example.com && echo "PROBE proxy NET"\n'
            "curl --noproxy '*' -sS -m 5 -o /dev/null https://example.com && echo \"PROBE direct NET\"\n"
            f"curl --noproxy '*' -fsS -m 5 -o /dev/null http://127.0.0.1:{api.port}/ping && "
            'echo "PROBE loopback NET"\n'
            "/usr/bin/python3 -c \"import socket; socket.create_connection(('1.1.1.1', 443), timeout=3); "
            "print('PROBE socket NET')\"\n"
            "echo PROBE end\n"
        )
        api.turns = [
            _tool("toolu_bash", "Bash", command=bash, description="sandbox probe"),
            _tool("toolu_write_out", "Write", file_path=str(outside / "write.txt"), content="x\n"),
            _tool("toolu_write_in", "Write", file_path=str(repo / "write.txt"), content="y\n"),
            _tool("toolu_write_tmp", "Write", file_path=str(tmpdir / "write.txt"), content="z\n"),
            _tool("toolu_read_hidden", "Read", file_path=str(hidden / "config.toml")),
        ]
        with api:
            plugin = _hook_plugin(root / "plugin", api.port, markers)
            settings_path = root / "cell-settings.json"
            if sandboxed:
                write_cell_settings(settings_path, repo, tmpdir, paths)
            env = {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "HOME": str(scratch_home),
                "SHELL": "/bin/zsh",
                "USER": os.environ.get("USER", "dev"),
                "LANG": "en_US.UTF-8",
                "TMPDIR": str(tmpdir),
                "CLAUDE_CONFIG_DIR": str(config),
                "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{api.port}",
                "ANTHROPIC_API_KEY": "sk-ant-scripted-sandbox-check-not-a-key",
                "DISABLE_AUTOUPDATER": "1",
                "DISABLE_TELEMETRY": "1",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                secret_env: str(hidden),
                **cell_env(tmpdir),
            }
            tools = list(allowed_tools) or ["Bash", "Read", "Glob", "Grep"]
            if not sandboxed:
                tools += ["Edit", "Write"]  # the negative control allows them bare
            argv = [
                claude_bin,
                "-p",
                "Run the sandbox probe.",
                "--output-format",
                "stream-json",
                "--verbose",
                "--model",
                model,
                "--permission-mode",
                permission_mode,
                "--no-session-persistence",
                "--allowedTools",
                ",".join(plan_tools(tools) if sandboxed else tools),
                "--plugin-dir",
                str(plugin),
                *ISOLATION_FLAGS,
            ]
            if sandboxed:
                argv += ["--settings", str(settings_path)]
            proc = subprocess.run(argv, cwd=repo, env=env, capture_output=True, text=True, timeout=timeout_s)
            bash_out, _ = api.result_text("toolu_bash")
            outcomes = {
                tool_id: api.result_text(tool_id)
                for tool_id in ("toolu_write_out", "toolu_write_in", "toolu_write_tmp", "toolu_read_hidden")
            }
            hooks_seen = sorted(set(api.hooks))
            requests = api.requests
        probes = sorted({line.strip() for line in bash_out.splitlines() if line.startswith("PROBE ")})
        files = {
            "bash_inside": (repo / "inside.txt").exists(),
            "bash_outside": (outside / "bash.txt").exists(),
            "bash_sibling": (sibling / "bash.txt").exists(),
            "bash_slash_tmp": slash_tmp.exists(),
            "write_outside": (outside / "write.txt").exists(),
            "write_inside": (repo / "write.txt").exists(),
            "write_tmp": (tmpdir / "write.txt").exists(),
        }
        read_text, read_error = outcomes["toolu_read_hidden"]
        result.observations = {
            "exit_code": proc.returncode,
            "api_requests": requests,
            "probes": probes,
            "files": files,
            "read_hidden_refused": read_error or "observe_only" not in read_text,
            "hooks_seen": hooks_seen,
            "hook_markers": sorted(p.name for p in markers.iterdir()),
            "stderr_tail": proc.stderr[-400:],
        }
        if requests == 0 or "PROBE end" not in probes:
            result.problems.append(
                f"the probe did not run (exit {proc.returncode}, {requests} API request(s)): "
                f"{proc.stderr[-300:]}"
            )
            return result
        escaped = [
            name
            for name, happened in (
                ("Bash wrote outside the cell", files["bash_outside"]),
                ("Bash wrote to a sibling under /private/tmp", files["bash_sibling"]),
                ("Bash wrote to /tmp", files["bash_slash_tmp"]),
                ("Bash read a hidden path", "PROBE hidden READ" in probes),
                ("Bash saw the arm's environment", "PROBE env VISIBLE" in probes),
                ("Bash reached the network through the proxy", "PROBE proxy NET" in probes),
                ("Bash reached the network directly", "PROBE direct NET" in probes),
                ("Bash reached a loopback server", "PROBE loopback NET" in probes),
                ("a raw socket reached the network", "PROBE socket NET" in probes),
                ("the Write tool wrote outside the cell", files["write_outside"]),
                ("the Read tool read a hidden path", not result.observations["read_hidden_refused"]),
            )
            if happened
        ]
        allowed = [
            name
            for name, happened in (
                ("Bash could not write inside the cell", files["bash_inside"]),
                ("Bash could not write to its TMPDIR", "PROBE tmpdir ok" in probes),
                ("Bash could not read the task interpreter's re-opened path", "PROBE readable ok" in probes),
                ("the Write tool could not write inside the cell", files["write_inside"]),
                ("the Write tool could not write to the cell's temp directory", files["write_tmp"]),
            )
            if not happened
        ]
        hooks_ok = {"SessionStart", "PreToolUse", "Stop"} <= set(hooks_seen)
        if sandboxed:
            result.problems += [f"escape: {e}" for e in escaped]
            result.problems += [f"over-confined: {a}" for a in allowed]
            if not hooks_ok:
                result.problems.append(f"hooks did not reach loopback from outside the sandbox: {hooks_seen}")
        else:
            # The control must see the escapes the sandbox prevents, or the probe proves nothing.
            needed = {
                "Bash wrote outside the cell",
                "Bash read a hidden path",
                "Bash saw the arm's environment",
                "Bash reached a loopback server",
                "the Write tool wrote outside the cell",
                "the Read tool read a hidden path",
            }
            missing = sorted(needed - set(escaped))
            if missing:
                result.problems.append(f"negative control: the unsandboxed probe did not observe {missing}")
        return result
    finally:
        for path in (cell_parent, sibling, root):
            shutil.rmtree(path, ignore_errors=True)
        slash_tmp.unlink(missing_ok=True)
