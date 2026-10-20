from __future__ import annotations

import logging
import threading

import numpy as np
import sounddevice as sd

from ...const import LOGGER_NAME
from ...exception import ERROR_CODE_LOCAL_AUDIO_DEVICE_QUERY_FAILED, VCClientError
from ..data_types.data_types import AudioDevice
from ..voice_chanager_const import AudioDeviceType

lock = threading.Lock()


def _list_device() -> tuple[list[AudioDevice], list[AudioDevice]]:
    with lock:
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


def _check_sample_rate(device_id: int, desired_sampling_rate: int, type: AudioDeviceType) -> bool:
    def dummy_callback(data: np.ndarray, frames, times, status):
        pass

    if type == "audioinput":
        try:
            with sd.InputStream(
                device=device_id, callback=dummy_callback, dtype="float32", samplerate=desired_sampling_rate
            ):
                pass
            return True
        except Exception as e:
            logging.getLogger(LOGGER_NAME).error(f"Failed to check_sampling_rate: {e}")
            return False
    else:
        try:
            with sd.OutputStream(
                device=device_id, callback=dummy_callback, dtype="float32", samplerate=desired_sampling_rate
            ):
                pass
            return True
        except Exception as e:
            logging.getLogger(LOGGER_NAME).error(f"Failed to check_sampling_rate: {e}")
            return False


def _get_default_sample_rate(device_id: int, type: AudioDeviceType) -> float:
    def dummy_callback(data: np.ndarray, frames, times, status):
        pass

    if type == "audioinput":
        try:
            with sd.InputStream(device=device_id, callback=dummy_callback, dtype="float32") as stream:
                sample_rate = stream.samplerate
                return sample_rate
        except Exception as e:
            logging.getLogger(LOGGER_NAME).error(f"Failed to get default sampling rate(input): {e}")
            return -1
    else:
        try:
            with sd.OutputStream(device=device_id, callback=dummy_callback, dtype="float32") as stream:
                sample_rate = stream.samplerate
                return sample_rate
        except Exception as e:
            logging.getLogger(LOGGER_NAME).error(f"Failed to get default sampling rate(output): {e}")
            return -1


class AudioDeviceManager:
    _instance: AudioDeviceManager | None = None
    audio_input_devices: list[AudioDevice]
    audio_output_devices: list[AudioDevice]

    @classmethod
    def get_instance(cls) -> AudioDeviceManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.reload_device()

    def reload_device(self) -> None:
        logging.getLogger(LOGGER_NAME).info("Reloading Audio Device info")
        (self.audio_input_devices, self.audio_output_devices) = _list_device()
        logging.getLogger(LOGGER_NAME).info(f"Audio(input):{self.audio_input_devices}")
        logging.getLogger(LOGGER_NAME).info(f"Audio(output):{self.audio_output_devices}")

    def get_audio_input_devices(self) -> list[AudioDevice]:
        return self.audio_input_devices

    def get_audio_input_device(self, index: int) -> AudioDevice | None:
        for d in self.audio_input_devices:
            if d.index == index:
                return d
        return None

    def get_audio_output_devices(self) -> list[AudioDevice]:
        return self.audio_output_devices

    def get_audio_output_device(self, index: int) -> AudioDevice | None:
        for d in self.audio_output_devices:
            if d.index == index:
                return d
        return None

    def check_available_sample_rate(self, device_id: int, desired_sampling_rate: int, type: AudioDeviceType) -> bool:
        return _check_sample_rate(device_id, desired_sampling_rate, type)

    def get_default_sample_rate(self, device_id: int, type: AudioDeviceType) -> float:
        return _get_default_sample_rate(device_id, type)
