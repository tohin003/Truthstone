"""Invoice lifecycle events: a small synchronous publish/subscribe bus.

A module subscribes a handler to an event name; ``emit`` calls every handler subscribed to
that name, in the order they subscribed, with the event's payload as keyword arguments. An
event nobody subscribed to is delivered to nobody. The events, their payloads and their
subscribers are listed in the README ("Invoice lifecycle and events").
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

Handler = Callable[..., None]

_SUBSCRIBERS: dict[str, list[Handler]] = defaultdict(list)


def subscribe(event: str, handler: Handler) -> Handler:
    """Call ``handler(**payload)`` for every ``event`` from now on. Returns the handler."""
    _SUBSCRIBERS[event].append(handler)
    return handler


def unsubscribe(event: str, handler: Handler) -> None:
    """Stop calling ``handler`` for ``event``. Unknown handlers are ignored."""
    if handler in _SUBSCRIBERS.get(event, []):
        _SUBSCRIBERS[event].remove(handler)


def on(event: str) -> Callable[[Handler], Handler]:
    """Decorator form of ``subscribe``."""

    def register(handler: Handler) -> Handler:
        return subscribe(event, handler)

    return register


def emit(event: str, **payload: Any) -> None:
    """Deliver ``event`` to its subscribers, in subscription order."""
    for handler in list(_SUBSCRIBERS.get(event, [])):
        handler(**payload)


def subscribers(event: str) -> list[Handler]:
    """The handlers subscribed to ``event``, in order."""
    return list(_SUBSCRIBERS.get(event, []))
