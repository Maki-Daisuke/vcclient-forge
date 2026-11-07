from __future__ import annotations

from typing import Any, Protocol


class EventEmitterProtocol(Protocol):
    def emit_coroutine(self, event: str, data: Any, to: str | None = None) -> None: ...


_emitter: EventEmitterProtocol | None = None


def set_event_emitter(emitter: EventEmitterProtocol | None) -> None:
    global _emitter
    _emitter = emitter


def emit_event(event: str, data: Any, to: str | None = None) -> None:
    if _emitter is not None:
        _emitter.emit_coroutine(event, data, to=to)
