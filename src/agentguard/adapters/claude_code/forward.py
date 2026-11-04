"""Hot-path forwarder for command hooks: stdin -> AgentGuard daemon -> stdout.

Why a command hook, and why this file
-------------------------------------
Settings-based installs reach the daemon through Claude Code ``http`` hooks, which carry
the local bearer token in a header. A *plugin* cannot do that. Measured on Claude Code
2.1.317 (see ``docs/CLAUDE-PLUGIN.md``): a plugin ``http`` hook interpolates header values
only from variables already in Claude Code's own launch environment — never
``${CLAUDE_PLUGIN_ROOT}``/``${CLAUDE_PLUGIN_DATA}``, and never anything a ``SessionStart``
hook writes to ``CLAUDE_ENV_FILE``. A per-user secret therefore cannot reach the header
without the user exporting it by hand, so the plugin uses ``command`` hooks, and every
tool call pays for one process. This module keeps that process as cheap as Python allows:

* it runs as a **file**, ``python -I -S forward.py``: no ``site`` (no site-packages scan,
  no ``.pth`` processing), no user site, no ``PYTHON*`` variables, and — the security
  half — no working directory on ``sys.path``. Hooks run inside the user's repository, so
  a repository file named ``json.py`` must never be importable here;
* it imports only builtin C modules: ``_socket`` instead of ``socket`` (whose ``enum``
  import costs ~2 ms) and ``_json`` instead of ``json`` (whose ``re`` import costs
  ~7 ms). The scanner below *is* CPython's JSON parser, minus the regex wrappers;
* it makes **one** request. There is no ``/health`` probe first: a refused connection is
  the probe, and it fails open in microseconds. Liveness checks, revival and the visible
  "unguarded" warning happen once per prompt, in ``plugin.py``, not once per tool call.

It must stay standalone: no ``agentguard`` imports (the package is not importable under
``-S``), standard library only.

Two safety properties are enforced here, at the transport boundary, so they hold even if a
daemon bug — or a foreign process squatting on the daemon's port — produces bad output:

* **AgentGuard never grants permissions.** A response carrying ``permissionDecision:
  "allow"`` is dropped, which is the same as saying nothing.
* **Fail open.** Every failure — no handshake, refused connection, timeout, non-200,
  unparsable body — exits 0 with no output, so the agent proceeds as if AgentGuard were
  not installed. Exit code 2 (which would *block* the agent) is never used.
"""

from __future__ import annotations

import _json
import _socket
import os
import sys

MAX_STDIN_BYTES = 1_000_000
MAX_RESPONSE_BYTES = 64_000
DEFAULT_TIMEOUT_S = 4.0
HOOK_PATH = "/hook/claude-code"
_TRUE = ("1", "true", "yes", "on")


class _Ctx:
    """The attribute bag ``_json.make_scanner`` reads: ``json.decoder``'s defaults.

    This is a private CPython interface and it does change — 3.15 added ``array_hook`` —
    so construction is guarded below and falls back to the public ``json`` module.
    """

    strict = True
    object_hook = None
    object_pairs_hook = None
    array_hook = None
    parse_float = float
    parse_int = int
    memo: dict = {}  # noqa: RUF012 - read by the C scanner, never mutated here

    @staticmethod
    def parse_constant(name: str) -> float:
        return {"-Infinity": float("-inf"), "Infinity": float("inf"), "NaN": float("nan")}[name]


try:
    _scan = _json.make_scanner(_Ctx())
except Exception:  # noqa: BLE001 - a newer CPython's scanner wants more; use the public API
    _scan = None


def loads(text: str) -> object:
    """Parse one JSON document with the C scanner. Raises ``ValueError`` on bad input."""
    if _scan is None:
        import json  # ~7 ms, only on a CPython whose private scanner contract moved

        return json.loads(text)
    start = len(text) - len(text.lstrip(" \t\n\r"))
    try:
        value, end = _scan(text, start)
    except StopIteration as exc:  # the C scanner's "no value here"
        raise ValueError("not JSON") from exc
    if text[end:].strip(" \t\n\r"):
        raise ValueError("trailing data")
    return value


# Former product names, newest first, as (display, slug, upper): the registry in
# agentguard/names.py, which this file cannot import. scripts/rename_product.py records a
# rename in both, and tests/test_names.py keeps them equal.
# rename-tool: keep-begin former-names
FORMER: tuple[tuple[str, str, str], ...] = ()
# rename-tool: keep-end


def setting(key: str) -> str:
    """``AGENTGUARD_<key>``, else the same setting under a former name; ``""`` if unset.

    The rule of ``names.env``: the first non-empty value wins, the current name first.
    """
    for upper in ("AGENTGUARD", *(former[2] for former in FORMER)):
        value = os.environ.get(upper + "_" + key)
        if value:
            return value
    return ""


def agentguard_home() -> str:
    """The rule of ``names.data_dir``: ``$AGENTGUARD_HOME``, else ``~/.agentguard``, unless
    only a former name's directory exists."""
    explicit = setting("HOME")
    if explicit:
        return os.path.expanduser(explicit)
    home = os.path.expanduser("~/.agentguard")
    if not os.path.lexists(home):
        for former in FORMER:
            candidate = os.path.expanduser("~/." + former[1])
            if os.path.lexists(candidate):
                return candidate
    return home


