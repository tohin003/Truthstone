"""Why the daemon is guarding less than it seems (R9): fail open, but never silently.

Failing open is right: a broken guard must not stop the developer. But each of these
makes AgentGuard *answer less* while every hook still looks healthy:

* a hook whose bearer token is stale gets "no opinion" on every call;
* an observe-only daemon says nothing to any session;
* a broken store forgets what it saw;
* an adapter that cannot load answers nothing for its host.

``/health`` lists the reasons under ``degraded`` (a stable message each) and
``degraded_detail`` (with a stable ``code``, plus counts where they help). The command
hooks tell the developer once per session per code.

Other modules report their own reasons here: :func:`report` with a stable ``code`` and a
message for people, :func:`clear` when it is over. A message must not embed a counter or
a timestamp: hooks that key their notices on the text would repeat the notice every time
it changed. Put numbers in ``detail``.

Stdlib only, and safe from any thread.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

MAX_REASONS = 32
MAX_MESSAGE_CHARS = 300


@dataclass(frozen=True)
class Reason:
    code: str
    message: str
    since: float | None = None
    expires: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {**self.detail, "code": self.code, "message": self.message}
        if self.since is not None:
            out["since"] = round(self.since, 3)
        return out


class DegradedRegistry:
    """Reasons reported by any module, each until it is cleared or expires."""

    def __init__(self, max_reasons: int = MAX_REASONS) -> None:
        self._lock = threading.Lock()
        self._reasons: dict[str, Reason] = {}
        self._max = max_reasons

    def report(
        self,
        code: str,
        message: str,
        *,
        ttl_s: float | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Record (or refresh) a reason. ``ttl_s`` makes it lapse on its own."""
        code = str(code).strip()
        message = " ".join(str(message).split())[:MAX_MESSAGE_CHARS]
        if not code or not message:
            return
        now = time.time()
        with self._lock:
            previous = self._reasons.get(code)
            since = previous.since if previous and previous.message == message else now
            if previous is None and len(self._reasons) >= self._max:
                return  # a flood of distinct codes is a bug elsewhere; keep what we have
            self._reasons[code] = Reason(
                code=code,
                message=message,
                since=since,
                expires=now + ttl_s if ttl_s is not None else None,
                detail=dict(detail or {}),
            )

    def clear(self, code: str) -> None:
        with self._lock:
            self._reasons.pop(str(code).strip(), None)

    def reasons(self) -> list[Reason]:
        """The live reasons, oldest first."""
        now = time.time()
        with self._lock:
            for code in [c for c, r in self._reasons.items() if r.expires is not None and r.expires <= now]:
                del self._reasons[code]
            return sorted(self._reasons.values(), key=lambda reason: reason.since or 0.0)

    def reset(self) -> None:
        with self._lock:
            self._reasons.clear()


class RecentEvents:
    """How many times something happened in the last ``window_s`` seconds."""

    def __init__(self, window_s: float, max_kept: int = 10_000) -> None:
        self.window_s = window_s
        self._lock = threading.Lock()
        self._times: deque[float] = deque(maxlen=max_kept)

    def note(self, now: float | None = None) -> int:
        """Record one occurrence; returns how many are now inside the window."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self._times.append(now)
            return self._count(now)

    def count(self, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        with self._lock:
            return self._count(now)

    def seconds_since_last(self, now: float | None = None) -> float | None:
        now = time.monotonic() if now is None else now
        with self._lock:
            return round(now - self._times[-1], 1) if self._times else None

    def _count(self, now: float) -> int:
        cutoff = now - self.window_s
        while self._times and self._times[0] <= cutoff:
            self._times.popleft()
        return len(self._times)


# The process-wide registry other modules report to.
REGISTRY = DegradedRegistry()


def report(
    code: str, message: str, *, ttl_s: float | None = None, detail: dict[str, Any] | None = None
) -> None:
    REGISTRY.report(code, message, ttl_s=ttl_s, detail=detail)


def clear(code: str) -> None:
    REGISTRY.clear(code)


def reasons() -> list[Reason]:
    return REGISTRY.reasons()
