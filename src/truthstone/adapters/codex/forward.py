"""The Codex plugin's lean forwarder: stdin -> Truthstone daemon (/hook/codex) -> stdout.

Codex runs every hook as a process, so every tool call pays for one. The plugin launcher
used to start ``truthstone-codex-hook``, a console script: Python with ``site`` (the
site-packages scan, ``.pth`` files), the ``truthstone`` package and ``json``/``socket``.
About 31 ms p50 and 34 ms p95 end to end, above the 30 ms budget (WP9). For the events
that only forward (PreToolUse, PostToolUse, Stop, SubagentStop, SessionEnd), the launcher
now runs this file instead, the way the Claude plugin runs its own forwarder:

    <runtime python> -I -S forward.py --timeout <s>

* ``-I``: no user site, no ``PYTHON*`` variables and — the ``-P`` safety — no working
  directory on ``sys.path``. Hooks run inside the user's repository, so a repository file
  named ``json.py`` must never be importable here. ``-S``: no ``site`` at all.
* Builtin C modules only: ``_json`` and ``_socket``, not ``json`` (``re``) or ``socket``
  (``enum``).
* One request, no ``/health`` probe. A dead daemon PID in the handshake is skipped for free;
  a refused connection costs microseconds.

SessionStart and UserPromptSubmit keep the full ``truthstone-codex-hook`` (it starts or
revives the daemon and says once when a session is unguarded); SessionStart also installs
this file and the interpreter it runs under into the plugin's data directory, so the two can
never drift apart for longer than a session.

It must stay standalone: no ``truthstone`` imports (the package is not importable under
``-S``), standard library only. It resolves the home exactly as every other entry point
does (``daemon/private_paths.py``, R11): ``TRUTHSTONE_HOME`` or ``~/.truthstone``, former
names included, through links only root or this user could have placed, else nothing.
``tests/test_codex_forward.py`` keeps the two in step.

Safety, enforced here at the transport boundary: Truthstone never grants a permission (a
response carrying ``permissionDecision: "allow"`` is dropped), and every failure exits 0 with
no output (fail open). Exit code 2, which Codex reads as "block", is never used.
"""

from __future__ import annotations

import _json
import _socket
import os
import stat
import sys

MAX_STDIN_BYTES = 1_000_000
MAX_RESPONSE_BYTES = 256_000
DEFAULT_TIMEOUT_S = 4.0
HOOK_PATH = "/hook/codex"
_TRUE = ("1", "true", "yes", "on")

# Former product names, newest first, as (display, slug, upper): the registry in
# truthstone/names.py, which this file cannot import. tests/test_codex_forward.py keeps them equal.
# rename-tool: keep-begin former-names
FORMER: tuple[tuple[str, str, str], ...] = (("AgentGuard", "agentguard", "AGENTGUARD"),)
# rename-tool: keep-end

ROOT_UID = 0
SYSTEM_ALIASES = {"/tmp": "/private/tmp", "/var": "/private/var"}


class _Ctx:
    """The attribute bag ``_json.make_scanner`` reads (``json.decoder``'s defaults)."""

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
    """One JSON document, parsed by the C scanner. Raises ``ValueError`` on bad input."""
    if _scan is None:
        import json  # only on a CPython whose private scanner contract moved

        return json.loads(text)
    start = len(text) - len(text.lstrip(" \t\n\r"))
    try:
        value, end = _scan(text, start)
    except StopIteration as exc:
        raise ValueError("not JSON") from exc
    if text[end:].strip(" \t\n\r"):
        raise ValueError("trailing data")
    return value


def setting(key: str) -> str:
    """``TRUTHSTONE_<key>``, else the same setting under a former name; ``""`` if unset."""
    for upper in ("TRUTHSTONE", *(former[2] for former in FORMER)):
        value = os.environ.get(upper + "_" + key)
        if value:
            return value
    return ""


def configured_home() -> str:
    """``private_paths.configured_home``: the variable, else ``~/.truthstone`` unless only a
    former name's directory exists."""
    explicit = setting("HOME")
    if explicit:
        return os.path.expanduser(explicit)
    home = os.path.expanduser("~/.truthstone")
    if not os.path.lexists(home):
        for former in FORMER:
            candidate = os.path.expanduser("~/." + former[1])
            if os.path.lexists(candidate):
                return candidate
    return home


