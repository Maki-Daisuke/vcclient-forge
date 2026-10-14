from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..voice_chanager_const import EmbedderType, InferencerType, PitchEstimatorType, VoiceChangerType


class EmbedderInfo(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    embedder_type: EmbedderType
    model_file: Path
    device_id: int
    candidate_onnx_providers: list[str] | None = None
    candidate_onnx_provider_options: Any = None
    onnx_providers: list[str] | None = None
    onnx_provider_options: Any | None = None


class PitchEstimatorInfo(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    pitch_estimator_type: PitchEstimatorType
    model_file: Path | None = None
    device_id: int
    candidate_onnx_providers: list[str] | None = None
    candidate_onnx_provider_options: Any = None
    onnx_providers: list[str] | None = None
    onnx_provider_options: Any | None = None


class RVCInferencerInfo(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    inferencer_type: InferencerType
    model_file: Path
    device_id: int
    candidate_onnx_providers: list[str] | None = None
    candidate_onnx_provider_options: Any = None
    onnx_providers: list[str] | None = None
    onnx_provider_options: Any | None = None


class PipelineInfo(BaseModel):
    slot_index: int = -1

    input_sample_rate: int = -1

    output_sample_rate: int = -1

    chunk_sec: float = 0.1

    slot_info: Any = None


class RVCPipelineInfo(PipelineInfo):
    embedder_info: EmbedderInfo
    pitch_estimator_info: PitchEstimatorInfo
    inferencer_info: RVCInferencerInfo


PipelineInfoMember = PipelineInfo | RVCPipelineInfo


class VoiceChangerInformation(BaseModel):
    slot_index: int = -1

    pitch_estimator_type: PitchEstimatorType | None = None

    gpu_device_index: int = -1

    input_sample_rate: int = -1

    output_sample_rate: int = -1

    monitor_sample_rate: int = -1

    vc_input_sample_rate: int = -1

    vc_output_sample_rate: int = -1

    resample_ratio_in: float = 1

    resample_ratio_out: float = 1

    resample_ratio_monitor: float = 1

    resample_ratio_pass_through_in_out: float = 1

    resample_ratio_pass_through_in_monitor: float = 1

    enable_high_pass_filter: bool = False

    high_pass_filter_cutoff: float = -1

    enable_low_pass_filter: bool = False

    low_pass_filter_cutoff: float = -1

    chunk_sec: float = 0.1

    pipeline_info: PipelineInfoMember | None = None

    voice_changer_type: VoiceChangerType | None = None

    bulk_process_start_flag: bool = False

    recording_start_flag: bool = False

    monitor_enabled: bool = False


class VoiceChangerManagerInfo(BaseModel):
    local_voice_changer_interface_active: bool
    voice_changer_information: VoiceChangerInformation
