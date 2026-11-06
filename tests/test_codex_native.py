"""The Codex plugin's native forwarder, ``forward_native.c``: forward.py in C.

``forward.py`` is the specification. Against the same loopback stand-in for the daemon, the two
must send byte-identical requests and print byte-identical output: the reply passed through
untouched, a grant never, and nothing at all when anything is wrong. Every run exits 0 (Codex
reads 2 as "block this tool call"). The few places where the C is deliberately stricter
(failing open where Python would carry on) are tested as such.

Then the build: SessionStart compiles it in the background, once per version, into a private
directory; without a compiler (or after any failure) there is no binary, and the plugin's
launcher keeps to the Python forwarder. What needs a C compiler is skipped without one.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from truthstone import names
from truthstone.adapters.codex import forward, hook
from truthstone.adapters.codex import native as builder

SOURCE = Path(forward.__file__).with_name("forward_native.c")
FORWARD = Path(forward.__file__)
PAYLOADS = Path(__file__).parent / "fixtures" / "codex_payloads"
CC = shutil.which("cc")

needs_cc = pytest.mark.skipif(CC is None, reason="needs a C compiler")


@pytest.fixture(scope="module")
def native(tmp_path_factory) -> Path:
    """The forwarder, compiled as SessionStart compiles it (``cc -O2``)."""
    if CC is None:
        pytest.skip("needs a C compiler")
    binary = tmp_path_factory.mktemp("native") / "forward-native"
    subprocess.run([CC, "-O2", "-o", str(binary), str(SOURCE)], check=True, capture_output=True, timeout=120)
    return binary


class _RawDaemon:
    """A loopback stand-in for the daemon that speaks raw bytes: it records every request
    exactly as it arrived, then answers with ``response`` (a whole HTTP response), or holds
    the connection open without a word (``hang``), or closes it unread (``slam``)."""

    def __init__(self, response: bytes = b"", hang: bool = False, slam: bool = False) -> None:
        self.requests: list[bytes] = []
        self.response, self.hang, self.slam = response, hang, slam
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(16)
        self.listener.settimeout(0.05)
        self.port = self.listener.getsockname()[1]
        self.held: list[socket.socket] = []
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        while not self.stopped.is_set():
            try:
                conn, _ = self.listener.accept()
            except OSError:
                continue
            try:
                if self.slam:
                    conn.close()
                    continue
                self.requests.append(self._read(conn))
                if self.hang:
                    self.held.append(conn)
                    continue
                conn.sendall(self.response)
                conn.close()
            except OSError:
                conn.close()

    @staticmethod
    def _read(conn: socket.socket) -> bytes:
        conn.settimeout(10)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                return data
            data += chunk
        head, _, body = data.partition(b"\r\n\r\n")
        length = 0
        for line in head.split(b"\r\n")[1:]:
            name, _, value = line.partition(b":")
            if name.strip().lower() == b"content-length":
                length = int(value.strip())
        while len(body) < length:
            chunk = conn.recv(65536)
            if not chunk:
                break
            body += chunk
        return head + b"\r\n\r\n" + body

    def close(self) -> None:
        self.stopped.set()
        self.thread.join(timeout=5)
        for conn in self.held:
            conn.close()
        self.listener.close()


def http(body: bytes, status: bytes = b"200 OK", headers: bytes = b"") -> bytes:
    """A response as uvicorn writes one, with any extra header lines."""
    return (
        b"HTTP/1.1 " + status + b"\r\nserver: uvicorn\r\ncontent-type: application/json\r\n"
        b"content-length: " + str(len(body)).encode() + b"\r\n" + headers + b"\r\n" + body
    )


DENY = json.dumps(
    {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Truthstone: no",
        }
    }
).encode()
PRE = (PAYLOADS / "PreToolUse.Bash.json").read_bytes()


@pytest.fixture
def daemon(isolated_home: Path):
    """Start a stand-in and point the home's handshake at it (``hs`` overrides its fields)."""
    servers: list[_RawDaemon] = []

    def start(response: bytes = b"", hs: dict | None = None, **mode: bool) -> _RawDaemon:
        server = _RawDaemon(response, **mode)
        servers.append(server)
        handshake = {"host": "127.0.0.1", "port": server.port, "token": "tok-123", "pid": os.getpid()}
        handshake.update(hs or {})
        (isolated_home / "daemon.json").write_text(json.dumps(handshake))
        return server

    yield start
    for server in servers:
        server.close()


def _env(isolated_home: Path, **extra: str | None) -> dict[str, str]:
    env = {"PATH": "/usr/bin:/bin", "HOME": str(isolated_home.parent), "TRUTHSTONE_HOME": str(isolated_home)}
    env.update(extra)
    return {k: v for k, v in env.items() if v is not None}


def _run(argv: list[str], payload: bytes, env: dict, cwd: Path | None = None, timeout: float = 60) -> bytes:
    proc = subprocess.run(argv, input=payload, capture_output=True, env=env, cwd=cwd, timeout=timeout)
    assert proc.returncode == 0, (argv[0], proc.returncode, proc.stderr)  # never 2, never anything but 0
    return proc.stdout


