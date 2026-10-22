import threading
import time
from collections.abc import Callable
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import numpy as np
import samplerate as sr
from scipy import signal
from scipy.io import wavfile

try:
    from simple_performance_timer.Timer import Timer
except ImportError:

    class Timer:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> Timer:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def record(self, *args: Any) -> None:
            pass


from vcclient.logger import logger

from ...const import SERVER_IO_RECORDING_FILE_IN, SERVER_IO_RECORDING_FILE_OUT
from ...exception import (
    ERROR_CODE_MODEL_UPDATE_FAILED,
    ERROR_CODE_PIPELINE_IS_NOT_INITIALIZED,
    ERROR_CODE_RECORDING_FAILED,
    VCClientError,
)
from ..configuration_manager.configuration_manager import ConfigurationManager
from ..data_types.data_types import PerformanceData
from ..data_types.slot_manager_data_types import RVCSlotInfo
from ..data_types.voice_changer_data_types import VoiceChangerInformation
from ..slot_manager.slot_manager import SlotManager
from ..voice_chanager_const import GET_GPU_DEVICE_ID_IS_NOT_AVAILABLE, PitchEstimatorType
from .crossfade_processor import CrossfadeProcessor
from .vc_pipelines.pipeline_manager import PipelineManager
from .vc_pipelines.vc_pipeline import VCPipeline

PerformanceListener = Callable[[PerformanceData], None]


