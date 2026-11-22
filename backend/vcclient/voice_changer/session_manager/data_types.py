from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from vcclient.server.api_common import ApiErrorResponse

from ..voice_changer_const import PitchEstimatorType, VoiceChangerInputMode

SessionStatus: TypeAlias = Literal["stopped", "starting", "running"]

LOCKED_SESSION_FIELDS: tuple[str, ...] = (
    "model_id",
    "chunk_sec",
    "pitch_estimator",
    "extra_frame_sec",
    "compute_device_id",
    "input_mode",
    "audio_input_device_index",
    "audio_output_device_index",
    "audio_monitor_device_index",
    "audio_input_device_sample_rate",
    "audio_output_device_sample_rate",
    "audio_monitor_device_sample_rate",
    "wasapi_exclusive_enabled",
)


class SessionSnapshot(BaseModel):
    """Self-contained immutable runtime configuration snapshot for a conversion session."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    model_id: str
    pitch_shift: int = 0
    index_ratio: float = 0.0
    chunk_sec: float = 0.5
    pitch_estimator: PitchEstimatorType = "rmvpe"
    extra_frame_sec: float = 0.5
    compute_device_id: int = Field(
        default=0,
        validation_alias=AliasChoices("compute_device_id", "gpu_device_id_int"),
    )
    input_mode: VoiceChangerInputMode = Field(
        default="client",
        validation_alias=AliasChoices("input_mode", "voice_changer_input_mode"),
    )
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
    pass_through: bool = False
    recording: bool = Field(
        default=False,
        validation_alias=AliasChoices("recording", "recording_started"),
    )
    enable_performance_monitor: bool = True
    realtime_process_status_enabled: bool = True
    realtime_output_status_enabled: bool = True


class SessionState(BaseModel):
    """Canonical lifecycle state returned by GET / PUT / DELETE /api/session."""

    status: SessionStatus = "stopped"
    snapshot: SessionSnapshot | None = None
    locked_fields: list[str] = Field(default_factory=lambda: list(LOCKED_SESSION_FIELDS))
    input_sample_rate: int | None = None
    output_sample_rate: int | None = None
    monitor_sample_rate: int | None = None
    last_error: ApiErrorResponse | None = None
