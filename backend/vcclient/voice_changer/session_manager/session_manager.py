from __future__ import annotations

import gc
import math
import threading
import weakref
from typing import Any

from vcclient.device import DeviceConfig, get_device_catalog
from vcclient.exception import VCClientError
from vcclient.logger import logger
from vcclient.server.api_common import ApiErrorResponse, DomainApiError, compute_etag, verify_if_match

from ..audio_device_manager import (
    check_available_sample_rate,
    get_audio_input_device,
    get_audio_output_device,
    get_default_sample_rate,
)
from ..data_types.slot_manager_data_types import RVCSlotInfo
from ..model_catalog import get_slot_info_by_model_id
from ..voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from ..voice_change_manager.vc_pipelines.pipeline_manager import PipelineManager
from ..voice_change_manager.vc_pipelines.vc_pipeline import VCPipeline
from ..voice_change_manager.voice_changer import VoiceChanger
from ..voice_changer_const import AudioDeviceType
from .data_types import LOCKED_SESSION_FIELDS, SessionSnapshot, SessionState, SessionStatus

_lock = threading.RLock()
_status: SessionStatus = "stopped"
_active_snapshot: SessionSnapshot | None = None
_input_sample_rate: int | None = None
_output_sample_rate: int | None = None
_monitor_sample_rate: int | None = None
_last_error: ApiErrorResponse | None = None
_generation: int = 0
_startup_thread: threading.Thread | None = None
_ws_hub: Any = None
_pipeline_cache_key: tuple[Any, ...] | None = None
_pipeline_cache_ref: weakref.ref[VCPipeline] | None = None


def set_websocket_hub(hub: Any) -> None:
    """Register WebSocketHub so DELETE /api/session can cleanly close active audio sockets."""
    global _ws_hub
    _ws_hub = hub


def get_active_snapshot() -> SessionSnapshot | None:
    """Return the immutable active SessionSnapshot without acquiring locks on the audio thread."""
    return _active_snapshot


def is_session_starting_or_running() -> bool:
    with _lock:
        return _status in ("starting", "running")


def is_client_session_running() -> bool:
    with _lock:
        return _status == "running" and _active_snapshot is not None and _active_snapshot.input_mode == "client"


def get_active_session_model_id() -> str | None:
    with _lock:
        if _status in ("starting", "running") and _active_snapshot is not None:
            return _active_snapshot.model_id
        return None


def get_starting_session_model_id() -> str | None:
    with _lock:
        if _status == "starting" and _active_snapshot is not None:
            return _active_snapshot.model_id
        return None


def is_session_recording_active() -> bool:
    with _lock:
        if _status in ("starting", "running") and _active_snapshot is not None and _active_snapshot.recording:
            return True
    vc = VoiceChanger.peek_instance()
    return vc is not None and vc.vc_info.recording_start_flag


def _build_state_locked() -> SessionState:
    return SessionState(
        status=_status,
        snapshot=_active_snapshot,
        locked_fields=list(LOCKED_SESSION_FIELDS),
        input_sample_rate=_input_sample_rate,
        output_sample_rate=_output_sample_rate,
        monitor_sample_rate=_monitor_sample_rate,
        last_error=_last_error,
    )


