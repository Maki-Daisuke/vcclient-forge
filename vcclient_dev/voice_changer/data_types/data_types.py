from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..voice_chanager_const import AudioDeviceType, ExtraSec, InferencerType, VoiceChangerInputMode, VoiceChangerType


class PerformanceData(BaseModel):
    input_size: float = 0

    input_sec: float = 0

    output_size: float = 0

    output_sec: float = 0

    elapsed_time: float = 0

    input_volume_db: float = 0

    output_volume_db: float = 0

    data_num: int = 0


class AudioDevice(BaseModel):
    kind: AudioDeviceType = "audioinput"

    index: int = 0

    name: str = ""

    host_api: str = ""

    max_input_channels: int = 0

    max_output_channels: int = 0

    default_samplerate: int = 0

    available_samplerates: list[int] = []


class VoiceChangerConfiguration(BaseModel):
    current_slot_index: int = 0

    voice_changer_input_mode: VoiceChangerInputMode = "client"

    sio_broadcast: bool = False

    pass_through: bool = False

    recording_started: bool = False

    enable_performance_monitor: bool = True

    enable_high_pass_filter: bool = False

    high_pass_filter_cutoff: float = 100

    enable_low_pass_filter: bool = False

    low_pass_filter_cutoff: float = 10000

    volume_tuning_type: str = "sqrt"

    audio_input_device_index: int = -1

    audio_output_device_index: int = -1

    audio_monitor_device_index: int = -1

    wasapi_exclude_emabled: bool = True

    audio_input_device_sample_rate: int = -1

    audio_output_device_sample_rate: int = -1

    audio_monitor_device_sample_rate: int = -1

    audio_input_device_gain: float = 2

    audio_output_device_gain: float = 1

    audio_monitor_device_gain: float = 1

    server_device_trancate_buffer_ratio: float = 1

    noise_gate: float = -100

    extra_frame_sec: float = ExtraSec[0]

    crossfade_sec: float = 0.05

    sola_search_frame_sec: float = 0.012

    gpu_device_id_int: int = -1

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
    terms_of_use_url: str
    icon_url: str | None = None
    credit: str
    description: str


class RVCSampleInfo(SampleInfo):
    model_url: str
    index_url: str | None = None
    inferencer_type: InferencerType
    f0: bool
    sample_rate: int


class BeatriceV2SampleInfo(SampleInfo):
    zip_url: str


SampleInfoMember = SampleInfo | RVCSampleInfo | BeatriceV2SampleInfo