def _native(binary: Path, payload: bytes, env: dict, *args: str, cwd: Path | None = None) -> bytes:
    out = subprocess.run(
        [str(binary), *(args or ("--timeout", "4"))],
        input=payload,
        capture_output=True,
        env=env,
        cwd=cwd,
        timeout=60,
    )
    assert out.returncode == 0 and out.stderr == b"", (out.returncode, out.stderr)
    return out.stdout


def _python(payload: bytes, env: dict, *args: str, cwd: Path | None = None) -> bytes:
    return _run([sys.executable, "-I", "-S", str(FORWARD), *(args or ("--timeout", "4"))], payload, env, cwd)


def both(binary: Path, server: _RawDaemon, payload: bytes, env: dict, cwd: Path | None = None) -> bytes:
    """Run the native forwarder, then forward.py; they must agree on the request and the output.
    Returns that output."""
    before = len(server.requests)
    ours = _native(binary, payload, env, cwd=cwd)
    sent = server.requests[before:]
    theirs = _python(payload, env, cwd=cwd)
    assert ours == theirs, (ours, theirs)
    assert sent == server.requests[before + len(sent) :], "the two forwarders sent different requests"
    return ours


# -- the protocol ------------------------------------------------------------------------------


def test_it_posts_the_payload_to_the_codex_route_and_prints_the_reply(native, daemon, isolated_home):
    server = daemon(http(DENY))
    assert _native(native, PRE, _env(isolated_home)) == DENY
    (request,) = server.requests
    assert request == (
        b"POST /hook/codex HTTP/1.1\r\nHost: 127.0.0.1:" + str(server.port).encode() + b"\r\n"
        b"Content-Type: application/json\r\nAuthorization: Bearer tok-123\r\n"
        b"Content-Length: " + str(len(PRE)).encode() + b"\r\nConnection: close\r\n\r\n" + PRE
    )


@pytest.mark.parametrize("fixture", sorted(p.name for p in PAYLOADS.glob("*.json")))
def test_recorded_payloads_are_forwarded_exactly_as_forward_py_does(native, daemon, isolated_home, fixture):
    payload = (PAYLOADS / fixture).read_bytes()
    context = json.dumps(
        {"hookSpecificOutput": {"hookEventName": "X", "additionalContext": "é ✓ \u2028"}}, ensure_ascii=False
    ).encode()
    replies = [
        DENY,
        context,
        b'{"decision": "block", "reason": "hold"}',
        b'{"systemMessage": "x"}\n',
        b'{"hookSpecificOutput": {"permissionDecision": "allow"}}',
    ]
    for reply in replies:
        server = daemon(http(reply))
        out = both(native, server, payload, _env(isolated_home))
        assert out == (b"" if b"allow" in reply else reply)
        assert server.requests[0].endswith(b"\r\n\r\n" + payload)


GRANTS = [
    b'{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}',
    b'{"decision": "approve"}',
    b'{"decision": "approve", "reason": "fine", "systemMessage": "x"}',
    b'{"hookSpecificOutput": {"permissionDecision": "\\u0061llow"}}',  # an escape is the same text
    b'{"\\u0064ecision": "approve"}',
    b'{"decision": "block", "decision": "approve"}',  # Python keeps the last duplicate
    b'{"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecision": "allow"}}',
    b'{"hookSpecificOutput": 1, "hookSpecificOutput": {"permissionDecision": "allow"}}',
    b' \n{"decision":"approve"}\r\n',
]


@pytest.mark.parametrize("reply", GRANTS)
def test_a_grant_is_never_printed(native, daemon, isolated_home, reply):
    server = daemon(http(reply))
    assert both(native, server, PRE, _env(isolated_home)) == b""


PASSED = [
    DENY,
    b'{"decision": "approve", "decision": "block"}',  # the last one counts
    b'{"hookSpecificOutput": {"permissionDecision": "allow"}, "hookSpecificOutput": {}}',
    b'{"hookSpecificOutput": {"permissionDecision": "allow", "permissionDecision": "ask"}}',
    b'{"hookSpecificOutput": "allow"}',
    b'{"hookSpecificOutput": {"permissionDecision": "ALLOW"}}',
    b'{"hookSpecificOutput": {"permissionDecision": "allow "}}',
    b'{"decision": "approved"}',
    b'{"decision": ["approve"]}',
    b'{"x": {"hookSpecificOutput": {"permissionDecision": "allow"}, "decision": "approve"}}',  # not top level
    b' \t\n\r{"a": 1} \n',  # surrounding whitespace is kept, byte for byte
    b'{"a": NaN, "b": Infinity, "c": -Infinity, "d": -0, "e": 1.5e-3, "f": 1E+5, "g": null, "h": true}',
    b'{"lone": "\\ud800", "pair": "\\ud83d\\ude00", "nul": "\\u0000", "esc": "\\"\\\\\\/\\b\\f\\n\\r\\t"}',
    '{"raw": "é ✓ 😀 \u2028", "del": "\x7f"}'.encode(),
    b'{"n": ' + b"9" * 4300 + b', "m": -' + b"9" * 4300 + b"}",  # CPython's longest integer
    b'{"f": ' + b"9" * 5000 + b".5}",  # floats have no digit limit
    b'{"d": ' + b"[" * 5000 + b"]" * 5000 + b"}",
    b'{"k": {}, "l": [], "m": [{}, [[]], {"a": [1, {"b": null}]}]}',
]