def _validate_live_scalars(snapshot: SessionSnapshot, input_sr: int | None) -> None:
    if not (-24 <= snapshot.pitch_shift <= 24):
        raise DomainApiError(
            422,
            "validation_error",
            "pitch_shift must be between -24 and 24.",
            {"field": "pitch_shift"},
        )
    if not math.isfinite(snapshot.index_ratio) or not (0.0 <= snapshot.index_ratio <= 1.0):
        raise DomainApiError(
            422,
            "validation_error",
            "index_ratio must be between 0.0 and 1.0.",
            {"field": "index_ratio"},
        )
    if not math.isfinite(snapshot.input_gain) or snapshot.input_gain < 0.0:
        raise DomainApiError(
            422,
            "validation_error",
            "input_gain must be non-negative.",
            {"field": "input_gain"},
        )
    if not math.isfinite(snapshot.output_gain) or snapshot.output_gain < 0.0:
        raise DomainApiError(
            422,
            "validation_error",
            "output_gain must be non-negative.",
            {"field": "output_gain"},
        )
    if not math.isfinite(snapshot.noise_gate) or not (-100.0 <= snapshot.noise_gate <= 0.0):
        raise DomainApiError(
            422,
            "validation_error",
            "noise_gate must be between -100.0 and 0.0.",
            {"field": "noise_gate"},
        )
    if not math.isfinite(snapshot.high_pass_filter_cutoff) or not (1.0 <= snapshot.high_pass_filter_cutoff <= 24000.0):
        raise DomainApiError(
            422,
            "invalid_filter_cutoff",
            "high_pass_filter_cutoff must be between 1 and 24000 Hz.",
            {"field": "high_pass_filter_cutoff"},
        )
    if not math.isfinite(snapshot.low_pass_filter_cutoff) or not (1.0 <= snapshot.low_pass_filter_cutoff <= 24000.0):
        raise DomainApiError(
            422,
            "invalid_filter_cutoff",
            "low_pass_filter_cutoff must be between 1 and 24000 Hz.",
            {"field": "low_pass_filter_cutoff"},
        )
    if snapshot.high_pass_filter_cutoff >= snapshot.low_pass_filter_cutoff:
        raise DomainApiError(
            422,
            "invalid_filter_cutoff",
            "high_pass_filter_cutoff must be strictly less than low_pass_filter_cutoff.",
        )
    if input_sr is not None and input_sr > 0:
        nyquist = input_sr / 2.0
        if snapshot.enable_high_pass_filter and snapshot.high_pass_filter_cutoff >= nyquist:
            raise DomainApiError(
                422,
                "invalid_filter_cutoff",
                f"high_pass_filter_cutoff must be below Nyquist frequency ({nyquist} Hz).",
                {"field": "high_pass_filter_cutoff", "nyquist": nyquist},
            )
        if snapshot.enable_low_pass_filter and snapshot.low_pass_filter_cutoff >= nyquist:
            raise DomainApiError(
                422,
                "invalid_filter_cutoff",
                f"low_pass_filter_cutoff must be below Nyquist frequency ({nyquist} Hz).",
                {"field": "low_pass_filter_cutoff", "nyquist": nyquist},
            )


def _resolve_device_sample_rate(device_index: int, kind: AudioDeviceType, requested: int, role: str) -> int:
    if requested > 0:
        if not check_available_sample_rate(device_index, requested, kind):
            raise DomainApiError(
                422,
                "invalid_audio_device",
                f"Requested {role} sample rate {requested} Hz is not supported by device {device_index}.",
                {"role": role, "device_index": device_index, "sample_rate": requested},
            )
        return requested
    if requested != -1:
        raise DomainApiError(
            422,
            "invalid_audio_device",
            f"Invalid {role} sample rate {requested}; specify a positive rate or -1 for default.",
            {"role": role, "device_index": device_index, "sample_rate": requested},
        )
    resolved = round(get_default_sample_rate(device_index, kind))
    if resolved <= 0:
        raise DomainApiError(
            422,
            "invalid_audio_device",
            f"Failed to determine default sample rate for {role} device {device_index}.",
            {"role": role, "device_index": device_index},
        )
    return resolved


