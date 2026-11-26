from __future__ import annotations

from queue import Empty, Queue
from threading import RLock
from typing import TYPE_CHECKING, Any

import numpy as np

from vcclient.app_status import is_app_stopping, wait_for_stop
from vcclient.logger import logger

from ...exception import (
    ERROR_CODE_AUDIO_INPUT_DEVICE_NOT_SELECTED,
    ERROR_CODE_AUDIO_OUTPUT_DEVICE_NOT_SELECTED,
    VCClientError,
)
from ..audio_device_manager import (
    get_audio_input_device,
    get_audio_output_device,
    get_default_sample_rate,
)
from ..configuration_manager.configuration_manager import ConfigurationManager
from ..event_emitter import EventEmitter
from ..sounddevice_loader import sounddevice as sd
from ..voice_changer_const import REALTIME_OUTPUT_STATUS_SEND_INTERVAL_SEC
from .voice_changer import VoiceChanger

if TYPE_CHECKING:
    import sounddevice as sd_types

local_voice_changer_callback_chunk_sec = 0.01
local_voice_changer_loop_interval_sec = 0.2
local_voice_changer_min_preroll_sec = 0.02
local_voice_changer_preroll_chunk_ratio = 0.1


class LocalVoiceChangerInterface(EventEmitter):
    _instance: LocalVoiceChangerInterface | None = None
    stop_flag: bool
    local_voice_changer_enabled: bool
    out_queue: Queue[np.ndarray]
    monitor_queue: Queue[np.ndarray]
    waveform_rest_output: np.ndarray
    waveform_rest_monitor: np.ndarray
    split_length: int
    output_preroll_needed: bool
    monitor_preroll_needed: bool
    audio_input_device_sample_rate: float
    audio_output_device_sample_rate: float
    audio_monitor_device_sample_rate: float
    input_block_size: int
    output_block_size: int
    monitor_block_size: int
    input_extra_settings: sd_types.WasapiSettings | None
    output_extra_settings: sd_types.WasapiSettings | None
    monitor_extra_settings: sd_types.WasapiSettings | None

    @classmethod
    def get_instance(cls) -> LocalVoiceChangerInterface:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        super().__init__()
        self.stop_flag = True
        self.local_voice_changer_enabled = False
        self.lifecycle_lock = RLock()
        self.stream_running = False
        self.out_queue = Queue()
        self.monitor_queue = Queue()
        self.waveform_rest_output = np.array([], dtype=np.float32)
        self.waveform_rest_monitor = np.array([], dtype=np.float32)
        self.split_length = 0
        self.output_preroll_needed = True
        self.monitor_preroll_needed = True
        self.input_volume: float = 0.0
        self.input_volume_calculation_buffer: list[np.ndarray] = []
        self.output_volume: float = 0.0
        self.output_volume_calculation_buffer: list[np.ndarray] = []
        self.process_call_counter: int = 0

    def _get_preroll_block_count(self) -> int:
        """Compute target preroll block count from the active inference chunk duration."""
        raw_chunk_sec = getattr(getattr(self, "vc", None), "vc_chunk_sec", None)
        if isinstance(raw_chunk_sec, (int, float)) and raw_chunk_sec > 0:
            chunk_sec = float(raw_chunk_sec)
            self.vc_chunk_sec = chunk_sec
        else:
            fallback_chunk_sec = getattr(self, "vc_chunk_sec", 0.0)
            chunk_sec = float(fallback_chunk_sec) if isinstance(fallback_chunk_sec, (int, float)) else 0.0
        preroll_sec = max(
            local_voice_changer_min_preroll_sec,
            chunk_sec * local_voice_changer_preroll_chunk_ratio,
        )
        return max(2, int(round(preroll_sec / local_voice_changer_callback_chunk_sec)))

    def _enqueue_preroll(self, queue: Queue[np.ndarray], block_size: int, dtype: np.dtype[Any]) -> None:
        """Pad the front of an output queue up to the target preroll block count with silence."""
        missing_blocks = max(0, self._get_preroll_block_count() - queue.qsize())
        for _ in range(missing_blocks):
            queue.put(np.zeros(block_size, dtype=dtype))

    def _enqueue_stream_blocks(
        self,
        waveform: np.ndarray,
        rest_attr: str,
        block_size: int,
        queue: Queue[np.ndarray],
        preroll_attr: str,
    ) -> None:
        """Split a converted chunk into callback blocks and replenish preroll after silence."""
        rest: np.ndarray = getattr(self, rest_attr)
        if rest.dtype != waveform.dtype:
            rest = np.array([], dtype=waveform.dtype)
        combined = np.concatenate([rest, waveform])
        splitted_waveforms = [combined[i : i + block_size] for i in range(0, len(combined), block_size)]
        self.split_length = len(splitted_waveforms)
        if splitted_waveforms and len(splitted_waveforms[-1]) < block_size:
            setattr(self, rest_attr, splitted_waveforms.pop())
        else:
            setattr(self, rest_attr, np.array([], dtype=waveform.dtype))
        if splitted_waveforms:
            if getattr(self, preroll_attr) and any(np.any(block) for block in splitted_waveforms):
                self._enqueue_preroll(queue, block_size, waveform.dtype)
            setattr(self, preroll_attr, not bool(np.any(splitted_waveforms[-1])))
            for block in splitted_waveforms:
                queue.put(block)
        elif not np.any(waveform):
            setattr(self, preroll_attr, True)

    def calc_vol(self, data: np.ndarray, prev_vol: float) -> float:
        if len(data) == 0:
            return prev_vol
        sum_val = float(np.sum(data * data))
        rms = float(np.sqrt(sum_val / len(data)))
        return max(rms, prev_vol * 0.5)

    def calculate_and_send_realtime_output_status(self) -> None:
        if len(self.input_volume_calculation_buffer) == 0 or len(self.output_volume_calculation_buffer) == 0:
            return

        input_combined_data = np.concatenate(self.input_volume_calculation_buffer)
        output_combined_data = np.concatenate(self.output_volume_calculation_buffer)

        self.input_volume = self.calc_vol(input_combined_data, self.input_volume)
        self.output_volume = self.calc_vol(output_combined_data, self.output_volume)

        realtime_output_status_data = {
            "realtimeOutputStatusSendIntervalSec": REALTIME_OUTPUT_STATUS_SEND_INTERVAL_SEC,
            "outputBufferSize": self.out_queue.qsize() * getattr(self, "output_block_size", 0),
            "inputRms": float(self.input_volume),
            "outputRms": float(self.output_volume),
        }
        self.emit("status", "realtime_output_status", realtime_output_status_data)

        self.input_volume_calculation_buffer = []
        self.output_volume_calculation_buffer = []

    def _get_active_config(self) -> tuple[Any, bool]:
        vc = getattr(self, "vc", None) or VoiceChanger.peek_instance()
        snap = getattr(vc, "_active_snapshot", None) if vc is not None else None
        if snap is not None:
            return (snap, True)
        return (ConfigurationManager.get_instance().get_voice_changer_configuration(), False)

    def start(self) -> None:
        with self.lifecycle_lock:
            cfg, is_session = self._get_active_config()
            if not is_session:
                if cfg.audio_input_device_index == -1:
                    raise VCClientError(ERROR_CODE_AUDIO_INPUT_DEVICE_NOT_SELECTED)
                if cfg.audio_output_device_index == -1:
                    raise VCClientError(ERROR_CODE_AUDIO_OUTPUT_DEVICE_NOT_SELECTED)
            self.local_voice_changer_enabled = True

    def stop(self) -> None:
        with self.lifecycle_lock:
            self.local_voice_changer_enabled = False
            vc = getattr(self, "vc", None) or VoiceChanger.peek_instance()
            if vc is not None and getattr(vc, "_active_snapshot", None) is not None:
                self.vc = vc
            else:
                self.vc = VoiceChanger.get_instance()
            self.vc.stop_convert_chunk_bulk()

    def run(self) -> None:
        with self.lifecycle_lock:
            if not self.local_voice_changer_enabled:
                return
            self.stream_running = True
            try:
                self.setup()
            except BaseException:
                self.stream_running = False
                raise
        try:
            self.launch_converter()
        finally:
            with self.lifecycle_lock:
                self.stream_running = False

    def setup(self) -> None:
        cfg, is_session = self._get_active_config()
        if cfg.audio_input_device_index == -1:
            raise VCClientError(ERROR_CODE_AUDIO_INPUT_DEVICE_NOT_SELECTED)
        if cfg.audio_output_device_index == -1:
            raise VCClientError(ERROR_CODE_AUDIO_OUTPUT_DEVICE_NOT_SELECTED)
        if is_session:
            vc = getattr(self, "vc", None) or VoiceChanger.peek_instance()
            if vc is None:
                vc = VoiceChanger.get_or_create_raw()
            self.vc = vc
        else:
            self.vc = VoiceChanger.get_instance()
        self.vc.start_convert_chunk_bulk()
        self.vc_info = self.vc.get_voice_changer_information()
        self.vc_chunk_sec = self.vc_info.chunk_sec
        self.output_preroll_needed = True
        self.monitor_preroll_needed = True

        if cfg.audio_input_device_sample_rate == -1:
            if is_session and self.vc_info.input_sample_rate > 0:
                self.audio_input_device_sample_rate = self.vc_info.input_sample_rate
            else:
                self.audio_input_device_sample_rate = get_default_sample_rate(
                    cfg.audio_input_device_index, "audioinput"
                )
        else:
            self.audio_input_device_sample_rate = cfg.audio_input_device_sample_rate

        if cfg.audio_output_device_sample_rate == -1:
            if is_session and self.vc_info.output_sample_rate > 0:
                self.audio_output_device_sample_rate = self.vc_info.output_sample_rate
            else:
                self.audio_output_device_sample_rate = get_default_sample_rate(
                    cfg.audio_output_device_index, "audiooutput"
                )
        else:
            self.audio_output_device_sample_rate = cfg.audio_output_device_sample_rate

        if cfg.audio_monitor_device_index != -1 and cfg.audio_monitor_device_sample_rate == -1:
            if is_session and self.vc_info.monitor_sample_rate > 0:
                self.audio_monitor_device_sample_rate = self.vc_info.monitor_sample_rate
            else:
                self.audio_monitor_device_sample_rate = get_default_sample_rate(
                    cfg.audio_monitor_device_index, "audiooutput"
                )
        else:
            self.audio_monitor_device_sample_rate = cfg.audio_monitor_device_sample_rate

        logger.info("audio input device:%s, sr:%s", cfg.audio_input_device_index, self.audio_input_device_sample_rate)
        logger.info(
            "audio output device:%s, sr:%s", cfg.audio_output_device_index, self.audio_output_device_sample_rate
        )
        logger.info(
            "audio monitor device:%s, sr:%s", cfg.audio_monitor_device_index, self.audio_monitor_device_sample_rate
        )

        if not is_session:
            conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
            conf.input_sample_rate = round(self.audio_input_device_sample_rate)
            conf.output_sample_rate = round(self.audio_output_device_sample_rate)
            conf.monitor_sample_rate = round(self.audio_monitor_device_sample_rate)
        self.input_block_size = int(round(local_voice_changer_callback_chunk_sec * self.audio_input_device_sample_rate))
        self.output_block_size = int(
            round(local_voice_changer_callback_chunk_sec * self.audio_output_device_sample_rate)
        )
        self.monitor_block_size = int(
            round(local_voice_changer_callback_chunk_sec * self.audio_monitor_device_sample_rate)
        )
        logger.info("block size:%s, %s, %s", self.input_block_size, self.output_block_size, self.monitor_block_size)

        exclusive_mode = cfg.wasapi_exclusive_enabled
        logger.info("wasapi_exclusive_enabled:%s", exclusive_mode)

        input_audio_device = get_audio_input_device(cfg.audio_input_device_index)
        if input_audio_device is not None and "WASAPI" in input_audio_device.host_api and exclusive_mode is True:
            self.input_extra_settings = sd.WasapiSettings(exclusive=True)
        else:
            self.input_extra_settings = None

        output_audio_device = get_audio_output_device(cfg.audio_output_device_index)
        if output_audio_device is not None and "WASAPI" in output_audio_device.host_api and exclusive_mode is True:
            self.output_extra_settings = sd.WasapiSettings(exclusive=True)
        else:
            self.output_extra_settings = None

        monitor_audio_device = get_audio_output_device(cfg.audio_monitor_device_index)
        if monitor_audio_device is not None and "WASAPI" in monitor_audio_device.host_api and exclusive_mode is True:
            self.monitor_extra_settings = sd.WasapiSettings(exclusive=True)
        else:
            self.monitor_extra_settings = None

        if monitor_audio_device is not None:
            self.vc.set_monitor_enable(True)
        else:
            self.vc.set_monitor_enable(False)

    def launch_converter(self) -> None:
        cfg, _ = self._get_active_config()
        stop_check_counter = 0
        if self.audio_input_device_sample_rate < 0:
            return None
        with sd.InputStream(
            device=cfg.audio_input_device_index,
            callback=self.audio_input_callback,
            samplerate=self.audio_input_device_sample_rate,
            blocksize=self.input_block_size,
            extra_settings=self.input_extra_settings,
        ) as input_stream:
            with sd.OutputStream(
                device=cfg.audio_output_device_index,
                callback=self.audio_output_callback,
                samplerate=self.audio_output_device_sample_rate,
                blocksize=self.output_block_size,
                extra_settings=self.output_extra_settings,
            ) as output_stream:
                if cfg.audio_monitor_device_index != -1:
                    with sd.OutputStream(
                        device=cfg.audio_monitor_device_index,
                        callback=self.audio_monitor_callback,
                        samplerate=self.audio_monitor_device_sample_rate,
                        blocksize=self.monitor_block_size,
                        extra_settings=self.monitor_extra_settings,
                    ) as monitor_stream:
                        from ..session_manager.session_manager import notify_audio_started

                        notify_audio_started()
                        logger.info(
                            "Start Local Voice Changer(2way), sr:[%s, %s, %s], ch:[%s, %s, %s], depth:[%s, %s, %s]",
                            input_stream.samplerate,
                            output_stream.samplerate,
                            monitor_stream.samplerate,
                            input_stream.channels,
                            output_stream.channels,
                            monitor_stream.channels,
                            input_stream.dtype,
                            output_stream.dtype,
                            monitor_stream.dtype,
                        )
                        while not is_app_stopping():
                            wait_for_stop(local_voice_changer_loop_interval_sec)
                            stop_check_counter += 1
                            if self.local_voice_changer_enabled is False:
                                break
                            if stop_check_counter % 100 == 0:
                                logger.debug(
                                    "Start Local Voice Changer(2way) counter:%s, sr:[%s, %s, %s], ch:[%s, %s, %s], depth:[%s, %s, %s]",
                                    stop_check_counter,
                                    input_stream.samplerate,
                                    output_stream.samplerate,
                                    monitor_stream.samplerate,
                                    input_stream.channels,
                                    output_stream.channels,
                                    monitor_stream.channels,
                                    input_stream.dtype,
                                    output_stream.dtype,
                                    monitor_stream.dtype,
                                )
                else:
                    from ..session_manager.session_manager import notify_audio_started

                    notify_audio_started()
                    logger.info(
                        "Start Local Voice Changer(1way), sr:[%s, %s], ch:[%s, %s], depth:[%s, %s]",
                        input_stream.samplerate,
                        output_stream.samplerate,
                        input_stream.channels,
                        output_stream.channels,
                        input_stream.dtype,
                        output_stream.dtype,
                    )
                    while not is_app_stopping():
                        wait_for_stop(local_voice_changer_loop_interval_sec)
                        stop_check_counter += 1
                        if self.local_voice_changer_enabled is False:
                            break
                        if stop_check_counter % 100 == 0:
                            logger.info(
                                "Start Local Voice Changer(1way) counter:%s, sr:[%s, %s], ch:[%s, %s], depth:[%s, %s]",
                                stop_check_counter,
                                input_stream.samplerate,
                                output_stream.samplerate,
                                input_stream.channels,
                                output_stream.channels,
                                input_stream.dtype,
                                output_stream.dtype,
                            )
        logger.info("Local Voice Changer main thread stopped")

    def audio_input_callback(self, indata: np.ndarray, frames: int, times: Any, status: sd_types.CallbackFlags) -> None:
        cfg, is_session = self._get_active_config()
        gain = cfg.input_gain if is_session else cfg.audio_input_device_gain
        try:
            indata = indata[:, 0].copy()
            indata = indata * gain
            if cfg.realtime_output_status_enabled:
                self.input_volume_calculation_buffer.append(indata)
            converted, converted_for_monitor = self.vc.convert_chunk_bulk(indata)

            if converted is not None:
                self._enqueue_stream_blocks(
                    converted, "waveform_rest_output", self.output_block_size, self.out_queue, "output_preroll_needed"
                )

            if converted_for_monitor is not None:
                self._enqueue_stream_blocks(
                    converted_for_monitor,
                    "waveform_rest_monitor",
                    self.monitor_block_size,
                    self.monitor_queue,
                    "monitor_preroll_needed",
                )
        except Exception as e:
            logger.error("audio input callback ex: %s", e, exc_info=True)

    def audio_output_callback(
        self, outdata: np.ndarray, frames: int, times: Any, status: sd_types.CallbackFlags
    ) -> None:
        cfg, is_session = self._get_active_config()
        gain = cfg.output_gain if is_session else cfg.audio_output_device_gain
        try:
            buffer_for_trancate = max(self.split_length, 3)

            if self.out_queue.qsize() > self.split_length + buffer_for_trancate:
                drop_count = self.out_queue.qsize()
                logger.info("audio_output_callback trancate queue: %s", drop_count)
                out_wav = None
                for _ in range(drop_count):
                    try:
                        out_wav = self.out_queue.get_nowait()
                    except Empty:
                        break
                if out_wav is None:
                    outdata.fill(0)
                    return
            else:
                out_wav = self.out_queue.get_nowait()

            out_wav = out_wav.reshape(-1, 1)
            out_wav = np.repeat(out_wav, outdata.shape[1]).reshape(-1, outdata.shape[1])
            out_wav = out_wav * gain
            if out_wav.shape[0] == outdata.shape[0]:
                outdata[:, :] = out_wav[:, :]
            else:
                min_len = min(out_wav.shape[0], outdata.shape[0])
                outdata[:min_len, :] = out_wav[:min_len, :]
                if min_len < outdata.shape[0]:
                    outdata[min_len:, :].fill(0)
        except Empty:
            outdata.fill(0)
        except Exception as e:
            outdata.fill(0)
            logger.error("audio output callback ex: %s", e, exc_info=True)
        finally:
            if cfg.realtime_output_status_enabled and outdata.shape[0] > 0 and outdata.shape[1] > 0:
                self.output_volume_calculation_buffer.append(outdata[:, 0].copy())
                self.process_call_counter += 1
                if self.process_call_counter >= (
                    REALTIME_OUTPUT_STATUS_SEND_INTERVAL_SEC / local_voice_changer_callback_chunk_sec
                ):
                    self.calculate_and_send_realtime_output_status()
                    self.process_call_counter = 0

    def audio_monitor_callback(
        self, outdata: np.ndarray, frames: int, times: Any, status: sd_types.CallbackFlags
    ) -> None:
        cfg, is_session = self._get_active_config()
        gain = cfg.output_gain if is_session else cfg.audio_output_device_gain
        try:
            buffer_for_trancate = max(self.split_length, 3)

            if self.monitor_queue.qsize() > self.split_length + buffer_for_trancate:
                drop_count = self.monitor_queue.qsize()
                out_wav = None
                for _ in range(drop_count):
                    try:
                        out_wav = self.monitor_queue.get_nowait()
                    except Empty:
                        break
                if out_wav is None:
                    outdata.fill(0)
                    return
            else:
                out_wav = self.monitor_queue.get_nowait()

            out_wav = out_wav.reshape(-1, 1)
            out_wav = np.repeat(out_wav, outdata.shape[1]).reshape(-1, outdata.shape[1])
            out_wav = out_wav * gain
            if out_wav.shape[0] == outdata.shape[0]:
                outdata[:, :] = out_wav[:, :]
            else:
                min_len = min(out_wav.shape[0], outdata.shape[0])
                outdata[:min_len, :] = out_wav[:min_len, :]
                if min_len < outdata.shape[0]:
                    outdata[min_len:, :].fill(0)
        except Empty:
            outdata.fill(0)
        except Exception as e:
            outdata.fill(0)
            logger.error("audio monitor callback ex: %s", e, exc_info=True)