@pytest.mark.parametrize("reply", PASSED, ids=range(len(PASSED)))
def test_any_other_object_is_passed_through_byte_for_byte(native, daemon, isolated_home, reply):
    server = daemon(http(reply))
    assert both(native, server, PRE, _env(isolated_home)) == reply


NOT_PRINTED = [
    b"",
    b"   ",
    b"{}",
    b" {} ",
    b"[]",
    b'["decision"]',
    b'"text"',
    b"1",
    b"null",
    b"not json",
    b'{"a": 1} x',
    b'{"a": 1}{"b": 2}',
    b'{"a": 1,}',
    b'{"a": [1,]}',
    b"{'a': 1}",
    b"{a: 1}",
    b"{1: 2}",
    b'{"a" 1}',
    b'{"a": 1',
    b'{"a": "unterminated}',
    b'{"a": 01}',
    b'{"a": 1.}',
    b'{"a": .5}',
    b'{"a": 1e}',
    b'{"a": 1e+}',
    b'{"a": -}',
    b'{"a": +1}',
    b'{"a": tru}',
    b'{"a": True}',
    b'{"a": nan}',
    b'{"a": -NaN}',
    b'{"a": "\\x"}',
    b'{"a": "\\u12"}',
    b'{"a": "\\u12G4"}',
    b'{"a": "\x01"}',  # strict: no raw control characters
    b'{"a": "\t"}',
    b'{"n": ' + b"9" * 4301 + b"}",  # CPython's int_max_str_digits
    b'{"n": -' + b"9" * 4301 + b"}",
    b'{"a": "\xff"}',  # not UTF-8
    b'{"a": "\xc0\xaf"}',  # an overlong form
    b'{"a": "\xed\xa0\x80"}',  # a UTF-8 surrogate
    b'{"a": "\xf4\x90\x80\x80"}',  # above U+10FFFF
    b'{"a": "\xe2\x82"}',  # truncated
    b"\xef\xbb\xbf{}",  # a BOM
    b'\xef\xbb\xbf{"a": 1}',
    b'{"a": 1}\x00',
    b'{"a":\xc2\xa01}',  # a non-ASCII space is not JSON whitespace
    b"[" * 120000 + b"]" * 120000,  # deeper than any CPython reads
    b'{"d": ' + b"[" * 120000 + b"]" * 120000 + b"}",
]


@pytest.mark.parametrize("reply", NOT_PRINTED, ids=range(len(NOT_PRINTED)))
def test_anything_but_one_json_object_is_not_printed(native, daemon, isolated_home, reply):
    server = daemon(http(reply))
    assert both(native, server, PRE, _env(isolated_home)) == b""


RESPONSES = [
    (http(b'{"detail": "invalid hook token"}', status=b"401 Unauthorized"), b""),  # a wrong token
    (http(DENY, status=b"500 Internal Server Error"), b""),
    (http(DENY, status=b"204 No Content"), b""),
    (http(DENY, status=b"2000 OK"), b""),
    (http(DENY, status=b"200"), DENY),
    (b"HTTP/1.0  200\t OK\r\n\r\n" + DENY, DENY),
    (b"HTTP/1.1\n200 OK\r\n\r\n" + DENY, DENY),  # one line for "\r\n", two words for split()
    (b"HTTP/1.1 200 OK\r\n\r\n" + DENY + b"\r\n\r\nmore", b""),  # the payload is everything after
    (b"HTTP/1.1 200 OK\r\n\r\n" + DENY, DENY),
    (b"200 OK\r\n\r\n" + DENY, b""),
    (b"HTTP/1.1 200 OK\r\n" + DENY, b""),  # no blank line
    (b"HTTP/1.1 200 OK\r\n\r\n", b""),
    (http(DENY, headers=b"Transfer-Encoding: chunked\r\n"), b""),
    (http(DENY, headers=b"TRANSFER-ENCODING: CHUNKED\r\n"), b""),
    (http(DENY, headers=b"x-note: transfer-encoding: chunked\r\n"), b""),
    (http(DENY, headers=b"Transfer-Encoding:  chunked\r\n"), DENY),  # not the exact phrase
    (http(DENY, headers=b"x-a: " + b"a" * 200_000 + b"\r\n"), DENY),
    (http(DENY, headers=b"x-a: " + b"a" * 256_000 + b"\r\n"), b""),  # over 256,000 bytes in all
]


@pytest.mark.parametrize("response, out", RESPONSES, ids=range(len(RESPONSES)))
def test_only_a_200_unchunked_response_within_the_cap_counts(native, daemon, isolated_home, response, out):
    server = daemon(response)
    assert both(native, server, PRE, _env(isolated_home)) == out


def test_the_response_cap_is_256000_bytes_in_all(native, daemon, isolated_home):
    head = b"HTTP/1.1 200 OK\r\n\r\n"
    exact = b'{"a": "' + b"x" * (forward.MAX_RESPONSE_BYTES - len(head) - 9) + b'"}'
    assert len(head + exact) == forward.MAX_RESPONSE_BYTES
    assert both(native, daemon(head + exact), PRE, _env(isolated_home)) == exact
    over = exact[:-2] + b'x"}'
    assert both(native, daemon(head + over), PRE, _env(isolated_home)) == b""


