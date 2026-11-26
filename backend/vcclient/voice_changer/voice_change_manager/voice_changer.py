import gc
import threading
import time
from queue import Empty, Queue
from typing import Any

import numpy as np
import samplerate as sr
from scipy import signal
from scipy.io import wavfile

from vcclient.logger import logger

from ...const import SERVER_IO_RECORDING_FILE_OUT
from ...exception import (
    ERROR_CODE_MODEL_UPDATE_FAILED,
    ERROR_CODE_PIPELINE_IS_NOT_INITIALIZED,
    ERROR_CODE_RECORDING_FAILED,
    VCClientError,
)
from ..configuration_manager.configuration_manager import ConfigurationManager
from ..data_types.data_types import PerformanceData
from ..data_types.slot_manager_data_types import RVCSlotInfo, SlotInfoMember
from ..data_types.voice_changer_data_types import VoiceChangerInformation
from ..event_emitter import EventEmitter
from ..voice_changer_const import (
    CROSSFADE_SEC,
    GET_GPU_DEVICE_ID_IS_NOT_AVAILABLE,
    REALTIME_PROCESS_STATUS_SEND_INTERVAL_SEC,
    SOLA_SEARCH_FRAME_SEC,
    PitchEstimatorType,
)
from .crossfade_processor import CrossfadeProcessor
from .vc_pipelines.pipeline_manager import PipelineManager
from .vc_pipelines.rvc_pipeline import RVCPipeline
from .vc_pipelines.vc_pipeline import VCPipeline

SILENCE_SKIP_DELAY_SEC = 0.2


