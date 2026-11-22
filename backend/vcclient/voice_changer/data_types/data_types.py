from pathlib import Path

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from ..voice_changer_const import AudioDeviceType, InferencerType, VoiceChangerInputMode, VoiceChangerType


class PerformanceData(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    input_buffer_size: float = Field(default=0, alias="inputBufferSize")
    elapsed_time: float = Field(default=0, alias="elapsedTime")


class AudioDevice(BaseModel):
    kind: AudioDeviceType = "audioinput"
    index: int = 0
    name: str = ""
    host_api: str = ""
    max_input_channels: int = 0
    max_output_channels: int = 0
    default_samplerate: int = 0


class VoiceChangerConfiguration(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    current_slot_index: int = 0
    model_id: str | None = None
    voice_changer_input_mode: VoiceChangerInputMode = Field(
        default="client",
        validation_alias=AliasChoices("voice_changer_input_mode", "input_mode"),
    )
    pass_through: bool = False
    recording_started: bool = False
    enable_performance_monitor: bool = True
    enable_high_pass_filter: bool = True
    high_pass_filter_cutoff: float = 100
    enable_low_pass_filter: bool = True
    low_pass_filter_cutoff: float = 12000
    audio_input_device_index: int = -1
    audio_output_device_index: int = -1
    audio_monitor_device_index: int = -1
    wasapi_exclusive_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("wasapi_exclusive_enabled", "wasapi_exclude_emabled", "wasapi_exclusive"),
    )
    audio_input_device_sample_rate: int = -1
    audio_output_device_sample_rate: int = -1
    audio_monitor_device_sample_rate: int = -1
    audio_input_device_gain: float = Field(
        default=2,
        validation_alias=AliasChoices("audio_input_device_gain", "input_gain"),
    )
    audio_output_device_gain: float = Field(
        default=1,
        validation_alias=AliasChoices("audio_output_device_gain", "output_gain"),
    )
    realtime_process_status_enabled: bool = True
    realtime_output_status_enabled: bool = True
    noise_gate: float = -35
    extra_frame_sec: float = 0.5
    gpu_device_id_int: int = Field(
        default=0,
        validation_alias=AliasChoices("gpu_device_id_int", "compute_device_id"),
    )
    input_sample_rate: int = 48000
    output_sample_rate: int = 48000
    monitor_sample_rate: int = 48000


class GPUInfo(BaseModel):
    name: str = ""
    device_id: str = ""
    adapter_ram: int = 0
    device_id_int: int = 0
    cuda_compute_version_major: int = -1
    cuda_compute_version_minor: int = -1


class ModuleInfo(BaseModel):
    id: str
    display_name: str
    url: str
    save_to: Path
    hash: str


class ModuleStatus(BaseModel):
    info: ModuleInfo
    downloaded: bool
    valid: bool


class SampleInfo(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    voice_changer_type: VoiceChangerType
    lang: str
    tag: list[str]
    name: str
    icon_url: str | None = None


class RVCSampleInfo(SampleInfo):
    model_url: str
    index_url: str | None = None
    inferencer_type: InferencerType
    f0: bool
    sample_rate: int