# -- the input ---------------------------------------------------------------------------------


@pytest.mark.parametrize("payload", [b"", b" \t\r\n\x0b\x0c", b"\n"])
def test_an_empty_payload_sends_nothing(native, daemon, isolated_home, payload):
    server = daemon(http(DENY))
    assert both(native, server, payload, _env(isolated_home)) == b"" and not server.requests


def test_stdin_is_read_up_to_a_million_bytes(native, daemon, isolated_home):
    server = daemon(http(DENY))
    exact = b'{"x": "' + b"y" * (forward.MAX_STDIN_BYTES - 9) + b'"}'
    assert len(exact) == forward.MAX_STDIN_BYTES
    assert both(native, server, exact, _env(isolated_home)) == DENY
    assert len(server.requests) == 2 and server.requests[0].endswith(exact)
    assert both(native, server, exact + b" ", _env(isolated_home)) == b""
    assert len(server.requests) == 2  # too big: nothing sent


def test_the_payload_is_forwarded_as_bytes_even_when_it_is_not_json(native, daemon, isolated_home):
    server = daemon(http(DENY))
    payload = b"\xff\x00 not json \r\n\r\n"
    assert both(native, server, payload, _env(isolated_home)) == DENY
    assert server.requests[0].endswith(b"\r\n\r\n" + payload)


# -- switched off ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "setting",
    [
        {"TRUTHSTONE_DISABLE": "1"},
        {"TRUTHSTONE_DISABLE": "true"},
        {"TRUTHSTONE_DISABLE": " YES\n"},
        {"TRUTHSTONE_DISABLE": "On"},
        {"TRUTHSTONE_DISABLE": "\u00a0on\u3000"},  # str.strip() strips Unicode spaces too
        {"TRUTHSTONE_DISABLE": "\x1ctrue\x1f"},
        {"TRUTHSTONE_DISABLE": "", "AGENTGUARD_DISABLE": "1"},  # an empty setting is unset
        {"AGENTGUARD_DISABLE": "yes"},
    ],
)
def test_switched_off_means_nothing_is_sent(native, daemon, isolated_home, setting):
    server = daemon(http(DENY))
    assert both(native, server, PRE, _env(isolated_home, **setting)) == b"" and not server.requests


@pytest.mark.parametrize(
    "setting",
    [
        {"TRUTHSTONE_DISABLE": "0"},
        {"TRUTHSTONE_DISABLE": "no"},
        {"TRUTHSTONE_DISABLE": "1 1"},
        {"TRUTHSTONE_DISABLE": "off", "AGENTGUARD_DISABLE": "1"},
        {"TRUTHSTONE_DISABLE": "\u0131"},
    ],
)
def test_anything_else_is_not_switched_off(native, daemon, isolated_home, setting):
    server = daemon(http(DENY))
    assert both(native, server, PRE, _env(isolated_home, **setting)) == DENY and len(server.requests) == 2


# -- the handshake -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hs, works",
    [
        ({}, True),
        ({"host": "localhost"}, True),
        ({"host": None}, False),
        ({"host": 127}, False),
        ({"host": "127.0.0.1 "}, False),
        ({"host": "127.1"}, False),
        ({"host": "10.0.0.1"}, False),
        ({"host": "128.0.0.1"}, False),
        ({"host": "127.0.0.256"}, False),
        ({"host": "127.0.0.-1"}, False),
        ({"host": "::1"}, False),
        ({"host": "127.0.0.1\u0000"}, False),
        ({"host": "127.0.0.\u0661"}, False),  # a digit to str.isdigit(), not to the resolver
        ({"port": 0}, False),
        ({"port": 65536}, False),
        ({"port": -1}, False),
        ({"port": True}, False),
        ({"port": None}, False),
        ({"token": ""}, False),
        ({"token": "a b"}, False),
        ({"token": "a\rb"}, False),
        ({"token": "a\nb"}, False),
        ({"token": "é"}, False),
        ({"token": 12}, False),
        ({"token": "tab\there"}, True),  # Python checks CR, LF and space only
        ({"pid": 0}, False),
        ({"pid": -1}, False),
        ({"pid": 2**31}, False),
        ({"pid": 2**22 + 12345}, False),  # not running
        ({"pid": "1"}, False),
        ({"pid": True}, False),
        ({"pid": 1.5}, False),
    ],
)
def test_the_handshake_is_checked_as_forward_py_checks_it(native, daemon, isolated_home, hs, works):
    server = daemon(http(DENY), hs=hs)
    assert both(native, server, PRE, _env(isolated_home)) == (DENY if works else b"")
    assert len(server.requests) == (2 if works else 0)


def test_a_pid_this_user_cannot_signal_is_not_the_daemon(native, daemon, isolated_home):
    if os.getuid() == 0:
        pytest.skip("root may signal any process")
    server = daemon(http(DENY), hs={"pid": 1})
    assert both(native, server, PRE, _env(isolated_home)) == b"" and not server.requests