def validate_session_snapshot(snapshot: SessionSnapshot) -> tuple[RVCSlotInfo, int, int, int | None]:
    """Validate snapshot references, compute/audio devices, rates, and DSP cutoffs before startup."""
    slot_info = get_slot_info_by_model_id(snapshot.model_id)
    if slot_info is None:
        raise DomainApiError(
            404,
            "model_not_found",
            f"Model '{snapshot.model_id}' not found.",
            {"model_id": snapshot.model_id},
        )

    if not math.isfinite(snapshot.chunk_sec) or not (0.05 <= snapshot.chunk_sec <= 5.0):
        raise DomainApiError(
            422,
            "validation_error",
            "chunk_sec must be between 0.05 and 5.0.",
            {"field": "chunk_sec"},
        )

    catalog = get_device_catalog()
    if not (0 <= snapshot.compute_device_id < len(catalog)):
        raise DomainApiError(
            422,
            "invalid_compute_device",
            f"Compute device ID {snapshot.compute_device_id} does not exist in catalog.",
            {"compute_device_id": snapshot.compute_device_id},
        )

    if not math.isfinite(snapshot.extra_frame_sec) or not (0.01 <= snapshot.extra_frame_sec <= 2.0):
        raise DomainApiError(
            422,
            "validation_error",
            "extra_frame_sec must be between 0.01 and 2.0.",
            {"field": "extra_frame_sec"},
        )

    if snapshot.input_mode == "server":
        if snapshot.audio_input_device_index < 0 or get_audio_input_device(snapshot.audio_input_device_index) is None:
            raise DomainApiError(
                422,
                "invalid_audio_device",
                f"Audio input device {snapshot.audio_input_device_index} is invalid or unavailable.",
                {"role": "input", "device_index": snapshot.audio_input_device_index},
            )
        if (
            snapshot.audio_output_device_index < 0
            or get_audio_output_device(snapshot.audio_output_device_index) is None
        ):
            raise DomainApiError(
                422,
                "invalid_audio_device",
                f"Audio output device {snapshot.audio_output_device_index} is invalid or unavailable.",
                {"role": "output", "device_index": snapshot.audio_output_device_index},
            )
        input_sr = _resolve_device_sample_rate(
            snapshot.audio_input_device_index,
            "audioinput",
            snapshot.audio_input_device_sample_rate,
            "input",
        )
        output_sr = _resolve_device_sample_rate(
            snapshot.audio_output_device_index,
            "audiooutput",
            snapshot.audio_output_device_sample_rate,
            "output",
        )
        monitor_sr: int | None = None
        if snapshot.audio_monitor_device_index != -1:
            if (
                snapshot.audio_monitor_device_index < 0
                or get_audio_output_device(snapshot.audio_monitor_device_index) is None
            ):
                raise DomainApiError(
                    422,
                    "invalid_audio_device",
                    f"Audio monitor device {snapshot.audio_monitor_device_index} is invalid or unavailable.",
                    {"role": "monitor", "device_index": snapshot.audio_monitor_device_index},
                )
            monitor_sr = _resolve_device_sample_rate(
                snapshot.audio_monitor_device_index,
                "audiooutput",
                snapshot.audio_monitor_device_sample_rate,
                "monitor",
            )
    else:
        if snapshot.audio_input_device_sample_rate != -1 and snapshot.audio_input_device_sample_rate <= 0:
            raise DomainApiError(
                422,
                "invalid_audio_device",
                f"Invalid input sample rate {snapshot.audio_input_device_sample_rate}.",
                {"role": "input", "sample_rate": snapshot.audio_input_device_sample_rate},
            )
        if snapshot.audio_output_device_sample_rate != -1 and snapshot.audio_output_device_sample_rate <= 0:
            raise DomainApiError(
                422,
                "invalid_audio_device",
                f"Invalid output sample rate {snapshot.audio_output_device_sample_rate}.",
                {"role": "output", "sample_rate": snapshot.audio_output_device_sample_rate},
            )
        input_sr = snapshot.audio_input_device_sample_rate if snapshot.audio_input_device_sample_rate > 0 else 48000
        output_sr = snapshot.audio_output_device_sample_rate if snapshot.audio_output_device_sample_rate > 0 else 48000
        monitor_sr = None

    _validate_live_scalars(snapshot, input_sr)
    return (slot_info, input_sr, output_sr, monitor_sr)


def _error_from_exception(exc: Exception) -> ApiErrorResponse:
    if isinstance(exc, DomainApiError):
        return ApiErrorResponse(code=exc.code, message=exc.message, details=exc.details)
    if isinstance(exc, VCClientError):
        return ApiErrorResponse(code="vcclient_error", message=exc.info.reason, details=exc.info.model_dump())
    return ApiErrorResponse(
        code="session_start_failed",
        message=str(exc) or type(exc).__name__,
        details={"error_type": type(exc).__name__},
    )


