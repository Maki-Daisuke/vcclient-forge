from __future__ import annotations

from typing import Any


def _load_sounddevice() -> Any:
    import sounddevice

    return sounddevice


class LazySoundDevice:
    def InputStream(self, *args: Any, **kwargs: Any) -> Any:
        return _load_sounddevice().InputStream(*args, **kwargs)

    def OutputStream(self, *args: Any, **kwargs: Any) -> Any:
        return _load_sounddevice().OutputStream(*args, **kwargs)

    def WasapiSettings(self, *args: Any, **kwargs: Any) -> Any:
        return _load_sounddevice().WasapiSettings(*args, **kwargs)

    def query_devices(self, *args: Any, **kwargs: Any) -> Any:
        return _load_sounddevice().query_devices(*args, **kwargs)

    def query_hostapis(self, *args: Any, **kwargs: Any) -> Any:
        return _load_sounddevice().query_hostapis(*args, **kwargs)

    def _initialize(self) -> Any:
        return _load_sounddevice()._initialize()

    def _terminate(self) -> Any:
        return _load_sounddevice()._terminate()


sounddevice = LazySoundDevice()


def is_port_audio_error(exc: BaseException) -> bool:
    # Checked by name so that handling an error never triggers the import (and Pa_Initialize) itself.
    return type(exc).__module__ == "sounddevice" and type(exc).__name__ == "PortAudioError"