@pytest.mark.parametrize(
    "text, works",
    [
        ('{"port": 1, "port": PORT, "token": "t", "pid": PID}', True),  # the last duplicate counts
        ('{"port": PORT, "port": 1, "token": "t", "pid": PID}', False),
        ('{"port": PORT, "token": "t", "pid": PID, "x": [NaN, {"y": null}, -Infinity]}', True),
        ('{"host": "\\u006cocalhost", "port": PORT, "token": "t", "pid": PID}', True),
        ('{"port": PORT, "token": "t", "pid": PID}  \n', True),
        ('{"port": PORT, "token": "t", "pid": PID', False),
        ('\ufeff{"port": PORT, "token": "t", "pid": PID}', False),
        ('[{"port": PORT, "token": "t", "pid": PID}]', False),
        ("{}", False),
        ('{"port": PORT.0, "token": "t", "pid": PID}', False),
        ('{"port": PORTe0, "token": "t", "pid": PID}', False),
        ('{"port": PORT, "token": "t", "pid": PID, "bad": "\x01"}', False),
    ],
)
def test_the_handshake_is_json_as_python_reads_it(native, daemon, isolated_home, text, works):
    server = daemon(http(DENY))
    (isolated_home / "daemon.json").write_text(
        text.replace("PORT", str(server.port)).replace("PID", str(os.getpid()))
    )
    assert both(native, server, PRE, _env(isolated_home)) == (DENY if works else b"")
    assert len(server.requests) == (2 if works else 0)


def test_an_escaped_token_is_sent_decoded(native, daemon, isolated_home):
    server = daemon(http(DENY))
    hs = json.loads((isolated_home / "daemon.json").read_text())
    (isolated_home / "daemon.json").write_text(json.dumps(hs).replace('"tok-123"', '"t\\u006fk\\t\\u0000"'))
    assert both(native, server, PRE, _env(isolated_home)) == DENY
    assert b"\r\nAuthorization: Bearer tok\t\x00\r\n" in server.requests[0]


def test_a_handshake_over_64000_bytes_is_refused(native, daemon, isolated_home):
    server = daemon(http(DENY))
    hs = json.loads((isolated_home / "daemon.json").read_text())
    base = json.dumps({**hs, "pad": ""})
    for size, works in ((64_000, True), (64_001, False)):
        text = base.replace('"pad": ""', '"pad": "' + "p" * (size - len(base)) + '"')
        (isolated_home / "daemon.json").write_text(text)
        assert len(text) == size
        assert both(native, server, PRE, _env(isolated_home)) == (DENY if works else b"")


def test_a_symlinked_handshake_is_refused(native, daemon, isolated_home, tmp_path):
    server = daemon(http(DENY))
    real = tmp_path / "elsewhere.json"
    (isolated_home / "daemon.json").rename(real)
    (isolated_home / "daemon.json").symlink_to(real)
    assert both(native, server, PRE, _env(isolated_home)) == b"" and not server.requests


def test_without_a_handshake_or_a_daemon_it_fails_open(native, daemon, isolated_home):
    assert _native(native, PRE, _env(isolated_home)) == b""  # no daemon.json
    (isolated_home / "daemon.json").mkdir()
    assert _native(native, PRE, _env(isolated_home)) == b""  # not a file
    (isolated_home / "daemon.json").rmdir()
    server = daemon(http(DENY))
    server.close()  # nobody listens on that port any more
    assert both(native, server, PRE, _env(isolated_home)) == b""
    slammed = daemon(slam=True)
    assert both(native, slammed, PRE, _env(isolated_home)) == b""


# -- the home ----------------------------------------------------------------------------------


def _home_with_handshake(home: Path, server: _RawDaemon) -> None:
    home.mkdir(parents=True, exist_ok=True)
    hs = {"host": "127.0.0.1", "port": server.port, "token": "tok", "pid": os.getpid()}
    (home / "daemon.json").write_text(json.dumps(hs))


def test_the_default_home_and_a_former_names_home(native, daemon, isolated_home, tmp_path):
    server = daemon(http(DENY))
    user = tmp_path / "user"
    env = _env(isolated_home, HOME=str(user), TRUTHSTONE_HOME=None)
    _home_with_handshake(user / f".{names.FORMER[0][1]}", server)
    assert both(native, server, PRE, env) == DENY  # only the former name's directory exists
    (user / f".{names.SLUG}").mkdir()
    assert both(native, server, PRE, env) == b""  # the current one exists, without a handshake
    _home_with_handshake(user / f".{names.SLUG}", server)
    assert both(native, server, PRE, env) == DENY
    other = tmp_path / "other"
    _home_with_handshake(other, server)
    assert both(native, server, PRE, {**env, f"{names.FORMER[0][2]}_HOME": str(other)}) == DENY
    assert both(native, server, PRE, {**env, "TRUTHSTONE_HOME": "~/.truthstone"}) == DENY
    assert both(native, server, PRE, {**env, "TRUTHSTONE_HOME": "~"}) == b""
    assert both(native, server, PRE, {**env, "TRUTHSTONE_HOME": "~nobody-here-x/h"}) == b""
    assert both(native, server, PRE, {**env, "HOME": str(user) + "///"}) == DENY