def _trusted_system_link(path: str, mode: int | None = None) -> bool:
    try:
        info = os.lstat(path)
        mode = info.st_mode if mode is None else mode
        target = SYSTEM_ALIASES.get(path)
        if target is not None:
            return info.st_uid == 0 and mode & 0o022 == 0 and os.path.realpath(path) == target
        if info.st_uid != ROOT_UID:
            return False
        parent = os.stat(os.path.dirname(path) or os.sep)
        return parent.st_uid == ROOT_UID and not parent.st_mode & 0o022
    except (OSError, ValueError):
        return False


def _trusted_home_link(path: str) -> bool:
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        return False
    try:
        info = os.lstat(path)
        if _trusted_system_link(path, info.st_mode):
            return True
        parent = os.stat(os.path.dirname(path) or os.sep)
    except (OSError, ValueError):
        return False
    owners = (ROOT_UID, getuid())
    if info.st_uid not in owners or parent.st_uid not in owners:
        return False
    return not parent.st_mode & 0o022 or bool(parent.st_mode & stat.S_ISVTX)


def resolve_home(home: str) -> tuple[str, bool]:
    """``private_paths.resolve_home``: ``(path, trusted)``."""
    try:
        absolute = home if os.path.isabs(home) else os.path.join(os.getcwd(), home)
        absolute = os.sep + os.sep.join(part for part in absolute.split(os.sep) if part not in ("", "."))
        links: list[str] = []
        current = absolute
        while True:
            try:
                if stat.S_ISLNK(os.lstat(current).st_mode) and current not in SYSTEM_ALIASES:
                    links.append(current)
            except OSError:
                pass
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        if not links:
            return home, True
        if all(_trusted_home_link(link) for link in links):
            return os.path.realpath(absolute), True
        return home, False
    except (OSError, ValueError):
        return home, False


def read_handshake() -> dict | None:
    """``daemon.json`` from a trusted home, or ``None``. A symlinked handshake is refused."""
    home, trusted = resolve_home(configured_home())
    if not trusted:
        return None
    path = os.path.join(home, "daemon.json")
    try:
        if os.path.islink(path):
            return None
        with open(path, "rb") as fh:
            raw = fh.read(64_001)
        if len(raw) > 64_000:
            return None
        data = loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def endpoint_of(hs: dict) -> tuple[str, int, str] | None:
    """``(host, port, token)`` from a handshake whose daemon is alive, or ``None``: IPv4
    loopback only, a sane token, and a PID that exists (a dead daemon is skipped for free)."""
    host = hs.get("host", "127.0.0.1")
    if host == "localhost":
        host = "127.0.0.1"
    parts = host.split(".") if isinstance(host, str) else []
    if len(parts) != 4 or parts[0] != "127" or not all(p.isdigit() and int(p) < 256 for p in parts):
        return None
    port, token, pid = hs.get("port"), hs.get("token"), hs.get("pid")
    if type(port) is not int or not 0 < port <= 65535:
        return None
    if not isinstance(token, str) or not token or not token.isascii() or any(c in token for c in "\r\n "):
        return None
    if type(pid) is not int or pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except (OSError, OverflowError, ValueError):
        return None
    return host, port, token


def post(host: str, port: int, token: str, body: bytes, timeout: float) -> bytes:
    """One HTTP/1.1 POST over a raw socket; the 200 response body, or ``b""``."""
    head = (
        f"POST {HOOK_PATH} HTTP/1.1\r\nHost: {host}:{port}\r\n"
        f"Content-Type: application/json\r\nAuthorization: Bearer {token}\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    ).encode("ascii")
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    chunks: list[bytes] = []
    size = 0
    try:
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.sendall(head + body)
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                return b""
            chunks.append(chunk)
    finally:
        sock.close()
    header, sep, payload = b"".join(chunks).partition(b"\r\n\r\n")
    if not sep:
        return b""
    status = header.split(b"\r\n", 1)[0].split()
    if len(status) < 2 or status[1] != b"200":
        return b""
    if b"transfer-encoding: chunked" in header.lower():
        return b""  # the daemon always sends Content-Length; anything else is not ours
    return payload


def grants_permission(response: dict) -> bool:
    """Whether a response would approve a tool call on the developer's behalf."""
    specific = response.get("hookSpecificOutput")
    if isinstance(specific, dict) and specific.get("permissionDecision") == "allow":
        return True
    return response.get("decision") == "approve"


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
    """Forward one hook event. Always returns 0: Truthstone never blocks by crashing."""
    try:
        if setting("DISABLE").strip().lower() in _TRUE:
            return 0
        body = stdin.read(MAX_STDIN_BYTES + 1)
        if not body or len(body) > MAX_STDIN_BYTES or not body.strip():
            return 0
        hs = read_handshake()
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