def _build_pipeline_cache_key(
    snapshot: SessionSnapshot,
    slot_info: RVCSlotInfo,
    device: DeviceConfig,
) -> tuple[Any, ...]:
    """Return a cache key covering all inputs that shape the constructed VCPipeline."""
    return (
        snapshot.model_id,
        slot_info.voice_changer_type,
        str(slot_info.model_file) if slot_info.model_file is not None else None,
        str(slot_info.index_file) if slot_info.index_file is not None else None,
        slot_info.name,
        slot_info.sample_rate,
        slot_info.inferencer_type,
        slot_info.version,
        slot_info.embedder,
        slot_info.is_f0,
        float(snapshot.chunk_sec),
        float(snapshot.extra_frame_sec),
        snapshot.pitch_estimator,
        device.id,
        device.canonical_id,
        device.provider,
        device.device_index,
        tuple(sorted(device.metadata.items())),
    )


def _clear_pipeline_cache_locked() -> None:
    global _pipeline_cache_key, _pipeline_cache_ref
    _pipeline_cache_key = None
    _pipeline_cache_ref = None


def _run_startup(
    gen: int,
    snapshot: SessionSnapshot,
    slot_info: RVCSlotInfo,
    input_sr: int,
    output_sr: int,
    monitor_sr: int | None,
) -> None:
    global _status, _active_snapshot, _input_sample_rate, _output_sample_rate, _monitor_sample_rate, _last_error
    global _pipeline_cache_key, _pipeline_cache_ref

    launch_slot = slot_info.model_copy(
        update={
            "chunk_sec": snapshot.chunk_sec,
            "pitch_estimator": snapshot.pitch_estimator,
            "pitch_shift": snapshot.pitch_shift,
            "index_ratio": snapshot.index_ratio,
        }
    )

    catalog = get_device_catalog()
    pipeline_key: tuple[Any, ...] | None = None
    if 0 <= snapshot.compute_device_id < len(catalog):
        pipeline_key = _build_pipeline_cache_key(snapshot, slot_info, catalog[snapshot.compute_device_id])

    cached_pipeline: VCPipeline | None = None
    release_webgpu_before_rebuild = False
    with _lock:
        if _generation != gen or _status != "starting":
            return
        vc_existing = VoiceChanger.peek_instance()
        if (
            pipeline_key is not None
            and vc_existing is not None
            and vc_existing.vc_pipeline is not None
            and _pipeline_cache_key == pipeline_key
            and _pipeline_cache_ref is not None
            and _pipeline_cache_ref() is vc_existing.vc_pipeline
        ):
            cached_pipeline = vc_existing.vc_pipeline
        elif (
            vc_existing is not None
            and vc_existing.vc_pipeline is not None
            and getattr(getattr(vc_existing.vc_pipeline, "device", None), "provider", None) == "webgpu"
        ):
            # Release any active WebGPU pipeline before creating a replacement because WebGpuContext
            # is a per-process singleton tied to live sessions.
            vc_existing.vc_pipeline = None
            _clear_pipeline_cache_locked()
            release_webgpu_before_rebuild = True
    if release_webgpu_before_rebuild:
        gc.collect()

    try:
        if cached_pipeline is not None:
            logger.info(
                "Reusing existing VC pipeline for model '%s' on compute device %s.",
                snapshot.model_id,
                snapshot.compute_device_id,
            )
            cached_pipeline.reset_buffers()
            pipeline = cached_pipeline
        else:
            pipeline = PipelineManager.get_pipeline(
                launch_slot,
                device=snapshot.compute_device_id,
                extra_frame_sec=snapshot.extra_frame_sec,
                snapshot_getter=get_active_snapshot,
            )
    except Exception as exc:
        logger.error("Session startup failed during pipeline creation: %s", exc, exc_info=True)
        with _lock:
            if _generation == gen and _status == "starting":
                vc_existing = VoiceChanger.peek_instance()
                if vc_existing is not None:
                    vc_existing.clear_session_snapshot()
                    vc_existing.vc_pipeline = None
                _clear_pipeline_cache_locked()
                _status = "stopped"
                _active_snapshot = None
                _input_sample_rate = None
                _output_sample_rate = None
                _monitor_sample_rate = None
                _last_error = _error_from_exception(exc)
        return

    with _lock:
        if _generation != gen or _status != "starting":
            return

        vc = VoiceChanger.get_or_create_raw()
        native_started = False
        bulk_started = False
        try:
            vc.configure_for_session(
                snapshot,
                pipeline,
                input_sample_rate=input_sr,
                output_sample_rate=output_sr,
                monitor_sample_rate=monitor_sr,
            )
            if snapshot.recording:
                vc.start_recording()
            vc.start_convert_chunk_bulk()
            bulk_started = True
            if snapshot.input_mode == "server":
                local = LocalVoiceChangerInterface.get_instance()
                local.vc = vc
                local.start()
                native_started = True
        except Exception as exc:
            logger.error("Session startup failed while launching workers: %s", exc, exc_info=True)
            if native_started:
                try:
                    LocalVoiceChangerInterface.get_instance().stop()
                except Exception:
                    pass
            if bulk_started:
                try:
                    vc.stop_convert_chunk_bulk()
                except Exception:
                    pass
            vc.vc_info.recording_start_flag = False
            vc.output_record = []
            vc.clear_session_snapshot()
            vc.vc_pipeline = None
            _clear_pipeline_cache_locked()
            vc.vc_info.model_id = None
            vc.vc_info.slot_index = -1
            vc.vc_info.pipeline_info = None
            _status = "stopped"
            _active_snapshot = None
            _input_sample_rate = None
            _output_sample_rate = None
            _monitor_sample_rate = None
            _last_error = _error_from_exception(exc)
            return

        _pipeline_cache_key = pipeline_key
        _pipeline_cache_ref = weakref.ref(pipeline)

        if snapshot.input_mode == "server":
            # The main audio loop reports readiness once all streams are open.
            return

        _status = "running"
        _active_snapshot = snapshot
        _input_sample_rate = input_sr
        _output_sample_rate = output_sr
        _monitor_sample_rate = monitor_sr if snapshot.input_mode == "server" else None
        _last_error = None