def test_a_relative_home_is_the_working_directory_s(native, daemon, isolated_home, tmp_path):
    server = daemon(http(DENY))
    _home_with_handshake(tmp_path / "work" / "rel" / "home", server)
    env = _env(isolated_home, TRUTHSTONE_HOME="rel/./home/")
    assert both(native, server, PRE, env, cwd=tmp_path / "work") == DENY
    assert both(native, server, PRE, env, cwd=tmp_path) == b""


def test_the_home_is_followed_through_trusted_links_only(native, daemon, isolated_home, tmp_path):
    server = daemon(http(DENY))
    real = tmp_path / "real-home"
    _home_with_handshake(real, server)
    mine = tmp_path / "link"  # in an owner-only directory: trusted
    mine.symlink_to(real)
    assert both(native, server, PRE, _env(isolated_home, TRUTHSTONE_HOME=str(mine))) == DENY
    assert (
        both(native, server, PRE, _env(isolated_home, TRUTHSTONE_HOME=str(mine / ".." / "real-home"))) == DENY
    )
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "link").symlink_to(real)
    shared.chmod(0o777)  # anyone could swap the link: refused
    try:
        assert both(native, server, PRE, _env(isolated_home, TRUTHSTONE_HOME=str(shared / "link"))) == b""
        shared.chmod(0o1777)  # sticky, like /tmp: only the owner can replace it
        assert both(native, server, PRE, _env(isolated_home, TRUTHSTONE_HOME=str(shared / "link"))) == DENY
    finally:
        shared.chmod(0o700)
    via_parent = tmp_path / "via"
    via_parent.symlink_to(tmp_path)  # a link further up the path
    env = _env(isolated_home, TRUTHSTONE_HOME=str(via_parent / "real-home"))
    assert both(native, server, PRE, env) == DENY


# -- timeouts and the exit code ----------------------------------------------------------------


def test_a_daemon_that_never_answers_costs_the_timeout_and_nothing_else(native, daemon, isolated_home):
    server = daemon(hang=True)
    started = time.monotonic()
    assert _native(native, PRE, _env(isolated_home), "--timeout", "0.3") == b""
    assert time.monotonic() - started < 3
    assert len(server.requests) == 1


@pytest.mark.slow
def test_the_timeout_argument_is_read_as_forward_py_reads_it(native, daemon, isolated_home):
    server = daemon(hang=True)
    for args, low, high in (
        (("--timeout", "0.4", "--timeout", "30"), 0.3, 3.0),  # the first one counts
        (("--timeout",), 3.5, 9.0),  # no value: the default
        (("--timeout", " 4e-1 "), 0.3, 3.0),
        (("--timeout", "61"), 3.5, 9.0),  # out of range: the default, 4 s
        (("--timeout", "0x1p-2"), 3.5, 9.0),  # not a Python float: the default
    ):
        started = time.monotonic()
        assert _native(native, PRE, _env(isolated_home), *args) == b""
        assert low <= time.monotonic() - started <= high, args
    assert len(server.requests) == 5  # each waited on the daemon, which never answered
    assert forward._timeout(["--timeout"]) == forward.DEFAULT_TIMEOUT_S
    assert forward._timeout(["--timeout", "0x1p-2"]) == forward.DEFAULT_TIMEOUT_S
    assert forward._timeout(["--timeout", " 4e-1 "]) == 0.4


