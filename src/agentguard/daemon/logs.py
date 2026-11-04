"""What the daemon may write to its log, and how large the log may grow (R17).

Hook payloads carry whatever the agent handled: file contents, commands with bearer
tokens, ``.env`` lines. ``daemon.log`` is a plain file that outlives the session, so no
payload value may reach it, whichever module logs:

* an exception is logged as its **type** and a redacted message. A pydantic
  ``ValidationError`` prints ``input_value=…`` — the payload itself — so for those only
  the field and the error type are kept, never the input;
* a traceback keeps its frames (file, line, our own source) and replaces each
  exception's line with that description;
* everything written passes :func:`~agentguard.core.store.redact_secrets` last.

:class:`SafeFormatter` does all three for every record the daemon process logs, through
the one handler :func:`install` puts on the root logger. Code that logs a failure itself
uses :func:`describe_exception` / :func:`safe_traceback`, so its message is safe under
any formatter.

``daemon.log`` is the daemon's stdout and stderr (the shim and the CLI open it for the
child), so the daemon rotates it in place: past
:data:`~agentguard.daemon.lifecycle.DAEMON_LOG_MAX_BYTES` it is renamed to
``daemon.log.1`` and a fresh file is put under the same descriptors. The spawners rotate
an oversized log before starting a daemon too, so it is bounded across restarts as well.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agentguard.core.config import DEFAULT_LOG_HANDLER, Settings, configure_logging
from agentguard.core.store import redact_secrets
from agentguard.daemon.lifecycle import (
    DAEMON_LOG_BACKUPS,
    DAEMON_LOG_MAX_BYTES,
    open_private_append,
    rotate_log,
)

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MAX_MESSAGE_CHARS = 300
MAX_CHAIN = 5
MAX_ERRORS = 5
_LOC_PART_CHARS = 40


def describe_exception(exc: BaseException) -> str:
    """``Type: message`` with no payload value in it. Never raises."""
    name = type(exc).__name__
    try:
        if isinstance(exc, ValidationError):
            return f"{name}: {_validation_summary(exc)}"
        message = " ".join(str(exc).split())
    except Exception:  # noqa: BLE001 - an exception whose str() fails is still described
        return name
    if not message:
        return name
    return f"{name}: {redact_secrets(message[: MAX_MESSAGE_CHARS * 2])[:MAX_MESSAGE_CHARS]}"


def _validation_summary(exc: ValidationError) -> str:
    """Where validation failed and why, by error type — never the input that failed."""
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    places = []
    for error in errors[:MAX_ERRORS]:
        loc = ".".join(str(part)[:_LOC_PART_CHARS] for part in error.get("loc", ())) or "(root)"
        places.append(f"{loc}: {error.get('type', 'invalid')}")
    more = f"; and {len(errors) - MAX_ERRORS} more" if len(errors) > MAX_ERRORS else ""
    count = exc.error_count()
    noun = "validation error" if count == 1 else "validation errors"
    return redact_secrets(f"{count} {noun} for {exc.title} ({'; '.join(places)}{more})")


def safe_traceback(exc: BaseException) -> str:
    """The traceback, frames only, with each exception's line replaced by its description.

    Frames are file names, line numbers and our own source lines; the exception lines are
    where payload values appear, so those are the lines that are rewritten.
    """
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(chain) < MAX_CHAIN:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    parts: list[str] = []
    for position, item in enumerate(reversed(chain)):
        if position:
            parts.append("\nDuring handling of the above, another exception occurred:\n\n")
        parts.append("Traceback (most recent call last):\n")
        try:
            parts.extend(traceback.format_tb(item.__traceback__))
        except Exception:  # noqa: BLE001 - a frame that cannot be shown is left out
            parts.append("  (frames unavailable)\n")
        parts.append(describe_exception(item) + "\n")
    return "".join(parts).rstrip("\n")


class SafeFormatter(logging.Formatter):
    """A formatter that can be handed any record: no payload value, no secret, survives."""

    def __init__(self, fmt: str = FORMAT) -> None:
        super().__init__(fmt)

    def format(self, record: logging.LogRecord) -> str:
        record.message = _safe_message(record)
        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)
        text = self.formatMessage(record)
        # Never `record.exc_text`: another handler may already have cached an unsafe one.
        exc = record.exc_info[1] if record.exc_info else None
        if exc is not None:
            text = f"{text}\n{safe_traceback(exc)}"
        if record.stack_info:
            text = f"{text}\n{self.formatStack(record.stack_info)}"
        return redact_secrets(text)


def _safe_message(record: logging.LogRecord) -> str:
    """``record.getMessage()``, with any exception among the message or its arguments
    replaced by its description (``log.warning("failed: %s", exc)`` would print it)."""
    msg = record.msg
    if isinstance(msg, BaseException):
        msg = describe_exception(msg)
    args = record.args
    try:
        if not args:
            return str(msg)
        if isinstance(args, tuple):
            args = tuple(describe_exception(a) if isinstance(a, BaseException) else a for a in args)
        elif isinstance(args, dict):
            args = {k: describe_exception(v) if isinstance(v, BaseException) else v for k, v in args.items()}
        return str(msg) % args
    except Exception:  # noqa: BLE001 - a malformed record still logs its template
        return str(msg)


class DaemonLogHandler(logging.StreamHandler):
    """Writes safe records to the daemon's stderr, and rotates it when it is daemon.log.

    Rotation only happens while the descriptor really is ``log_path`` (same device and
    inode): a daemon run by hand in a terminal, or by a test with a pipe, is never
    touched.
    """

    def __init__(
        self,
        log_path: Path | None,
        stream: Any = None,
        fd: int = 2,
        also: tuple[int, ...] = (1,),
        max_bytes: int = DAEMON_LOG_MAX_BYTES,
        backups: int = DAEMON_LOG_BACKUPS,
    ) -> None:
        super().__init__(stream if stream is not None else sys.stderr)
        self.setFormatter(SafeFormatter())
        self._path = Path(log_path) if log_path is not None else None
        self._fd = fd
        self._also = also
        self._max_bytes = max_bytes
        self._backups = backups
        self._rotating = threading.Lock()

    @property
    def rotates(self) -> bool:
        return self._path is not None

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        if self._path is not None:
            self._maybe_rotate()

    def _maybe_rotate(self) -> None:
        if not self._rotating.acquire(blocking=False):
            return
        try:
            info = os.fstat(self._fd)
            if info.st_size < self._max_bytes or self._path is None:
                return
            try:
                current = os.lstat(self._path)
            except FileNotFoundError:
                return  # renamed under us; whoever did it owns the file now
            if not os.path.samestat(info, current):
                self._path = None  # this descriptor is not daemon.log: never rotate it
                return
            # Write anything buffered to the old file before the descriptor moves.
            self.flush()
            rotate_log(self._path, max_bytes=self._max_bytes, backups=self._backups)
            fresh = open_private_append(self._path)
            try:
                for fd in (self._fd, *self._also):
                    try:
                        same = os.path.samestat(os.fstat(fd), info)
                    except OSError:
                        same = False
                    if same:
                        os.dup2(fresh.fileno(), fd)
            finally:
                fresh.close()
        except OSError:
            # Rotation is impossible here (permissions, a full disk, a vanished home):
            # keep writing where we are rather than lose the log line by line.
            self._path = None
        finally:
            self._rotating.release()


def install(settings: Settings, log_path: Path | None = None) -> DaemonLogHandler:
    """Route every log record of this process through :class:`DaemonLogHandler`.

    The handler goes on the root logger, so AgentGuard's loggers, uvicorn's (run with
    ``log_config=None``) and any library's all pass the same formatter. Then
    ``log_level`` is applied (``configure_logging``, which adds nothing once the root
    logger has a handler).
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, DaemonLogHandler):
            root.removeHandler(handler)
    agentguard = logging.getLogger("agentguard")
    for handler in list(agentguard.handlers):
        # The plain handler `configure_logging` adds when nothing else is configured.
        if handler.get_name() == DEFAULT_LOG_HANDLER:
            agentguard.removeHandler(handler)
    handler = DaemonLogHandler(log_path)
    root.addHandler(handler)
    configure_logging(settings)
    return handler
