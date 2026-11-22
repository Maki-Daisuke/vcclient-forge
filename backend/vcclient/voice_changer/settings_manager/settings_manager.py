from __future__ import annotations

import json
import math
import threading
import uuid
from pathlib import Path

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from vcclient.device import get_device_catalog
from vcclient.server.api_common import DomainApiError, compute_etag, verify_if_match

from .. import voice_changer_const
from ..voice_changer_const import VoiceChangerInputMode


class UserSettings(BaseModel):
    """Persisted user default settings managed purely without runtime side effects."""

    model_config = ConfigDict(populate_by_name=True)

    model_id: str | None = None
    input_mode: VoiceChangerInputMode = Field(
        default="client",
        validation_alias=AliasChoices("input_mode", "voice_changer_input_mode"),
    )
    compute_device_id: int = Field(
        default=0,
        validation_alias=AliasChoices("compute_device_id", "gpu_device_id_int"),
    )
    extra_frame_sec: float = 0.5
    audio_input_device_index: int = -1
    audio_output_device_index: int = -1
    audio_monitor_device_index: int = -1
    audio_input_device_sample_rate: int = -1
    audio_output_device_sample_rate: int = -1
    audio_monitor_device_sample_rate: int = -1
    wasapi_exclusive_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("wasapi_exclusive_enabled", "wasapi_exclude_emabled", "wasapi_exclusive"),
    )
    input_gain: float = Field(
        default=2.0,
        validation_alias=AliasChoices("input_gain", "audio_input_device_gain"),
    )
    output_gain: float = Field(
        default=1.0,
        validation_alias=AliasChoices("output_gain", "audio_output_device_gain"),
    )
    enable_high_pass_filter: bool = True
    high_pass_filter_cutoff: float = 100.0
    enable_low_pass_filter: bool = True
    low_pass_filter_cutoff: float = 12000.0
    noise_gate: float = -35.0
    enable_performance_monitor: bool = True
    realtime_process_status_enabled: bool = True
    realtime_output_status_enabled: bool = True


def _validate_finite_range(name: str, value: float, low: float, high: float) -> None:
    if not math.isfinite(value) or not (low <= value <= high):
        raise DomainApiError(422, "validation_error", f"{name} must be between {low} and {high}.")


def validate_user_settings(settings: UserSettings) -> None:
    """Validate domain constraints for UserSettings before persisting."""
    catalog = get_device_catalog()
    if not (0 <= settings.compute_device_id < len(catalog)):
        raise DomainApiError(
            422,
            "invalid_compute_device",
            f"Compute device ID {settings.compute_device_id} does not exist in catalog.",
            {"compute_device_id": settings.compute_device_id},
        )

    _validate_finite_range("extra_frame_sec", settings.extra_frame_sec, 0.01, 2.0)
    if not math.isfinite(settings.input_gain) or settings.input_gain < 0.0:
        raise DomainApiError(422, "validation_error", "input_gain must be non-negative.")
    if not math.isfinite(settings.output_gain) or settings.output_gain < 0.0:
        raise DomainApiError(422, "validation_error", "output_gain must be non-negative.")
    _validate_finite_range("noise_gate", settings.noise_gate, -100.0, 0.0)

    if not math.isfinite(settings.high_pass_filter_cutoff) or not (1.0 <= settings.high_pass_filter_cutoff <= 24000.0):
        raise DomainApiError(
            422,
            "invalid_filter_cutoff",
            "high_pass_filter_cutoff must be between 1 and 24000 Hz.",
            {"field": "high_pass_filter_cutoff"},
        )
    if not math.isfinite(settings.low_pass_filter_cutoff) or not (1.0 <= settings.low_pass_filter_cutoff <= 24000.0):
        raise DomainApiError(
            422,
            "invalid_filter_cutoff",
            "low_pass_filter_cutoff must be between 1 and 24000 Hz.",
            {"field": "low_pass_filter_cutoff"},
        )
    if settings.high_pass_filter_cutoff >= settings.low_pass_filter_cutoff:
        raise DomainApiError(
            422,
            "invalid_filter_cutoff",
            "high_pass_filter_cutoff must be strictly less than low_pass_filter_cutoff.",
        )

    if settings.audio_input_device_sample_rate > 0:
        nyquist = settings.audio_input_device_sample_rate / 2.0
        if settings.enable_high_pass_filter and settings.high_pass_filter_cutoff >= nyquist:
            raise DomainApiError(
                422,
                "invalid_filter_cutoff",
                f"high_pass_filter_cutoff must be below Nyquist frequency ({nyquist} Hz).",
                {"field": "high_pass_filter_cutoff", "nyquist": nyquist},
            )
        if settings.enable_low_pass_filter and settings.low_pass_filter_cutoff >= nyquist:
            raise DomainApiError(
                422,
                "invalid_filter_cutoff",
                f"low_pass_filter_cutoff must be below Nyquist frequency ({nyquist} Hz).",
                {"field": "low_pass_filter_cutoff", "nyquist": nyquist},
            )


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)


_lock = threading.RLock()


def _config_path() -> Path:
    return Path(voice_changer_const.ConfigFile)


def _read_settings_locked() -> UserSettings:
    config_path = _config_path()
    if not config_path.exists():
        return UserSettings()
    settings = UserSettings.model_validate_json(config_path.read_text(encoding="utf-8"))
    catalog = get_device_catalog()
    if not (0 <= settings.compute_device_id < len(catalog)):
        settings.compute_device_id = 0
    return settings


def get_settings() -> tuple[UserSettings, str]:
    """Load persisted UserSettings and its ETag without mutating runtime audio state."""
    with _lock:
        settings = _read_settings_locked()
        return settings, compute_etag(settings.model_dump())


def update_settings(
    new_settings: UserSettings,
    *,
    if_match: str | None = None,
) -> tuple[UserSettings, str]:
    """Validate and persist UserSettings atomically without triggering pipeline rebuilds."""
    with _lock:
        current = _read_settings_locked()
        verify_if_match(if_match, compute_etag(current.model_dump()))
        validate_user_settings(new_settings)
        _atomic_write_text(_config_path(), new_settings.model_dump_json(indent=4))
        return new_settings, compute_etag(new_settings.model_dump())


def clear_model_id_if_matches(model_id: str) -> None:
    """Clear persisted model_id when a model directory is deleted."""
    with _lock:
        config_path = _config_path()
        if not config_path.exists():
            return
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("model_id") == model_id:
            raw["model_id"] = None
            if "current_slot_index" in raw:
                raw["current_slot_index"] = -1
            _atomic_write_text(config_path, json.dumps(raw, indent=4))
