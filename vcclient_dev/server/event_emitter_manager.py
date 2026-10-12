from __future__ import annotations

from vcclient_dev.server.event_emitter import EventEmitter


class EventEmitterManager:
    _instance: "EventEmitterManager | None" = None

    event_emitter: "EventEmitter | None" = None

    def get_instance(cls):

        if cls._instance is None:
            cls._instance = cls()

            return cls._instance

        return cls._instance

    get_instance = classmethod(get_instance)

    def set_event_emitter(self=None, event_emitter=None):

        self.event_emitter = event_emitter

    def get_event_emitter(self=None):

        return self.event_emitter