def read_handshake(home: str) -> dict | None:
    """``daemon.json``, or ``None``. A symlinked handshake is refused, as in the shim."""
    path = os.path.join(home, "daemon.json")
    try:
        if os.path.islink(path):
            return None
        with open(path, "rb") as fh:
            raw = fh.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return None
        data = loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def loopback_ipv4(host: object) -> str | None:
    """The daemon binds IPv4 loopback only; refuse to send the token anywhere else."""
    if not isinstance(host, str):
        return None
    host = host.strip()
    if host.lower() == "localhost":
        return "127.0.0.1"
    parts = host.split(".")
    if len(parts) != 4 or not all(p.isdigit() and len(p) <= 3 for p in parts):
        return None
    octets = [int(p) for p in parts]
    if octets[0] != 127 or any(o > 255 for o in octets):
        return None
    return ".".join(str(o) for o in octets)


def endpoint_of(hs: dict) -> tuple[str, int, str] | None:
    """``(host, port, token)`` from a handshake, or ``None`` if any part is unsafe."""
    host = loopback_ipv4(hs.get("host", "127.0.0.1"))
    port = hs.get("port")
    token = hs.get("token")
    if host is None or type(port) is not int or not 0 < port <= 65535:
        return None
    if not isinstance(token, str) or not token or not token.isascii():
        return None
    if any(c in token for c in "\r\n "):
        return None  # header injection
    return host, port, token


def _dechunk(body: bytes) -> bytes:
    out = bytearray()
    while True:
        line, sep, rest = body.partition(b"\r\n")
        if not sep:
            raise ValueError("truncated chunk header")
        size = int(line.split(b";", 1)[0].strip() or b"0", 16)
        if size == 0:
            return bytes(out)
        if len(rest) < size:
            raise ValueError("truncated chunk")
        out += rest[:size]
        body = rest[size + 2 :]


def post(host: str, port: int, token: str, body: bytes, timeout: float) -> bytes:
    """One HTTP/1.1 POST over a raw socket; the 200 response body, or ``b""``."""
    head = (
        f"POST {HOOK_PATH} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Content-Type: application/json\r\n"
        f"Authorization: Bearer {token}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.sendall(head + body)
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES + 16_384:
                return b""
            chunks.append(chunk)
    finally:
        sock.close()

    raw = b"".join(chunks)
    header, sep, payload = raw.partition(b"\r\n\r\n")
    if not sep:
        return b""
    lines = header.split(b"\r\n")
    status = lines[0].split()
    if len(status) < 2 or status[1] != b"200":
        return b""
    for line in lines[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"transfer-encoding" and b"chunked" in value.lower():
            return _dechunk(payload)
    return payload


def grants_permission(response: dict) -> bool:
    """Whether a response would approve a tool call on the developer's behalf."""
    specific = response.get("hookSpecificOutput")
    if isinstance(specific, dict):
        if specific.get("permissionDecision") == "allow":
            return True
        decision = specific.get("decision")  # PermissionRequest shape
        if isinstance(decision, dict) and decision.get("behavior") == "allow":
            return True
    return response.get("decision") == "approve"  # legacy alias of "allow"


def standing_down() -> bool:
    """Whether the plugin must stay silent because settings hooks already cover this.

    ``plugin.py`` writes these markers at SessionStart when it finds AgentGuard's
    settings-based hooks in a settings file Claude Code reads for this project. Both
    installs would otherwise handle every event, and the daemon would count each tool
    call, challenge and completion-gate hold twice.
    """
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data:
        return False
    marks = os.path.join(data, "standdown")
    if os.path.exists(os.path.join(marks, "user")):
        return True
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    return bool(project) and os.path.exists(os.path.join(marks, project_key(project)))


def project_key(project_dir: str) -> str:
    """A filename for a project directory, shared by writer (plugin.py) and reader."""
    key = "".join(c if c.isalnum() else "-" for c in project_dir)
    return "project" + key[-200:]


def _timeout(argv: list[str]) -> float:
    if "--timeout" in argv:
        try:
            value = float(argv[argv.index("--timeout") + 1])
        except (IndexError, ValueError):
            return DEFAULT_TIMEOUT_S
        if 0 < value <= 60:
            return value
    return DEFAULT_TIMEOUT_S


def run(argv: list[str], stdin: object, stdout: object) -> int:
    """Forward one hook event. Always returns 0: AgentGuard never blocks by crashing."""
    try:
        if setting("DISABLE").strip().lower() in _TRUE:
            return 0
        if standing_down():
            return 0
        body = stdin.read(MAX_STDIN_BYTES + 1)
        if not body or len(body) > MAX_STDIN_BYTES or not body.strip():
            return 0
        hs = read_handshake(agentguard_home())
        target = endpoint_of(hs) if hs else None
        if target is None:
            return 0
        raw = post(*target, body, _timeout(argv))
        if not raw:
            return 0
        response = loads(raw.decode("utf-8"))
        if not isinstance(response, dict) or not response or grants_permission(response):
            return 0
        stdout.write(raw)
        stdout.flush()
    except Exception:  # noqa: BLE001 - fail open: any failure means "no decision"
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:], sys.stdin.buffer, sys.stdout.buffer))