def notify_audio_started() -> None:
    """Publish server readiness after the input, output and monitor streams open."""
    global _status, _input_sample_rate, _output_sample_rate, _monitor_sample_rate, _last_error
    with _lock:
        if _status != "starting" or _active_snapshot is None or _active_snapshot.input_mode != "server":
            return
        vc = VoiceChanger.peek_instance()
        if vc is None:
            return
        _input_sample_rate = vc.vc_info.input_sample_rate
        _output_sample_rate = vc.vc_info.output_sample_rate
        _monitor_sample_rate = vc.vc_info.monitor_sample_rate if vc.vc_info.monitor_enabled else None
        _last_error = None
        _status = "running"


def report_audio_failure(exc: Exception) -> None:
    """Expose server audio failures through the session resource."""
    global _status, _active_snapshot, _input_sample_rate, _output_sample_rate, _monitor_sample_rate, _last_error
    with _lock:
        if (
            _status not in ("starting", "running")
            or _active_snapshot is None
            or _active_snapshot.input_mode != "server"
        ):
            return
        vc = VoiceChanger.peek_instance()
        if vc is not None:
            if vc.vc_info.recording_start_flag:
                if _status == "running":
                    vc.stop_recording()
                else:
                    vc.vc_info.recording_start_flag = False
                    vc.output_record = []
            vc.clear_session_snapshot()
            vc.vc_pipeline = None
            _clear_pipeline_cache_locked()
            vc.vc_info.model_id = None
            vc.vc_info.slot_index = -1
            vc.vc_info.pipeline_info = None
        _status = "stopped"
        _active_snapshot = None
        _input_sample_rate = None
        _output_sample_rate = None
        _monitor_sample_rate = None
        _last_error = _error_from_exception(exc)


def get_session_state() -> tuple[SessionState, str]:
    """Return current SessionState and ETag without modifying pipelines or audio."""
    with _lock:
        state = _build_state_locked()
        return (state, compute_etag(state.model_dump()))


