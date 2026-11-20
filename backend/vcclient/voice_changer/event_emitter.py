from __future__ import annotations

from typing import Any, Callable


class EventEmitter:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[..., Any]]] = {}

    def on(self, event: str, callback: Callable[..., Any]) -> None:
        """Register a callback for the given event."""
        listeners = self._listeners.setdefault(event, [])
        if callback not in listeners:
            listeners.append(callback)

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Emit an event to all registered callbacks."""
        for callback in list(self._listeners.get(event, [])):
            callback(*args, **kwargs)
