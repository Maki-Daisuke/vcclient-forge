from __future__ import annotations

import concurrent.futures
import queue
import threading
from collections.abc import Callable
from typing import Any

import numpy as np

from vcclient.logger import logger

from ...exception import ERROR_CODE_LOCAL_AUDIO_DEVICE_QUERY_FAILED, VCClientError
from ..data_types.data_types import AudioDevice
from ..sounddevice_loader import sounddevice as sd
from ..voice_changer_const import AudioDeviceType

_worker_init_lock = threading.Lock()
_worker_queue: queue.Queue[tuple[Callable[[], Any], concurrent.futures.Future[Any]]] = queue.Queue()
_worker_thread: threading.Thread | None = None


def _audio_device_worker_loop() -> None:
    while True:
        task, future = _worker_queue.get()
        try:
            future.set_result(task())
        except BaseException as exc:
            future.set_exception(exc)


def _ensure_worker_thread() -> threading.Thread:
    global _worker_thread
    with _worker_init_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(
                target=_audio_device_worker_loop,
                daemon=True,
                name="audio-device-worker",
            )
            _worker_thread.start()
        return _worker_thread


def _run_on_audio_device_thread[T](task: Callable[[], T]) -> T:
    """Run all PortAudio device enumeration and probing sequentially on one dedicated thread."""
    worker = _ensure_worker_thread()
    if threading.current_thread() is worker:
        return task()
    future: concurrent.futures.Future[T] = concurrent.futures.Future()
    _worker_queue.put((task, future))
    return future.result()


def _list_device() -> tuple[list[AudioDevice], list[AudioDevice]]:
    def _do_list() -> tuple[list[AudioDevice], list[AudioDevice]]:
        try:
            sd._terminate()
            sd._initialize()
            audio_device_list = sd.query_devices()
        except Exception as e:
            raise VCClientError(ERROR_CODE_LOCAL_AUDIO_DEVICE_QUERY_FAILED, detail=str(e))

        input_audio_device_list = [d for d in audio_device_list if d["max_input_channels"] > 0]
        output_audio_device_list = [d for d in audio_device_list if d["max_output_channels"] > 0]
        hostapis = sd.query_hostapis()
        audio_input_devices: list[AudioDevice] = []
        audio_output_devices: list[AudioDevice] = []

        for d in input_audio_device_list:
            input_audio_device = AudioDevice(
                kind="audioinput",
                index=d["index"],
                name=d["name"],
                host_api=hostapis[d["hostapi"]]["name"],
                max_input_channels=d["max_input_channels"],
                max_output_channels=d["max_output_channels"],
                default_samplerate=d["default_samplerate"],
            )
            audio_input_devices.append(input_audio_device)

        for d in output_audio_device_list:
            output_audio_device = AudioDevice(
                kind="audiooutput",
                index=d["index"],
                name=d["name"],
                host_api=hostapis[d["hostapi"]]["name"],
                max_input_channels=d["max_input_channels"],
                max_output_channels=d["max_output_channels"],
                default_samplerate=d["default_samplerate"],
            )
            audio_output_devices.append(output_audio_device)

        return (audio_input_devices, audio_output_devices)

    return _run_on_audio_device_thread(_do_list)


def _probe_stream_sample_rate(
    device_id: int,
    device_type: AudioDeviceType,
    *,
    samplerate: int | None = None,
) -> float:
    def _probe() -> float:
        def dummy_callback(data: np.ndarray, frames: Any, times: Any, status: Any) -> None:
            pass

        stream_cls: Any = sd.InputStream if device_type == "audioinput" else sd.OutputStream
        kwargs: dict[str, Any] = {
            "device": device_id,
            "callback": dummy_callback,
            "dtype": "float32",
        }
        if samplerate is not None:
            kwargs["samplerate"] = samplerate
        with stream_cls(**kwargs) as stream:
            return float(stream.samplerate)

    return _run_on_audio_device_thread(_probe)


def _check_sample_rate(device_id: int, desired_sampling_rate: int, type: AudioDeviceType) -> bool:
    try:
        _probe_stream_sample_rate(device_id, type, samplerate=desired_sampling_rate)
        return True
    except Exception as e:
        logger.error("Failed to check_sampling_rate: %s", e)
        return False


def _get_default_sample_rate(device_id: int, type: AudioDeviceType) -> float:
    try:
        return _probe_stream_sample_rate(device_id, type)
    except Exception as e:
        direction = "input" if type == "audioinput" else "output"
        logger.error("Failed to get default sampling rate(%s): %s", direction, e)
        return -1


_audio_input_devices: list[AudioDevice] = []
_audio_output_devices: list[AudioDevice] = []
_audio_devices_initialized: bool = False
# A failed query is cached too, so PortAudio is retried only by an explicit reload.
_audio_devices_error: VCClientError | None = None


def reload_audio_devices() -> tuple[list[AudioDevice], list[AudioDevice]]:
    def _reload() -> tuple[list[AudioDevice], list[AudioDevice]]:
        global _audio_input_devices, _audio_output_devices, _audio_devices_initialized, _audio_devices_error
        logger.info("Reloading Audio Device info")
        _audio_devices_initialized = True
        try:
            (_audio_input_devices, _audio_output_devices) = _list_device()
        except VCClientError as e:
            _audio_input_devices, _audio_output_devices = [], []
            _audio_devices_error = e
            raise
        _audio_devices_error = None
        logger.info("Audio(input): %s", _audio_input_devices)
        logger.info("Audio(output): %s", _audio_output_devices)
        return (_audio_input_devices, _audio_output_devices)

    return _run_on_audio_device_thread(_reload)


def _get_cached_devices(*, raise_error: bool) -> tuple[list[AudioDevice], list[AudioDevice]]:
    def _get() -> tuple[list[AudioDevice], list[AudioDevice]]:
        if not _audio_devices_initialized:
            try:
                reload_audio_devices()
            except VCClientError:
                pass
        if raise_error and _audio_devices_error is not None:
            raise VCClientError(_audio_devices_error.info.code, detail=_audio_devices_error.info.detail)
        return (_audio_input_devices, _audio_output_devices)

    return _run_on_audio_device_thread(_get)


def get_audio_input_devices() -> list[AudioDevice]:
    return _get_cached_devices(raise_error=True)[0]


def get_audio_input_device(index: int) -> AudioDevice | None:
    for d in _get_cached_devices(raise_error=False)[0]:
        if d.index == index:
            return d
    return None


def get_audio_output_devices() -> list[AudioDevice]:
    return _get_cached_devices(raise_error=True)[1]


def get_audio_output_device(index: int) -> AudioDevice | None:
    for d in _get_cached_devices(raise_error=False)[1]:
        if d.index == index:
            return d
    return None


def check_available_sample_rate(device_id: int, desired_sampling_rate: int, type: AudioDeviceType) -> bool:
    return _check_sample_rate(device_id, desired_sampling_rate, type)


def get_default_sample_rate(device_id: int, type: AudioDeviceType) -> float:
    return _get_default_sample_rate(device_id, type)