def put_session(
    snapshot: SessionSnapshot,
    *,
    if_match: str | None = None,
) -> tuple[SessionState, str, int]:
    """Start a session from stopped (202) or atomically apply live updates while running (200)."""
    global _status, _active_snapshot, _input_sample_rate, _output_sample_rate, _monitor_sample_rate
    global _last_error, _generation, _startup_thread

    with _lock:
        current_state = _build_state_locked()
        verify_if_match(if_match, compute_etag(current_state.model_dump()))

        if _status == "starting":
            raise DomainApiError(
                409,
                "session_starting",
                "Session startup is in progress; wait for startup to complete.",
            )

        if _status == "stopped":
            slot_info, input_sr, output_sr, monitor_sr = validate_session_snapshot(snapshot)
            _generation += 1
            gen = _generation
            _status = "starting"
            _active_snapshot = snapshot
            _input_sample_rate = None
            _output_sample_rate = None
            _monitor_sample_rate = None
            _last_error = None

            state = _build_state_locked()
            etag = compute_etag(state.model_dump())
            worker = threading.Thread(
                target=_run_startup,
                args=(gen, snapshot, slot_info, input_sr, output_sr, monitor_sr),
                daemon=True,
                name=f"session-startup-{gen}",
            )
            _startup_thread = worker
            worker.start()
            return (state, etag, 202)

        assert _active_snapshot is not None
        conflicting = [
            field for field in LOCKED_SESSION_FIELDS if getattr(snapshot, field) != getattr(_active_snapshot, field)
        ]
        if conflicting:
            raise DomainApiError(
                409,
                "session_rebuild_required",
                "Session must be stopped before changing rebuild-required fields.",
                {"conflicting_fields": conflicting},
            )

        _validate_live_scalars(snapshot, _input_sample_rate)
        vc = VoiceChanger.get_or_create_raw()
        _active_snapshot = snapshot
        vc.apply_live_snapshot(snapshot)
        state = _build_state_locked()
        return (state, compute_etag(state.model_dump()), 200)


def delete_session(*, if_match: str | None = None) -> tuple[SessionState, str]:
    """Stop an active session and finalize any active recording cleanly."""
    global _status, _active_snapshot, _input_sample_rate, _output_sample_rate, _monitor_sample_rate, _generation

    with _lock:
        current_state = _build_state_locked()
        verify_if_match(if_match, compute_etag(current_state.model_dump()))

        if _status == "starting":
            raise DomainApiError(
                409,
                "session_starting",
                "Cannot stop session while startup is in progress.",
            )

        if _status == "stopped":
            return (current_state, compute_etag(current_state.model_dump()))

        if _ws_hub is not None:
            _ws_hub.close_audio_clients(code=1000, reason="")

        vc = VoiceChanger.peek_instance()
        local = LocalVoiceChangerInterface._instance
        if local is not None:
            local.stop()
        elif vc is not None:
            vc.stop_convert_chunk_bulk()

        if vc is not None:
            if vc.vc_info.recording_start_flag:
                vc.stop_recording()
            vc.clear_session_snapshot()

        _generation += 1
        _status = "stopped"
        _active_snapshot = None
        _input_sample_rate = None
        _output_sample_rate = None
        _monitor_sample_rate = None
        state = _build_state_locked()
        return (state, compute_etag(state.model_dump()))


def reset_session_state() -> None:
    """Reset session state cleanly for test isolation."""
    global _status, _active_snapshot, _input_sample_rate, _output_sample_rate, _monitor_sample_rate
    global _last_error, _generation, _startup_thread

    thread: threading.Thread | None
    with _lock:
        _generation += 1
        thread = _startup_thread
        _startup_thread = None
        _status = "stopped"
        _active_snapshot = None
        _input_sample_rate = None
        _output_sample_rate = None
        _monitor_sample_rate = None
        _last_error = None
        _clear_pipeline_cache_locked()

    if thread is not None and thread.is_alive():
        thread.join(timeout=2.0)

    vc = VoiceChanger.peek_instance()
    if vc is not None:
        vc.stop_convert_chunk_bulk()
        vc.vc_info.recording_start_flag = False
        vc.output_record = []
        vc.clear_session_snapshot()
