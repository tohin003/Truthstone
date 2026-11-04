"""Host adapters by name (H4). The daemon routes ``POST /hook/<name>`` through this module,
so adding a host never means editing the daemon.

Two ways in:

* **built in** — listed in :data:`BUILTIN` by dotted module path and imported on first
  use, so a daemon that only ever serves one host never imports the others;
* **explicit registration** — ``register("cursor", "my_pkg.cursor.translate")`` with a
  dotted path (imported lazily), or with the module or object itself.

An adapter provides ``to_event(payload)``, ``from_decision(event, decision, hook_name)``
and, optionally, ``handle_payload(guard, payload)`` (``docs/ADAPTER-CONTRACT.md``, (d)).
The registry wraps it in a :class:`RegisteredAdapter`, which satisfies
``core.hosts.Adapter``.

Failing open: an adapter that cannot be imported, or does not provide the protocol, is
logged once and treated as absent, so its route answers ``{}``; :func:`load_errors` keeps
the reason, so ``/health`` can say so rather than leave the silence unexplained.

This module is imported by the daemon only. Hook processes (``shim.py``, ``forward.py``,
``codex/hook.py``) never import it, so it costs them nothing.
"""

from __future__ import annotations

import importlib
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentguard.core.events import AgentEvent
    from agentguard.core.models import Decision

log = logging.getLogger(__name__)

# The hosts that ship with AgentGuard: route name -> the adapter's translation module.
BUILTIN: dict[str, str] = {
    "claude-code": "agentguard.adapters.claude_code.translate",
    "codex": "agentguard.adapters.codex.translate",
}

# A route segment: lowercase, digits and dashes.
_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
# Where both built-in hosts put the native hook name. An adapter whose host spells it
# differently defines ``hook_name(payload)``.
_HOOK_NAME_FIELD = "hook_event_name"
_MAX_ERROR_CHARS = 300

_lock = threading.Lock()
_targets: dict[str, str | object] = dict(BUILTIN)
_loaded: dict[str, RegisteredAdapter] = {}
_errors: dict[str, str] = {}


@dataclass(frozen=True)
class RegisteredAdapter:
    """One adapter, as the daemon sees it: a name and an implementation (a module, usually)."""

    name: str
    impl: Any

    def to_event(self, payload: dict[str, Any]) -> AgentEvent | None:
        return self.impl.to_event(payload)

    def from_decision(self, event: AgentEvent, decision: Decision, hook_name: str) -> dict[str, Any]:
        return self.impl.from_decision(event, decision, hook_name)

    @property
    def handle_payload(self) -> Callable[[Any, dict[str, Any]], dict[str, Any]] | None:
        handler = getattr(self.impl, "handle_payload", None)
        return handler if callable(handler) else None

    def hook_name(self, payload: dict[str, Any]) -> str:
        """The host's own name for the hook this payload came from."""
        custom = getattr(self.impl, "hook_name", None)
        value = custom(payload) if callable(custom) else payload.get(_HOOK_NAME_FIELD)
        return value if isinstance(value, str) else ""


def register(name: str, target: str | object, *, replace: bool = False) -> None:
    """Serve an adapter at ``/hook/<name>``. ``target`` is a dotted module path (imported
    on first use) or the module/object itself. Re-registering a name needs ``replace``."""
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError(f"adapter names are lowercase route segments, not {name!r}")
    if isinstance(target, str) and not target.strip():
        raise ValueError("an adapter target cannot be empty")
    with _lock:
        if name in _targets and not replace:
            raise ValueError(f"an adapter is already registered as {name!r}")
        _targets[name] = target
        _loaded.pop(name, None)
        _errors.pop(name, None)


def unregister(name: str) -> None:
    with _lock:
        _targets.pop(name, None)
        _loaded.pop(name, None)
        _errors.pop(name, None)


def reset() -> None:
    """Back to the built-in adapters only (tests)."""
    with _lock:
        _targets.clear()
        _targets.update(BUILTIN)
        _loaded.clear()
        _errors.clear()


def names() -> list[str]:
    """Every registered route, without importing anything."""
    with _lock:
        return sorted(_targets)


def get(name: str) -> RegisteredAdapter | None:
    """The adapter registered as ``name``, imported on first use; ``None`` if there is none
    or it cannot be loaded (logged once; see :func:`load_errors`)."""
    if not isinstance(name, str):
        return None
    with _lock:
        loaded = _loaded.get(name)
        if loaded is not None:
            return loaded
        target = _targets.get(name)
        if target is None or name in _errors:
            return None
    # Imported outside the lock: an adapter's first import may take a while, and the
    # import system has its own lock.
    try:
        impl = importlib.import_module(target) if isinstance(target, str) else target
        missing = [attr for attr in ("to_event", "from_decision") if not callable(getattr(impl, attr, None))]
        if missing:
            raise TypeError(f"not an adapter: no {' or '.join(missing)}")
    except Exception as exc:  # one broken adapter must not take down the daemon
        log.exception("agentguard: adapter %r could not be loaded; its hooks answer nothing", name)
        with _lock:
            if _targets.get(name) is target:
                _errors[name] = f"{type(exc).__name__}: {exc}"[:_MAX_ERROR_CHARS]
        return None
    adapter = RegisteredAdapter(name, impl)
    with _lock:
        if _targets.get(name) is not target:
            return adapter  # replaced meanwhile: serve this request, cache nothing
        return _loaded.setdefault(name, adapter)


def available() -> list[str]:
    """The registered routes whose adapter loads (imports each one on first call)."""
    return [name for name in names() if get(name) is not None]


def load_errors() -> dict[str, str]:
    """Adapters that failed to load: name -> the reason."""
    with _lock:
        return dict(_errors)
