from abc import ABC, abstractmethod


class EventEmitter(ABC):
    def emit_coroutine(self, event, data, to=(None,)):

        pass

    emit_coroutine = abstractmethod(emit_coroutine)