def test_a_closed_stdout_is_not_a_crash(native, daemon, isolated_home):
    daemon(http(DENY))
    proc = subprocess.Popen(
        [str(native), "--timeout", "4"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env(isolated_home),
    )
    proc.stdout.close()  # whoever ran the hook stopped listening
    _, err = proc.communicate(PRE, timeout=30)
    assert proc.returncode == 0 and err == b""


# -- deliberately stricter: fails open where forward.py would carry on --------------------------


def test_the_host_is_read_by_inet_pton_and_never_resolved(native, daemon, isolated_home):
    """Python's socket reads an address with inet_pton first, as this does. macOS's reads
    "127.0.0.01" as 127.0.0.1, and the two agree; glibc's refuses a leading zero, and where Python
    would go on to getaddrinfo (octal, or a name lookup), this refuses."""
    host = "127.0.0.01"
    try:
        readable = socket.inet_pton(socket.AF_INET, host) == socket.inet_pton(socket.AF_INET, "127.0.0.1")
    except OSError:
        readable = False
    server = daemon(http(DENY), hs={"host": host})
    if readable:
        assert both(native, server, PRE, _env(isolated_home)) == DENY
        assert f"Host: {host}:".encode() in server.requests[0]
    else:
        assert _native(native, PRE, _env(isolated_home)) == b"" and not server.requests


def test_a_fifo_named_daemon_json_is_not_waited_on(native, daemon, isolated_home):
    daemon(http(DENY))
    (isolated_home / "daemon.json").unlink()
    os.mkfifo(isolated_home / "daemon.json")
    started = time.monotonic()
    assert _native(native, PRE, _env(isolated_home)) == b""
    assert time.monotonic() - started < 5


# -- the source ----------------------------------------------------------------------------------


def _code() -> str:
    """The C source without its comments and string literals' contents."""
    text = re.sub(r"/\*.*?\*/", "", SOURCE.read_text(), flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def test_the_names_are_the_registry_s():
    text = SOURCE.read_text()
    prefixes = re.search(r"PREFIXES\[\] = \{(.*?)\};", text, re.S).group(1)
    homes = re.search(r"HOMES\[\] = \{(.*?)\};", text, re.S).group(1)
    assert re.findall(r'"([^"]+)"', prefixes) == [names.UPPER, *(former[2] for former in names.FORMER)]
    assert re.findall(r'"([^"]+)"', homes) == [f"~/.{names.SLUG}", *(f"~/.{f[1]}" for f in names.FORMER)]


def test_the_limits_are_forward_py_s():
    defines = dict(re.findall(r"#define (\w+) ([\d.]+)", SOURCE.read_text()))
    assert int(defines["MAX_STDIN"]) == forward.MAX_STDIN_BYTES
    assert int(defines["MAX_RESPONSE"]) == forward.MAX_RESPONSE_BYTES
    assert int(defines["MAX_HANDSHAKE"]) == 64_000
    assert float(defines["DEFAULT_TIMEOUT"]) == forward.DEFAULT_TIMEOUT_S
    assert forward.HOOK_PATH == "/hook/codex" and '"POST /hook/codex HTTP/1.1' in SOURCE.read_text()


def test_no_heap_no_shell_no_exec_and_no_path_from_the_environment_but_the_home_s():
    code = _code()
    for banned in ("malloc", "calloc", "realloc", "strdup", "system(", "popen", "exec", "fork", "dlopen"):
        assert banned not in code, banned
    assert re.findall(r"getenv\(([^)]*)\)", code) == ["name", '"HOME"']  # name: <PREFIX>_HOME or _DISABLE
    assert sorted(set(re.findall(r'setting\("(\w+)"\)', code))) == ["DISABLE", "HOME"]


@needs_cc
def test_it_compiles_cleanly_with_all_warnings(tmp_path):
    proc = subprocess.run(
        [CC, "-O2", "-Wall", "-Wextra", "-o", str(tmp_path / "fn"), str(SOURCE)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0 and proc.stderr == "", proc.stderr


def test_the_stand_in_records_the_request_forward_py_writes(daemon, isolated_home):
    server = daemon(http(DENY))
    assert _python(PRE, _env(isolated_home)) == DENY
    (request,) = server.requests
    assert request.startswith(b"POST /hook/codex HTTP/1.1\r\nHost: 127.0.0.1:") and request.endswith(PRE)


# -- the build: at SessionStart, in the background, once per version ----------------------------


def _install(data: Path, monkeypatch) -> subprocess.Popen | None:
    """SessionStart's install, returning the background build it started (if any)."""
    started: list[subprocess.Popen | None] = []
    real = builder.start
    monkeypatch.setattr(builder, "start", lambda lean, python=None: started.append(real(lean, python)))
    assert hook.install_lean(str(data))
    (build,) = started
    return build


def _finish(build: subprocess.Popen | None) -> None:
    assert build is not None, "no build was started"
    assert build.wait(timeout=180) == 0


def _private(path: Path) -> Path:
    path.mkdir(parents=True)
    path.chmod(0o700)
    return path


@needs_cc
def test_session_start_builds_it_in_the_background_once_per_version(
    tmp_path, monkeypatch, daemon, isolated_home
):
    data = tmp_path / "data"
    lean = data / hook.LEAN_DIR
    _finish(_install(data, monkeypatch))
    binary = lean / builder.BINARY
    assert binary.is_file() and not binary.is_symlink() and os.access(binary, os.X_OK)
    assert (lean.stat().st_mode & 0o777) == 0o700
    assert (lean / builder.STAMP).read_text().strip() == builder.stamp(SOURCE.read_bytes())
    assert not (lean / builder.LOCK).exists() and not list(lean.glob(".forward-native*"))
    assert builder.start(str(lean)) is None  # current: compiled once per version
    daemon(http(DENY))
    assert _native(binary, PRE, _env(isolated_home)) == DENY  # the very forwarder tested above


def test_without_a_compiler_there_is_no_binary(tmp_path, monkeypatch):
    empty = tmp_path / "bin-without-cc"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    data = tmp_path / "data"
    lean = data / hook.LEAN_DIR
    _finish(_install(data, monkeypatch))
    assert not (lean / builder.BINARY).exists() and not (lean / builder.STAMP).exists()
    assert not (lean / builder.LOCK).exists() and not list(lean.glob(".forward-native*"))
    assert (lean / "run.py").is_file() and (lean / "forward.py").is_file()  # the Python path stays


@needs_cc
def test_a_stale_binary_is_removed_at_once_then_rebuilt(tmp_path):
    lean = _private(tmp_path / "lean")
    (lean / builder.BINARY).write_text("#!/bin/sh\necho stale\n")
    (lean / builder.BINARY).chmod(0o700)
    (lean / builder.STAMP).write_text("an older version\n")
    build = builder.start(str(lean))
    assert not (lean / builder.BINARY).exists()  # the Python forwarder answers until the new one lands
    _finish(build)
    assert b"stale" not in (lean / builder.BINARY).read_bytes()
    assert (lean / builder.STAMP).read_text().strip() == builder.stamp(SOURCE.read_bytes())


@needs_cc
def test_one_build_at_a_time(tmp_path):
    lean = _private(tmp_path / "lean")
    (lean / builder.LOCK).write_text("12345")
    assert builder.start(str(lean)) is None and not (lean / builder.BINARY).exists()
    old = time.time() - builder.LOCK_STALE_S - 10  # a builder that died long ago
    os.utime(lean / builder.LOCK, (old, old))
    _finish(builder.start(str(lean)))
    assert (lean / builder.BINARY).is_file() and not (lean / builder.LOCK).exists()


def test_a_symlinked_lean_directory_is_refused(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    (data / hook.LEAN_DIR).symlink_to(elsewhere)
    assert not hook.install_lean(str(data))
    assert builder.start(str(data / hook.LEAN_DIR)) is None
    assert list(elsewhere.iterdir()) == []


def test_a_lean_directory_others_could_use_is_made_private(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "start", lambda lean, python=None: None)
    lean = tmp_path / "data" / hook.LEAN_DIR
    lean.mkdir(parents=True)
    lean.chmod(0o755)
    assert hook.install_lean(str(tmp_path / "data"))
    assert (lean.stat().st_mode & 0o777) == 0o700


def _fake_cc(bin_dir: Path, body: str) -> None:
    """A stand-in compiler: ``body`` runs with $out set to the -o argument."""
    bin_dir.mkdir()
    script = 'out=""\nwhile [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done\n' + body
    (bin_dir / "cc").write_text("#!/bin/sh\n" + script)
    (bin_dir / "cc").chmod(0o755)


@pytest.mark.parametrize(
    "body",
    [
        "exit 1\n",  # does not compile
        "exit 0\n",  # says it did, made nothing
        'printf "#!/bin/sh\\nexit 3\\n" > "$out"\n',  # a binary that does not exit 0
        'printf "#!/bin/sh\\necho hello\\n" > "$out"\n',  # one that prints without input
        'mkdir "$out"\n',  # not a file
    ],
)
def test_a_failed_build_leaves_nothing_behind(tmp_path, monkeypatch, body):
    _fake_cc(tmp_path / "bin", body)
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    lean = _private(tmp_path / "lean")
    _finish(builder.start(str(lean)))
    assert list(lean.iterdir()) == []


def test_the_compiler_is_never_the_repository_s_and_gets_a_clean_environment(tmp_path, monkeypatch):
    _fake_cc(tmp_path / "repo", "exit 0\n")
    monkeypatch.chdir(tmp_path / "repo")
    monkeypatch.setenv("PATH", os.pathsep.join([".", "", "relative/bin"]))
    assert builder.compiler() is None  # ./cc is the repository's, never the compiler
    monkeypatch.setenv("PATH", os.pathsep.join([".", "/usr/bin", "/bin"]))
    for name in ("CPATH", "C_INCLUDE_PATH", "CFLAGS", "LIBRARY_PATH", "CC"):
        monkeypatch.setenv(name, str(tmp_path / "repo"))
    env = builder.compiler_env()
    assert env["PATH"] == os.pathsep.join(["/usr/bin", "/bin"])
    assert set(env) <= {"PATH", "LC_ALL", "HOME", "TMPDIR", "DEVELOPER_DIR", "SDKROOT"}


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS's /usr/bin/cc stands in for the developer tools")
def test_on_macos_the_cc_shim_is_used_only_with_the_developer_tools(tmp_path, monkeypatch):
    """Without them, /usr/bin/cc offers to install them in a dialog: never run it then."""
    if not os.path.exists("/usr/bin/cc"):
        pytest.skip("no /usr/bin/cc")
    calls: list[list[str]] = []

    def xcode_select(status: int, out: bytes):
        def run(argv, **kwargs):
            calls.append(list(argv))
            return subprocess.CompletedProcess(argv, status, out, b"")

        return run

    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(builder.subprocess, "run", xcode_select(2, b""))
    assert builder.compiler() is None and calls == [["/usr/bin/xcode-select", "-p"]]
    monkeypatch.setattr(builder.subprocess, "run", xcode_select(0, str(tmp_path / "gone").encode()))
    assert builder.compiler() is None
    monkeypatch.setattr(builder.subprocess, "run", xcode_select(0, str(tmp_path).encode() + b"\n"))
    assert builder.compiler() == "/usr/bin/cc"


def test_the_builder_runs_isolated_and_says_nothing(tmp_path):
    """``python -I -S native.py <lean>``: no package import, exit 0 even when told nonsense."""
    for argv in ([], ["relative/lean"], [str(tmp_path / "missing")], ["a", "b"]):
        proc = subprocess.run(
            [sys.executable, "-I", "-S", builder.__file__, *argv],
            capture_output=True,
            timeout=60,
            cwd=tmp_path,
        )
        assert (proc.returncode, proc.stdout, proc.stderr) == (0, b"", b"")
    assert "import truthstone" not in Path(builder.__file__).read_text()