class VoiceChanger(EventEmitter):
    _instance: VoiceChanger | None = None

    vc_info: VoiceChangerInformation
    crossfade_processor: CrossfadeProcessor
    bulk_process: threading.Thread | None
    vc_pipeline: VCPipeline | None
    output_record: list[np.ndarray]
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
    _active_snapshot: Any
    _filter_coeffs: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None

    @classmethod
    def peek_instance(cls) -> VoiceChanger | None:
        return cls._instance

    @classmethod
    def get_or_create_raw(cls) -> VoiceChanger:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def get_instance(cls) -> VoiceChanger:
        if cls._instance is None:
            cls._instance = cls()
        cls._instance.check_and_update_pipeline()
        return cls._instance

    def check_and_update_pipeline(self) -> None:
        if getattr(self, "_active_snapshot", None) is not None:
            return None
        logger.info("[check_and_update_pipeline]")
        self._check_reload_model_is_required_and_update()
        self._check_and_update_pitch_estimator()
        self._check_and_update_sample_rate()
        self._check_and_update_filter()

    def __init__(self) -> None:
        super().__init__()
        self.initialize()
        self.realtime_process_status_send_counter = 0

    def initialize(self) -> None:
        self.vc_info = VoiceChangerInformation()
        self.crossfade_processor = CrossfadeProcessor()
        self.bulk_process = None
        self.vc_pipeline = None
        self._active_snapshot = None
        self._filter_coeffs = None
        self.output_record = []
        self.resampler_in = sr.Resampler("sinc_best", channels=1)
        self.resampler_out = sr.Resampler("sinc_best", channels=1)
        self.resampler_monitor = sr.Resampler("sinc_best", channels=1)

    def _require_pipeline(self) -> VCPipeline:
        if self.vc_pipeline is None:
            raise VCClientError(ERROR_CODE_PIPELINE_IS_NOT_INITIALIZED, "Voice changer pipeline is not initialized.")
        return self.vc_pipeline

    def _apply_slot_info(self, slot_info: SlotInfoMember) -> None:
        if (
            self.vc_pipeline is not None
            and getattr(getattr(self.vc_pipeline, "device", None), "provider", None) == "webgpu"
        ):
            self.vc_pipeline = None
            gc.collect()
        pipeline = PipelineManager.get_pipeline(slot_info)
        self.vc_pipeline = pipeline
        self.vc_info.voice_changer_type = slot_info.voice_changer_type
        self.vc_info.vc_input_sample_rate = pipeline.get_input_sample_rate()
        self.vc_info.vc_output_sample_rate = pipeline.get_output_sample_rate()
        self.vc_info.pitch_estimator_type = pipeline.get_pitch_estimator_type()
        self.vc_info.gpu_device_index = pipeline.get_gpu_device_id()

    def _update_model_by_id(self, model_id: str) -> None:
        try:
            from ..model_catalog import get_slot_info_by_model_id

            slot_info = get_slot_info_by_model_id(model_id)
            if slot_info is None:
                raise VCClientError(ERROR_CODE_MODEL_UPDATE_FAILED, f"Model '{model_id}' not found.")
            self._apply_slot_info(slot_info)
            logger.info(
                "model_id Changed: %s, gpu_device_index: %s",
                model_id,
                self.vc_info.gpu_device_index,
            )
        except Exception as e:
            logger.warning("Failed to update model '%s': %s", model_id, e)
            if isinstance(e, VCClientError):
                raise
            raise VCClientError(ERROR_CODE_MODEL_UPDATE_FAILED, f"Failed to update model:{e}")

    def _check_reload_model_is_required_and_update(self) -> None:
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        shape_changed = (
            isinstance(self.vc_pipeline, RVCPipeline)
            and self.vc_pipeline.target_frames != self.vc_pipeline._calculate_target_feats_length()
        )
        gpu_changed = (
            self.vc_info.gpu_device_index != conf.gpu_device_id_int
            and self.vc_info.gpu_device_index != GET_GPU_DEVICE_ID_IS_NOT_AVAILABLE
        )
        target_model_id = getattr(conf, "model_id", None)
        current_model_id = getattr(self.vc_info, "model_id", None)

        if target_model_id is not None:
            if current_model_id != target_model_id or gpu_changed or shape_changed or self.vc_pipeline is None:
                logger.info(
                    "model_id: %s -> %s, gpu_device_index: %s -> %s",
                    current_model_id,
                    target_model_id,
                    self.vc_info.gpu_device_index,
                    conf.gpu_device_id_int,
                )
                prev_model_id = current_model_id
                prev_gpu_index = self.vc_info.gpu_device_index
                try:
                    self._update_model_by_id(target_model_id)
                    self.vc_info.model_id = target_model_id
                    self.vc_info.slot_index = -1
                    self.vc_info.gpu_device_index = conf.gpu_device_id_int
                    self._set_io_sample_rate()
                except Exception as e:
                    logger.error("Failed to switch model to '%s': %s", target_model_id, e)
                    self.vc_info.model_id = prev_model_id
                    self.vc_info.gpu_device_index = prev_gpu_index
                    if shape_changed and target_model_id == prev_model_id and conf.gpu_device_id_int == prev_gpu_index:
                        raise
                    conf.model_id = prev_model_id
                    ConfigurationManager.get_instance().set_voice_changer_configuration(conf)
            return None

        if current_model_id is not None or self.vc_pipeline is not None:
            self.vc_pipeline = None
            self.vc_info.model_id = None
            self.vc_info.slot_index = -1
            self.vc_info.voice_changer_type = None
            self.vc_info.pitch_estimator_type = None
            self.vc_info.pipeline_info = None
        return None

    def _set_pitch_estimator(self, pitch_estimator: PitchEstimatorType) -> None:
        pipeline = self._require_pipeline()
        pipeline.set_pitch_estimator_type(pitch_estimator)
        PipelineManager.warmup(pipeline)

    def _check_and_update_pitch_estimator(self) -> None:
        current_model_id = getattr(self.vc_info, "model_id", None)
        if current_model_id is None:
            return None
        from ..model_catalog import get_slot_info_by_model_id

        slot_info = get_slot_info_by_model_id(current_model_id)
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

        if self.vc_info.slot_index == -1 and getattr(self.vc_info, "model_id", None) is None:
            logger.warning("Slot index is not set")
            return None

        self.input_sample_rate = self.vc_info.input_sample_rate
        self.output_sample_rate = self.vc_info.output_sample_rate
        self.monitor_sample_rate = (
            self.vc_info.monitor_sample_rate if self.vc_info.monitor_sample_rate > 0 else self.output_sample_rate
        )
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

    @staticmethod
    def _compute_filter_coeffs(
        input_sample_rate: int,
        high_cutoff: float,
        low_cutoff: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        (bh, ah) = signal.butter(N=5, Wn=high_cutoff, btype="high", fs=input_sample_rate)
        clamped_low = min(low_cutoff, (input_sample_rate / 2) * 0.9)
        (bl, al) = signal.butter(N=5, Wn=clamped_low, btype="low", fs=input_sample_rate)
        (bb, ab) = signal.butter(N=5, Wn=[high_cutoff, clamped_low], btype="band", fs=input_sample_rate)
        return (bh, ah, bl, al, bb, ab)

    def _generate_filter(self) -> None:
        if hasattr(self, "input_sample_rate") is False:
            return None

        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        coeffs = self._compute_filter_coeffs(
            self.input_sample_rate, conf.high_pass_filter_cutoff, conf.low_pass_filter_cutoff
        )
        self._filter_coeffs = coeffs
        (self.bh, self.ah, self.bl, self.al, self.bb, self.ab) = coeffs

    def reset_client_stream_buffers(self) -> None:
        self.waveform_rest = np.array([], dtype=np.float32)
        for queue_obj in (
            self.convert_chunk_bulk_queue_in,
            self.convert_chunk_bulk_queue_out,
            self.convert_chunk_bulk_queue_monitor,
        ):
            while True:
                try:
                    queue_obj.get_nowait()
                except Empty:
                    break

    def configure_for_session(
        self,
        snapshot: Any,
        pipeline: VCPipeline,
        *,
        input_sample_rate: int,
        output_sample_rate: int,
        monitor_sample_rate: int | None,
    ) -> None:
        self.vc_pipeline = pipeline
        self.vc_info.model_id = snapshot.model_id
        self.vc_info.slot_index = -1
        self.vc_info.gpu_device_index = snapshot.compute_device_id
        slot_meta = getattr(pipeline, "_slot_info", None)
        self.vc_info.voice_changer_type = getattr(slot_meta, "voice_changer_type", "RVC")
        self.vc_info.vc_input_sample_rate = pipeline.get_input_sample_rate()
        self.vc_info.vc_output_sample_rate = pipeline.get_output_sample_rate()
        self.vc_info.pitch_estimator_type = pipeline.get_pitch_estimator_type()
        self.vc_info.chunk_sec = pipeline.get_chunk_sec()
        self.vc_info.input_sample_rate = input_sample_rate
        self.vc_info.output_sample_rate = output_sample_rate
        self.vc_info.monitor_sample_rate = monitor_sample_rate if monitor_sample_rate is not None else -1
        self.vc_info.monitor_enabled = (
            snapshot.input_mode == "server"
            and monitor_sample_rate is not None
            and snapshot.audio_monitor_device_index != -1
        )
        self.vc_info.enable_high_pass_filter = snapshot.enable_high_pass_filter
        self.vc_info.high_pass_filter_cutoff = snapshot.high_pass_filter_cutoff
        self.vc_info.enable_low_pass_filter = snapshot.enable_low_pass_filter
        self.vc_info.low_pass_filter_cutoff = snapshot.low_pass_filter_cutoff
        self._set_io_sample_rate()
        coeffs = self._compute_filter_coeffs(
            self.input_sample_rate,
            snapshot.high_pass_filter_cutoff,
            snapshot.low_pass_filter_cutoff,
        )
        self._filter_coeffs = coeffs
        (self.bh, self.ah, self.bl, self.al, self.bb, self.ab) = coeffs
        self.crossfade_processor = CrossfadeProcessor()
        self.reset_client_stream_buffers()
        self.vc_info.pipeline_info = pipeline.get_pipeline_info()
        self._active_snapshot = snapshot

    def apply_live_snapshot(self, snapshot: Any) -> None:
        prev = getattr(self, "_active_snapshot", None)
        if (
            prev is None
            or prev.high_pass_filter_cutoff != snapshot.high_pass_filter_cutoff
            or prev.low_pass_filter_cutoff != snapshot.low_pass_filter_cutoff
            or getattr(self, "_filter_coeffs", None) is None
        ):
            coeffs = self._compute_filter_coeffs(
                self.input_sample_rate,
                snapshot.high_pass_filter_cutoff,
                snapshot.low_pass_filter_cutoff,
            )
            self._filter_coeffs = coeffs
            (self.bh, self.ah, self.bl, self.al, self.bb, self.ab) = coeffs
        self.vc_info.enable_high_pass_filter = snapshot.enable_high_pass_filter
        self.vc_info.high_pass_filter_cutoff = snapshot.high_pass_filter_cutoff
        self.vc_info.enable_low_pass_filter = snapshot.enable_low_pass_filter
        self.vc_info.low_pass_filter_cutoff = snapshot.low_pass_filter_cutoff
        self._active_snapshot = snapshot
        if snapshot.recording and not self.vc_info.recording_start_flag:
            self.start_recording()
        elif not snapshot.recording and self.vc_info.recording_start_flag:
            self.stop_recording()

    def clear_session_snapshot(self) -> None:
        self._active_snapshot = None

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
        return self.resampler_out.process(waveform, self.vc_info.resample_ratio_pass_through_in_out, end_of_input=False)

    def _exec_resample_pass_through_in_monitor(self, waveform: np.ndarray) -> np.ndarray:
        return self.resampler_monitor.process(
            waveform, self.vc_info.resample_ratio_pass_through_in_monitor, end_of_input=False
        )

    def get_voice_changer_information(self) -> VoiceChangerInformation:
        if getattr(self, "_active_snapshot", None) is not None:
            if self.vc_pipeline is not None:
                self.vc_info.chunk_sec = self.vc_pipeline.get_chunk_sec()
                self.vc_info.pipeline_info = self.vc_pipeline.get_pipeline_info()
            return self.vc_info
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
        self.output_record = []
        self.vc_info.recording_start_flag = True

    def stop_recording(self) -> None:
        if self.vc_info.recording_start_flag is False:
            logger.warning("recording process is already stopped.")
            return None
        self.vc_info.recording_start_flag = False
        self._save_record()

    def _save_record(self) -> None:
        def audio(chunks: list[np.ndarray]) -> np.ndarray:
            if not chunks:
                return np.empty(0, dtype=np.float32)
            return np.concatenate(
                [chunk.astype(np.float32) / 32768 if chunk.dtype == np.int16 else chunk for chunk in chunks]
            )

        try:
            sample_rate = getattr(self, "output_sample_rate", None)
            if not isinstance(sample_rate, int) or sample_rate <= 0:
                sample_rate = ConfigurationManager.get_instance().get_voice_changer_configuration().output_sample_rate
            wavfile.write(
                SERVER_IO_RECORDING_FILE_OUT,
                sample_rate,
                audio(self.output_record),
            )
        except Exception as e:
            logger.warning("Failed to save recording: %s", e, exc_info=True)
            raise VCClientError(ERROR_CODE_RECORDING_FAILED, f"Failed to save recording:{e}")

    waveform_rest: np.ndarray = np.array([])
    convert_chunk_bulk_queue_in: Queue[np.ndarray] = Queue()
    convert_chunk_bulk_queue_out: Queue[np.ndarray] = Queue()
    convert_chunk_bulk_queue_monitor: Queue[np.ndarray] = Queue()

    def is_convert_chunk_bulk_started(self) -> bool:
        return self.vc_info.bulk_process_start_flag

    def start_convert_chunk_bulk(self) -> None:
        logger.warning("start_convert_chunk_bulk called")
        if self.vc_info.bulk_process_start_flag is True:
            logger.warning("bulk conversion process is already started.")
            return None
        self.check_and_update_pipeline()
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

    def convert_chunk_bulk(self, waveform: np.ndarray) -> tuple[np.ndarray | None, np.ndarray | None]:
        try:
            if self.vc_info.bulk_process_start_flag is False:
                logger.debug("bulk conversion process is not started.")
                return (None, None)
            if self.waveform_rest.dtype != waveform.dtype:
                self.waveform_rest = np.array([], dtype=waveform.dtype)
            self.waveform_rest = np.concatenate([self.waveform_rest, waveform])
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
            else:
                converted_waveforms = [self.convert_chunk_bulk_queue_out.get() for _i in range(out_ready_size)]
                output = np.concatenate(converted_waveforms)

            if self.vc_info.monitor_enabled is True:
                monitor_ready_size = self.convert_chunk_bulk_queue_monitor.qsize()
                if monitor_ready_size == 0:
                    monitor = None
                else:
                    monitor_waveforms = [
                        self.convert_chunk_bulk_queue_monitor.get() for _i in range(monitor_ready_size)
                    ]
                    monitor = np.concatenate(monitor_waveforms)
            else:
                monitor = None

            if self.vc_info.monitor_enabled is False:
                return (output, None)
            return (output, monitor)
        except Exception as e:
            logger.warning("Failed to convert_chunk_bulk: %s", e, exc_info=True)
            raise e

    def convert_chunk_bulk_internal(self) -> None:
        silent_input_samples = 0
        monitor_silent_input_samples = 0
        while True:
            try:
                if self.vc_info.bulk_process_start_flag is False:
                    logger.debug("bulk conversion process awared the stop operation.")
                    self.convert_chunk_bulk_queue_in = Queue()
                    self.convert_chunk_bulk_queue_out = Queue()
                    self.convert_chunk_bulk_queue_monitor = Queue()
                    return None
                w = self.convert_chunk_bulk_queue_in.get(timeout=0.5)
                converted, converted_for_monitor = self.convert_chunk(w)
                silence_delay_samples = round(self.input_sample_rate * SILENCE_SKIP_DELAY_SEC)
                if np.any(converted):
                    silent_input_samples = 0
                    self.convert_chunk_bulk_queue_out.put(converted)
                else:
                    if silent_input_samples < silence_delay_samples:
                        self.convert_chunk_bulk_queue_out.put(converted)
                    silent_input_samples += len(w)

                if converted_for_monitor is None:
                    monitor_silent_input_samples = 0
                elif np.any(converted_for_monitor):
                    monitor_silent_input_samples = 0
                    self.convert_chunk_bulk_queue_monitor.put(converted_for_monitor)
                else:
                    if monitor_silent_input_samples < silence_delay_samples:
                        self.convert_chunk_bulk_queue_monitor.put(converted_for_monitor)
                    monitor_silent_input_samples += len(w)
            except Empty:
                pass
            except Exception as e:
                logger.warning("Failed to convert_chunk_bulk_internal: %s", e, exc_info=True)

    def convert_chunk(self, waveform: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
        """Convert waveform.

        Args:
            waveform (np.ndarray): waveform data. int16 or float32. shape: (n,)

        Returns:
            np.ndarray: converted waveform. int16 or float32. shape: (n,)
            np.ndarray: converted waveform for monitor. int16 or float32. shape: (n,)
        """
        snap = getattr(self, "_active_snapshot", None)
        if snap is not None:
            perf_enabled = snap.realtime_process_status_enabled and snap.enable_performance_monitor
        else:
            conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
            perf_enabled = conf.realtime_process_status_enabled and conf.enable_performance_monitor
        if perf_enabled is True:
            self.realtime_process_status_send_counter += 1
            chunk_sec = self.vc_chunk_sec if hasattr(self, "vc_chunk_sec") and self.vc_chunk_sec > 0 else 0.1
            if self.realtime_process_status_send_counter >= REALTIME_PROCESS_STATUS_SEND_INTERVAL_SEC / chunk_sec:
                self.realtime_process_status_send_counter = 0
                start_time = time.time()
                (output, monitor) = self._convert_chunk(waveform)
                end_time = time.time()
                elapsed_time = round(end_time - start_time, 3)
                input_size = len(waveform)
                in_qsize = (
                    self.convert_chunk_bulk_queue_in.qsize() if hasattr(self, "convert_chunk_bulk_queue_in") else 0
                )
                chunk_sz = self.chunk_size if hasattr(self, "chunk_size") and self.chunk_size > 0 else input_size
                rest_len = len(self.waveform_rest) if hasattr(self, "waveform_rest") else 0
                input_buffer_size = rest_len + in_qsize * chunk_sz

                performance_data = PerformanceData(
                    inputBufferSize=input_buffer_size,
                    elapsedTime=elapsed_time,
                )

                self.emit("status", "realtime_process_status", performance_data.model_dump(by_alias=True))

                return (output, monitor)

            (output, monitor) = self._convert_chunk(waveform)
            return (output, monitor)

        (output, monitor) = self._convert_chunk(waveform)
        return (output, monitor)

    def _convert_chunk(self, waveform: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
        """Convert waveform.

        Args:
            waveform (np.ndarray): waveform data. int16 or float32. shape: (n,)

        Returns:
            np.ndarray: converted waveform. int16 or float32. shape: (n,)
            np.ndarray: converted waveform for monitor. int16 or float32. shape: (n,)
        """
        snap = getattr(self, "_active_snapshot", None)
        if snap is not None:
            pass_through = snap.pass_through
            enable_high_pass_filter = snap.enable_high_pass_filter
            enable_low_pass_filter = snap.enable_low_pass_filter
        else:
            conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
            pass_through = conf.pass_through
            enable_high_pass_filter = conf.enable_high_pass_filter
            enable_low_pass_filter = conf.enable_low_pass_filter

        if pass_through is True or getattr(self, "vc_pipeline", None) is None:
            waveform_out = self._exec_resample_pass_through_in_out(waveform)
            if self.vc_info.recording_start_flag is True:
                self.output_record.append(waveform_out / 32768 if waveform.dtype == np.int16 else waveform_out)
            if self.vc_info.monitor_enabled is True:
                waveform_monitor = self._exec_resample_pass_through_in_monitor(waveform)
                return (waveform_out, waveform_monitor)
            return (waveform_out, None)

        pipeline = self._require_pipeline()
        vc_chunk_sec = pipeline.get_chunk_sec()
        vc_input_bitdepth = pipeline.get_input_bitdepth()
        vc_output_bitdepth = pipeline.get_output_bitdepth()
        vc_needs_crossfade = pipeline.needs_crossfade()

        input_size = int(self.vc_info.vc_input_sample_rate * vc_chunk_sec)
        output_size = int(self.vc_info.vc_output_sample_rate * vc_chunk_sec)

        input_data_type = waveform.dtype
        if vc_input_bitdepth == np.int16 and waveform.dtype != np.int16:
            waveform = (waveform * 32768).astype(np.int16)
        elif vc_input_bitdepth == np.float32 and waveform.dtype != np.float32:
            waveform = (waveform / 32768).astype(np.float32)

        coeffs = getattr(self, "_filter_coeffs", None)
        try:
            if snap is not None and coeffs is not None:
                bh, ah, bl, al, bb, ab = coeffs
                if enable_high_pass_filter is True and enable_low_pass_filter is True:
                    filtered_waveform = signal.filtfilt(bb, ab, waveform)
                elif enable_high_pass_filter is True:
                    filtered_waveform = signal.filtfilt(bh, ah, waveform)
                elif enable_low_pass_filter is True:
                    filtered_waveform = signal.filtfilt(bl, al, waveform)
                else:
                    filtered_waveform = waveform
            elif enable_high_pass_filter is True and enable_low_pass_filter is True:
                filtered_waveform = self._exec_filter_in_band_pass(waveform)
            elif enable_high_pass_filter is True:
                filtered_waveform = self._exec_filter_in_high_pass(waveform)
            elif enable_low_pass_filter is True:
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

        if hasattr(self, "vc_info") and self.vc_info.vc_output_sample_rate > 0 and output_size > 0:
            actual_chunk_sec = output_size / self.vc_info.vc_output_sample_rate
        else:
            actual_chunk_sec = vc_chunk_sec

        real_crossfade_sec = min(CROSSFADE_SEC, actual_chunk_sec)
        converted_waveform = pipeline.run(resampled_waveform, real_crossfade_sec=real_crossfade_sec)
        if vc_needs_crossfade is True:
            crossfade_frame = int(round(real_crossfade_sec * self.vc_info.vc_output_sample_rate))
            sola_search_frame = int(round(SOLA_SEARCH_FRAME_SEC * self.vc_info.vc_output_sample_rate))
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

        return (resampled_waveform_out, resampled_waveform_monitor)

    def __del__(self) -> None:
        logger.info("VoiceChanger is deleting.")
        if self.vc_info.bulk_process_start_flag is True:
            logger.info("bulk_process is stopping.")
            self.stop_convert_chunk_bulk()
        logger.info("VoiceChanger is deleted.")
