from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..voice_changer_const import AudioDeviceType, ExtraSec, InferencerType, VoiceChangerInputMode, VoiceChangerType


class PerformanceData(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    input_buffer_size: float = Field(default=0, alias="inputBufferSize")
    input_size: float = Field(default=0, alias="inputSize")
    input_sec: float = Field(default=0, alias="inputSec")
    output_size: float = Field(default=0, alias="outputSize")
    output_sec: float = Field(default=0, alias="outputSec")
    elapsed_time: float = Field(default=0, alias="elapsedTime")
    input_volume_db: float = 0
    output_volume_db: float = 0
    data_num: int = Field(default=0, alias="dataNum")

    @property
    def inputBufferSize(self) -> float:
        return self.input_buffer_size

    @inputBufferSize.setter
    def inputBufferSize(self, val: float) -> None:
        self.input_buffer_size = val

    @property
    def inputSize(self) -> float:
        return self.input_size

    @inputSize.setter
    def inputSize(self, val: float) -> None:
        self.input_size = val

    @property
    def inputSec(self) -> float:
        return self.input_sec

    @inputSec.setter
    def inputSec(self, val: float) -> None:
        self.input_sec = val

    @property
    def outputSize(self) -> float:
        return self.output_size

    @outputSize.setter
    def outputSize(self, val: float) -> None:
        self.output_size = val

    @property
    def outputSec(self) -> float:
        return self.output_sec

    @outputSec.setter
    def outputSec(self, val: float) -> None:
        self.output_sec = val

    @property
    def elapsedTime(self) -> float:
        return self.elapsed_time

    @elapsedTime.setter
    def elapsedTime(self, val: float) -> None:
        self.elapsed_time = val

    @property
    def dataNum(self) -> int:
        return self.data_num

    @dataNum.setter
    def dataNum(self, val: int) -> None:
        self.data_num = val


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
    wasapi_exclude_emabled: bool = False
    audio_input_device_sample_rate: int = -1
    audio_output_device_sample_rate: int = -1
    audio_monitor_device_sample_rate: int = -1
    audio_input_device_gain: float = 2
    audio_output_device_gain: float = 1
    audio_monitor_device_gain: float = 1
    server_device_trancate_buffer_ratio: float = 1
    realtime_process_status_enabled: bool = True
    realtime_process_status_send_interval_sec: float = 1.0
    realtime_output_status_enabled: bool = True
    realtime_output_status_send_interval_sec: float = 0.2
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
