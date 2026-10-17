from __future__ import annotations

from vcclient.server.event_emitter import EventEmitter


class EventEmitterManager:
    _instance: EventEmitterManager | None = None
    event_emitter: EventEmitter | None = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_event_emitter(self, event_emitter=None):
        self.event_emitter = event_emitter

    def get_event_emitter(self):
        return self.event_emitter