class VoiceChanger:
    _instance: VoiceChanger | None = None

    vc_info: VoiceChangerInformation
    crossfade_processor: CrossfadeProcessor
    bulk_process: threading.Thread | None
    vc_pipeline: VCPipeline | None
    performance_listener: PerformanceListener | None
    input_record: list[np.ndarray]
    output_record: list[np.ndarray]
    monitor_record: list[np.ndarray]
    resampler_in: sr.Resampler
    resampler_out: sr.Resampler
    resampler_monitor: sr.Resampler
    # Set lazily once device rates, filters, or chunking are known; callers probe them with hasattr().
    input_sample_rate: int
    output_sample_rate: int
    monitor_sample_rate: int
    vc_chunk_sec: float
    chunk_size: int
    bh: np.ndarray
    ah: np.ndarray
    bl: np.ndarray
    al: np.ndarray
    bb: np.ndarray
    ab: np.ndarray

    @classmethod
    def get_instance(cls) -> VoiceChanger:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.initialize()
        self.performance_listener = None
        self.currentCrossFadeOffsetRate = 0
        self.currentCrossFadeEndRate = 0
        self.currentCrossFadeOverlapSize = 0
        self.crossfadeSize = 0

    def set_performance_listener(self, performance_listener: PerformanceListener | None = None) -> None:
        self.performance_listener = performance_listener

    def remove_performance_listener(self) -> None:
        self.performance_listener = None

    def initialize(self) -> None:
        self.vc_info = VoiceChangerInformation()
        self.crossfade_processor = CrossfadeProcessor()
        self.bulk_process = None
        self.vc_pipeline = None
        self.input_record = []
        self.output_record = []
        self.monitor_record = []
        self.resampler_in = sr.Resampler("sinc_best", channels=1)
        self.resampler_out = sr.Resampler("sinc_best", channels=1)
        self.resampler_monitor = sr.Resampler("sinc_best", channels=1)

    def _require_pipeline(self) -> VCPipeline:
        if self.vc_pipeline is None:
            raise VCClientError(ERROR_CODE_PIPELINE_IS_NOT_INITIALIZED, "Voice changer pipeline is not initialized.")
        return self.vc_pipeline

    def _update_model(self, slot_index: int) -> None:
        try:
            slot_info = SlotManager.get_instance().get_slot_info(slot_index)
            pipeline = PipelineManager.get_pipeline(slot_info)
            self.vc_pipeline = pipeline
            self.vc_info.voice_changer_type = slot_info.voice_changer_type
            self.vc_info.vc_input_sample_rate = pipeline.get_input_sample_rate()
            self.vc_info.vc_output_sample_rate = pipeline.get_output_sample_rate()
            self.vc_info.pitch_estimator_type = pipeline.get_pitch_estimator_type()
            self.vc_info.gpu_device_index = pipeline.get_gpu_device_id()
            logger.info(
                "slot_index Changed: %s, gpu_device_index: %s",
                self.vc_info.slot_index,
                self.vc_info.gpu_device_index,
            )
        except Exception as e:
            logger.warning("Failed to update model: %s", e)
            raise VCClientError(ERROR_CODE_MODEL_UPDATE_FAILED, f"Failed to update model:{e}")

    def _check_reload_model_is_required_and_update(self) -> None:
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        slot_index = conf.current_slot_index
        if self.vc_info.slot_index != slot_index or (
            self.vc_info.gpu_device_index != conf.gpu_device_id_int
            and self.vc_info.gpu_device_index != GET_GPU_DEVICE_ID_IS_NOT_AVAILABLE
        ):
            logger.info(
                "slot_index: %s -> %s, gpu_device_index: %s -> %s",
                self.vc_info.slot_index,
                slot_index,
                self.vc_info.gpu_device_index,
                conf.gpu_device_id_int,
            )
            prev_slot_index = self.vc_info.slot_index
            prev_gpu_index = self.vc_info.gpu_device_index
            try:
                self._update_model(slot_index)
                self.vc_info.slot_index = slot_index
                self.vc_info.gpu_device_index = conf.gpu_device_id_int
                self._set_io_sample_rate()
            except Exception as e:
                logger.error("Failed to switch model to slot %s: %s", slot_index, e)
                self.vc_info.slot_index = prev_slot_index
                self.vc_info.gpu_device_index = prev_gpu_index
                conf.current_slot_index = prev_slot_index
                ConfigurationManager.get_instance().set_voice_changer_configuration(conf)
            return None
        return None

    def _set_pitch_estimator(self, pitch_estimator: PitchEstimatorType) -> None:
        self._require_pipeline().set_pitch_estimator_type(pitch_estimator)

    def _check_and_update_pitch_estimator(self) -> None:
        slot_info = SlotManager.get_instance().get_slot_info(self.vc_info.slot_index)
        if not isinstance(slot_info, RVCSlotInfo):
            return None

        if self.vc_info.pitch_estimator_type != slot_info.pitch_estimator:
            self.vc_info.pitch_estimator_type = slot_info.pitch_estimator
            self._set_pitch_estimator(slot_info.pitch_estimator)
            return None

    def _set_io_sample_rate(self) -> None:
        if self.vc_info.input_sample_rate == -1 or self.vc_info.output_sample_rate == -1:
            logger.warning("Input or output sample rate is not set")
            return None

        if self.vc_info.slot_index == -1:
            logger.warning("Slot index is not set")
            return None

        self.input_sample_rate = self.vc_info.input_sample_rate
        self.output_sample_rate = self.vc_info.output_sample_rate
        self.monitor_sample_rate = self.vc_info.monitor_sample_rate
        self.vc_info.resample_ratio_in = self.vc_info.vc_input_sample_rate / self.input_sample_rate
        self.vc_info.resample_ratio_out = self.output_sample_rate / self.vc_info.vc_output_sample_rate
        self.vc_info.resample_ratio_monitor = self.monitor_sample_rate / self.vc_info.vc_output_sample_rate

        self.vc_info.resample_ratio_pass_through_in_out = self.output_sample_rate / self.input_sample_rate

        self.vc_info.resample_ratio_pass_through_in_monitor = self.monitor_sample_rate / self.input_sample_rate

        logger.info(
            "resample_ratio_in:%s, resample_ratio_out:%s, resample_ratio_monitor:%s",
            self.vc_info.resample_ratio_in,
            self.vc_info.resample_ratio_out,
            self.vc_info.resample_ratio_monitor,
        )

        logger.info(
            "  self.vc_info.vc_input_sample_rate:%s, self.input_sample_rate:%s",
            self.vc_info.vc_input_sample_rate,
            self.input_sample_rate,
        )

        logger.info(
            "  self.vc_info.vc_output_sample_rate:%s, self.output_sample_rate:%s",
            self.vc_info.vc_output_sample_rate,
            self.output_sample_rate,
        )

        logger.info(
            "  self.vc_monitor_sample_rate:%s, self.monitor_sample_rate:%s",
            self.vc_info.vc_output_sample_rate,
            self.monitor_sample_rate,
        )

        self.resampler_in = sr.Resampler("sinc_best", channels=1)

        self.resampler_out = sr.Resampler("sinc_best", channels=1)

        self.resampler_monitor = sr.Resampler("sinc_best", channels=1)

    def _check_and_update_sample_rate(self) -> None:
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        input_sample_rate = conf.input_sample_rate
        output_sample_rate = conf.output_sample_rate
        moniotr_sample_rate = conf.monitor_sample_rate
        if (
            self.vc_info.input_sample_rate != input_sample_rate
            or self.vc_info.output_sample_rate != output_sample_rate
            or self.vc_info.monitor_sample_rate != moniotr_sample_rate
        ):
            self.vc_info.input_sample_rate = input_sample_rate
            self.vc_info.output_sample_rate = output_sample_rate
            self.vc_info.monitor_sample_rate = moniotr_sample_rate
            self._set_io_sample_rate()
            return None

    def _generate_filter(self) -> None:
        if hasattr(self, "input_sample_rate") is False:
            return None

        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        (bh, ah) = signal.butter(N=5, Wn=conf.high_pass_filter_cutoff, btype="high", fs=self.input_sample_rate)
        self.bh = bh
        self.ah = ah

        low_pass_filter_cutoff = min(conf.low_pass_filter_cutoff, self.input_sample_rate / 2) - 1
        (bl, al) = signal.butter(N=5, Wn=low_pass_filter_cutoff, btype="low", fs=self.input_sample_rate)
        self.bl = bl
        self.al = al

        (bb, ab) = signal.butter(
            N=5, Wn=[conf.high_pass_filter_cutoff, low_pass_filter_cutoff], btype="band", fs=self.input_sample_rate
        )
        self.bb = bb
        self.ab = ab

    def _check_and_update_filter(self) -> None:
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        if (
            self.vc_info.enable_high_pass_filter != conf.enable_high_pass_filter
            or self.vc_info.high_pass_filter_cutoff != conf.high_pass_filter_cutoff
            or self.vc_info.enable_low_pass_filter != conf.enable_low_pass_filter
            or self.vc_info.low_pass_filter_cutoff != conf.low_pass_filter_cutoff
        ):
            self.vc_info.enable_high_pass_filter = conf.enable_high_pass_filter
            self.vc_info.high_pass_filter_cutoff = conf.high_pass_filter_cutoff
            self.vc_info.enable_low_pass_filter = conf.enable_low_pass_filter
            self.vc_info.low_pass_filter_cutoff = conf.low_pass_filter_cutoff
            self._generate_filter()
            return None

    def _exec_filter_in_high_pass(self, waveform: np.ndarray) -> np.ndarray:
        return signal.filtfilt(self.bh, self.ah, waveform)

    def _exec_filter_in_low_pass(self, waveform: np.ndarray) -> np.ndarray:
        return signal.filtfilt(self.bl, self.al, waveform)

    def _exec_filter_in_band_pass(self, waveform: np.ndarray) -> np.ndarray:
        return signal.filtfilt(self.bb, self.ab, waveform)

    def _exec_resample_in(self, waveform: np.ndarray) -> np.ndarray:
        return self.resampler_in.process(waveform, self.vc_info.resample_ratio_in, end_of_input=False)

    def _exec_resample_out(self, waveform: np.ndarray) -> np.ndarray:
        return self.resampler_out.process(waveform, self.vc_info.resample_ratio_out, end_of_input=False)

    def _exec_resample_monitor(self, waveform: np.ndarray) -> np.ndarray:
        return self.resampler_monitor.process(waveform, self.vc_info.resample_ratio_monitor, end_of_input=False)

    def _exec_resample_pass_through_in_out(self, waveform: np.ndarray) -> np.ndarray:
        return self.resampler_monitor.process(
            waveform, self.vc_info.resample_ratio_pass_through_in_out, end_of_input=False
        )

    def _exec_resample_pass_through_in_monitor(self, waveform: np.ndarray) -> np.ndarray:
        return self.resampler_monitor.process(
            waveform, self.vc_info.resample_ratio_pass_through_in_monitor, end_of_input=False
        )

    def get_voice_changer_information(self) -> VoiceChangerInformation:
        self._check_reload_model_is_required_and_update()
        if self.vc_pipeline is None:
            logger.warning("vc_pipeline is None, returning default vc_info")
            return self.vc_info

        self._check_and_update_pitch_estimator()
        self._check_and_update_sample_rate()
        self._check_and_update_filter()
        pipeline = self._require_pipeline()
        self.vc_info.chunk_sec = pipeline.get_chunk_sec()
        self.vc_info.pipeline_info = pipeline.get_pipeline_info()
        return self.vc_info

    def set_monitor_enable(self, enable: bool) -> None:
        """ローカルマイクでのモニタリング。ブラウザ経由ではブラウザ上でやるので無視してよい。"""
        self.vc_info.monitor_enabled = enable

    def start_recording(self) -> None:
        if self.vc_info.recording_start_flag is True:
            logger.warning("recording process is already started.")
            return None
        self.input_record = []
        self.output_record = []
        self.monitor_record = []
        self.vc_info.recording_start_flag = True

    def stop_recording(self) -> None:
        if self.vc_info.recording_start_flag is False:
            logger.warning("recording process is already stopped.")
            return None
        self.vc_info.recording_start_flag = False
        self._save_record()

    def _save_record(self) -> None:
        try:
            wavfile.write(SERVER_IO_RECORDING_FILE_IN, self.input_sample_rate, np.concatenate(self.input_record))
            wavfile.write(SERVER_IO_RECORDING_FILE_OUT, self.output_sample_rate, np.concatenate(self.output_record))
            if self.vc_info.monitor_enabled is True:
                wavfile.write("monitor.wav", self.output_sample_rate, np.concatenate(self.monitor_record))
        except Exception as e:
            logger.warning("Failed to save recording: %s", e, exc_info=True)
            raise VCClientError(ERROR_CODE_RECORDING_FAILED, f"Failed to save recording:{e}")

    waveform_rest: np.ndarray = np.array([])
    convert_chunk_bulk_queue_in: Queue[np.ndarray] = Queue()
    convert_chunk_bulk_queue_out: Queue[tuple[np.ndarray, PerformanceData | None]] = Queue()
    convert_chunk_bulk_queue_monitor: Queue[tuple[np.ndarray, PerformanceData | None]] = Queue()

    def is_convert_chunk_bulk_started(self) -> bool:
        return self.vc_info.bulk_process_start_flag

    def start_convert_chunk_bulk(self) -> None:
        logger.warning("start_convert_chunk_bulk called")
        if self.vc_info.bulk_process_start_flag is True:
            logger.warning("bulk conversion process is already started.")
            return None
        self.vc_info.bulk_process_start_flag = True
        self.bulk_process = threading.Thread(target=self.convert_chunk_bulk_internal)
        self.bulk_process.start()

    def stop_convert_chunk_bulk(self) -> None:
        if self.vc_info.bulk_process_start_flag is False:
            logger.debug("bulk conversion process is already stopped.")
            return None
        self.vc_info.bulk_process_start_flag = False
        if self.bulk_process is not None and self.bulk_process.is_alive():
            self.bulk_process.join()
            return None

    def convert_chunk_bulk(
        self, waveform: np.ndarray
    ) -> tuple[np.ndarray | None, np.ndarray | None, PerformanceData | None]:
        self._check_reload_model_is_required_and_update()
        self._check_and_update_pitch_estimator()
        self._check_and_update_sample_rate()
        self._check_and_update_filter()
        try:
            if self.vc_info.bulk_process_start_flag is False:
                logger.debug("bulk conversion process is not started.")
                return (None, None, None)
            if self.waveform_rest.dtype != waveform.dtype:
                self.waveform_rest = np.array([], dtype=waveform.dtype)
            self.waveform_rest = np.concatenate([self.waveform_rest, waveform])
            self._check_reload_model_is_required_and_update()
            self.vc_chunk_sec = self._require_pipeline().get_chunk_sec()
            self.chunk_size = int(round(self.input_sample_rate * self.vc_chunk_sec))
            splitted_waveforms = [
                self.waveform_rest[i : i + self.chunk_size] for i in range(0, len(self.waveform_rest), self.chunk_size)
            ]
            if len(splitted_waveforms[-1]) < self.chunk_size:
                self.waveform_rest = splitted_waveforms.pop()
            else:
                self.waveform_rest = np.array([], dtype=waveform.dtype)
            for w in splitted_waveforms:
                self.convert_chunk_bulk_queue_in.put(w)
            out_ready_size = self.convert_chunk_bulk_queue_out.qsize()
            if out_ready_size == 0:
                output = None
                accumulated_performance_data = None
            else:
                converted_waveforms = []
                accumulated_performance_data = PerformanceData()
                accumulated_performance_data_num = 0
                for _i in range(out_ready_size):
                    converted_waveform, performance_data = self.convert_chunk_bulk_queue_out.get()
                    converted_waveforms.append(converted_waveform)
                    if performance_data is not None:
                        performance_dict = performance_data.model_dump()
                        for k, v in performance_dict.items():
                            setattr(accumulated_performance_data, k, getattr(accumulated_performance_data, k) + v)
                        accumulated_performance_data_num += 1
                output = np.concatenate(converted_waveforms)
                if accumulated_performance_data_num > 0:
                    for k, v in accumulated_performance_data.model_dump().items():
                        setattr(accumulated_performance_data, k, v / accumulated_performance_data_num)
                    accumulated_performance_data.data_num = accumulated_performance_data_num
                else:
                    accumulated_performance_data = None

            if self.vc_info.monitor_enabled is True:
                monitor_ready_size = self.convert_chunk_bulk_queue_monitor.qsize()
                if monitor_ready_size == 0:
                    monitor = None
                else:
                    monitor_waveforms = []
                    for _i in range(monitor_ready_size):
                        converted_waveform, _ = self.convert_chunk_bulk_queue_monitor.get()
                        monitor_waveforms.append(converted_waveform)
                    monitor = np.concatenate(monitor_waveforms)
            else:
                monitor = None

            if self.vc_info.monitor_enabled is False:
                return (output, None, accumulated_performance_data)
            return (output, monitor, accumulated_performance_data)
        except Exception as e:
            logger.warning("Failed to convert_chunk_bulk: %s", e, exc_info=True)
            raise e

    def convert_chunk_bulk_internal(self) -> None:
        while True:
            try:
                if self.vc_info.bulk_process_start_flag is False:
                    logger.debug("bulk conversion process awared the stop operation.")
                    self.convert_chunk_bulk_queue_in = Queue()
                    self.convert_chunk_bulk_queue_out = Queue()
                    self.convert_chunk_bulk_queue_monitor = Queue()
                    return None
                w = self.convert_chunk_bulk_queue_in.get(timeout=0.5)
                converted, converted_for_monitor, performance_data = self.convert_chunk(w)
                self.convert_chunk_bulk_queue_out.put((converted, performance_data))
                if converted_for_monitor is not None:
                    self.convert_chunk_bulk_queue_monitor.put((converted_for_monitor, performance_data))
            except Empty:
                pass
            except Exception as e:
                logger.warning("Failed to convert_chunk_bulk_internal: %s", e, exc_info=True)

    def convert_chunk(
        self, waveform: np.ndarray, direct_from_server: bool | None = None
    ) -> tuple[np.ndarray, np.ndarray | None, PerformanceData | None]:
        """Convert waveform.

        Args:
            waveform (np.ndarray): waveform data. int16 or float32. shape: (n,)

        Returns:
            np.ndarray: converted waveform. int16 or float32. shape: (n,)
            np.ndarray: converted waveform for monitor. int16 or float32. shape: (n,)
        """
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        if conf.enable_performance_monitor is True:
            start_time = time.time()
            (output, monitor) = self._convert_chunk(waveform, direct_from_server=direct_from_server)
            end_time = time.time()
            elapsed_time = round(end_time - start_time, 3)
            input_size = len(waveform)
            output_size = len(output)
            reference_volume = 1

            input_volume = np.sqrt(np.mean(waveform**2))
            if input_volume < 1e-06:
                input_volume_db = -(np.inf)
            else:
                input_volume_db = 20 * np.log10(input_volume / reference_volume)
            input_volume_db = round(input_volume_db, 2)

            output_volume = np.sqrt(np.mean(output**2))
            if output_volume < 1e-06:
                output_volume_db = -(np.inf)
            else:
                output_volume_db = 20 * np.log10(output_volume / reference_volume)
            output_volume_db = round(output_volume_db, 2)

            performance_data = PerformanceData(
                input_size=input_size,
                input_sec=self.vc_chunk_sec if hasattr(self, "vc_chunk_sec") else 0,
                output_size=output_size,
                output_sec=self.vc_chunk_sec if hasattr(self, "vc_chunk_sec") else 0,
                elapsed_time=elapsed_time,
                input_volume_db=input_volume_db,
                output_volume_db=output_volume_db,
                data_num=1,
            )

            if self.performance_listener is not None:
                self.performance_listener(performance_data)

            return (output, monitor, performance_data)

        (output, monitor) = self._convert_chunk(waveform, direct_from_server=direct_from_server)
        return (output, monitor, None)

    def _convert_chunk(
        self, waveform: np.ndarray, direct_from_server: bool | None = None
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """Convert waveform.

        Args:
            waveform (np.ndarray): waveform data. int16 or float32. shape: (n,)

        Returns:
            np.ndarray: converted waveform. int16 or float32. shape: (n,)
            np.ndarray: converted waveform for monitor. int16 or float32. shape: (n,)
        """
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()

        if conf.pass_through is True or getattr(self, "vc_pipeline", None) is None:
            self._check_and_update_sample_rate()
            waveform_out = self._exec_resample_pass_through_in_out(waveform)
            if self.vc_info.recording_start_flag is True:
                self.output_record.append(waveform_out)
            if self.vc_info.monitor_enabled is True:
                waveform_monitor = self._exec_resample_pass_through_in_monitor(waveform)
                if self.vc_info.recording_start_flag is True:
                    self.monitor_record.append(waveform_monitor)
                return (waveform_out, waveform_monitor)
            return (waveform_out, None)

        self._check_reload_model_is_required_and_update()
        self._check_and_update_pitch_estimator()
        self._check_and_update_sample_rate()
        self._check_and_update_filter()

        pipeline = self._require_pipeline()
        vc_chunk_sec = pipeline.get_chunk_sec()
        vc_input_bitdepth = pipeline.get_input_bitdepth()
        vc_output_bitdepth = pipeline.get_output_bitdepth()
        vc_needs_crossfade = pipeline.needs_crossfade()

        if direct_from_server is True:
            input_size = int(self.vc_info.resample_ratio_in * waveform.shape[0])
            output_size = int((input_size / self.vc_info.vc_input_sample_rate) * self.vc_info.vc_output_sample_rate)
        else:
            input_size = int(self.vc_info.vc_input_sample_rate * vc_chunk_sec)
            output_size = int(self.vc_info.vc_output_sample_rate * vc_chunk_sec)

        if self.vc_info.recording_start_flag is True:
            self.input_record.append(waveform)

        input_data_type = waveform.dtype
        if vc_input_bitdepth == np.int16 and waveform.dtype != np.int16:
            waveform = (waveform * 32768).astype(np.int16)
        elif vc_input_bitdepth == np.float32 and waveform.dtype != np.float32:
            waveform = (waveform / 32768).astype(np.float32)

        try:
            if conf.enable_high_pass_filter is True and conf.enable_low_pass_filter is True:
                filtered_waveform = self._exec_filter_in_band_pass(waveform)
            elif conf.enable_high_pass_filter is True:
                filtered_waveform = self._exec_filter_in_high_pass(waveform)
            elif conf.enable_low_pass_filter is True:
                filtered_waveform = self._exec_filter_in_low_pass(waveform)
            else:
                filtered_waveform = waveform
        except Exception as e:
            logger.warning("Failed to filter_in(ignored): %s", e)
            filtered_waveform = waveform

        resampled_waveform = self._exec_resample_in(filtered_waveform)
        if resampled_waveform.shape[0] < input_size:
            original_shape = resampled_waveform.shape
            resampled_waveform = np.concatenate(
                [resampled_waveform, np.zeros(input_size - resampled_waveform.shape[0])]
            )
            padded_shape = resampled_waveform.shape
            logger.debug("data type resampled is short. padded.: %s, shape: %s", original_shape, padded_shape)

        real_crossfade_sec = min(vc_chunk_sec, conf.crossfade_sec)
        converted_waveform = pipeline.run(resampled_waveform, real_crossfade_sec=real_crossfade_sec)
        if vc_needs_crossfade is True:
            crossfade_frame = int(round(real_crossfade_sec * self.vc_info.vc_output_sample_rate))
            sola_search_frame = int(round(conf.sola_search_frame_sec * self.vc_info.vc_output_sample_rate))
            crossfaded_waveform = self.crossfade_processor.apply(
                converted_waveform, output_size, crossfade_frame, 0, 1, sola_search_frame
            )
        else:
            crossfaded_waveform = converted_waveform

        resampled_waveform_out = self._exec_resample_out(crossfaded_waveform)
        if vc_output_bitdepth != input_data_type:
            if input_data_type == np.int16:
                resampled_waveform_out = (resampled_waveform_out * 32768).astype(np.int16)
            elif input_data_type == np.float32:
                resampled_waveform_out = (resampled_waveform_out / 32768).astype(np.float32)

        if self.vc_info.recording_start_flag is True:
            self.output_record.append(resampled_waveform_out)

        # Read monitor_enabled once: another thread may toggle it during conversion.
        resampled_waveform_monitor: np.ndarray | None = None
        if self.vc_info.monitor_enabled is True:
            resampled_waveform_monitor = self._exec_resample_monitor(crossfaded_waveform)
            if vc_output_bitdepth != input_data_type:
                if input_data_type == np.int16:
                    resampled_waveform_monitor = (resampled_waveform_monitor * 32768).astype(np.int16)
                elif input_data_type == np.float32:
                    resampled_waveform_monitor = (resampled_waveform_monitor / 32768).astype(np.float32)
            if self.vc_info.recording_start_flag is True:
                self.monitor_record.append(resampled_waveform_monitor)

        return (resampled_waveform_out, resampled_waveform_monitor)

    def convert_file(self, input_file: str, output_file: str) -> None:
        logger.info("file convert starts: %s -> %s", input_file, output_file)
        input_path = Path(input_file)
        if input_path.exists() is False:
            raise FileNotFoundError(f"Input file not found:{input_file}")
        src_sample_rate, waveform = wavfile.read(input_path)
        if waveform.dtype == np.float32 or waveform.dtype == np.float64:
            waveform = (waveform * 32768).astype(np.int16)
        logger.info("srcSampleRate:%s, waveform:%s", src_sample_rate, waveform.shape)
        configuration = ConfigurationManager.get_instance().get_voice_changer_configuration()
        configuration.input_sample_rate = src_sample_rate
        configuration.output_sample_rate = src_sample_rate
        self.vc_chunk_sec = self._require_pipeline().get_chunk_sec()
        self.chunk_size = int(round(src_sample_rate * self.vc_chunk_sec))
        splitted_waveforms = [waveform[i : i + self.chunk_size] for i in range(0, len(waveform), self.chunk_size)]
        chunk_num = len(splitted_waveforms)
        logger.info("chunk_size:%s, chunk_num:%s", self.chunk_size, chunk_num)
        convertd_datas = []
        with Timer("converting", enable=False) as t:
            for i, splitted_waveform in enumerate(splitted_waveforms):
                resampled_converted, _, _ = self.convert_chunk(splitted_waveform)
                convertd_datas.append(resampled_converted)
                print(f"converting... {i * 100 // chunk_num}%")
                t.record(f"chunk-{i}")
        output_data = np.concatenate(convertd_datas)
        wavfile.write(output_file, src_sample_rate, output_data)
        logger.info("file convert done: %s -> %s", input_file, output_file)

    def __del__(self) -> None:
        logger.info("VoiceChanger is deleting.")
        if self.vc_info.bulk_process_start_flag is True:
            logger.info("bulk_process is stopping.")
            self.stop_convert_chunk_bulk()
        logger.info("VoiceChanger is deleted.")
