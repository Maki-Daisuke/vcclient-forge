from pathlib import Path
from typing import Dict

from pydantic import BaseModel, ConfigDict, field_validator

from ..voice_chanager_const import (
    MAX_BEATRICE_MERGED_SPEAKER_WEIGHTS_SLOT,
    EmbedderType,
    InferencerType,
    PitchEstimatorType,
    VoiceChangerType,
)


class ModelImportParam(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    voice_changer_type: VoiceChangerType
    name: str
    terms_of_use_url: str = ""
    slot_index: int | None = None
    icon_file: Path | None = None


class BeatriceV2ModelImportParam(ModelImportParam):
    voice_changer_type: VoiceChangerType = "Beatrice_v2"
    zip_file: Path | None = None


class ReservedForSampleModelImportParam(ModelImportParam):
    voice_changer_type: VoiceChangerType = "RESERVED_FOR_SAMPLE"
    progress: float


class RVCModelImportParam(ModelImportParam):
    voice_changer_type: VoiceChangerType = "RVC"
    model_file: Path
    index_file: Path | None = None
    embedder: EmbedderType | None = None


ModelImportParamMember = (
    ModelImportParam | ReservedForSampleModelImportParam | RVCModelImportParam | BeatriceV2ModelImportParam
)


class ModelSource(BaseModel):
    slot_index: int
    strength: float


class MergeParam(BaseModel):
    files: list[ModelSource]


class OnnxExportParam(BaseModel):
    slot_index: int


class ExportParam(BaseModel):
    slot_index: int


class SlotInfo(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    slot_index: int = -1

    voice_changer_type: VoiceChangerType | None = None

    name: str = ""

    description: str = ""

    credit: str = ""

    terms_of_use_url: str = ""

    icon_file: Path | None = None

    speakers: dict = {}

    def update(self, **kwargs):

        for key, value in kwargs.items():
            if key in self.model_fields:
                setattr(self, key, value)


class RVCSlotInfo(SlotInfo):
    voice_changer_type: VoiceChangerType = "RVC"

    model_file: Path | None = None

    index_file: Path | None = None

    is_onnx: bool = False

    inferencer_type: InferencerType = "onnxRVC"

    sample_rate: int = -1

    is_f0: bool = True

    deprecated: bool = False

    embedder: EmbedderType = "hubert_base_l12"

    pitch_estimator: PitchEstimatorType = "rmvpe"
    sample_id: str | None = None
    version: str = ""
    chunk_sec: float = 0.5
    pitch_shift: int = 0
    index_ratio: float = 0
    protect_ratio: float = 0.5

    @field_validator("pitch_estimator", mode="before")
    @classmethod
    def normalize_pitch_estimator(cls, v: str) -> str:
        if v == "rmvpe_onnx":
            return "rmvpe"
        return v


class ReservedForSampleSlotInfo(SlotInfo):
    voice_changer_type: VoiceChangerType = "RESERVED_FOR_SAMPLE"
    progress: float


class BeatriceV2Model(BaseModel):
    version: str
    name: str
    description: str


class BeatriceV2Portrait(BaseModel):
    path: str
    description: str


class BeatriceV2Voice(BaseModel):
    name: str
    description: str
    average_pitch: float
    portrait: BeatriceV2Portrait


class BeatriceV2ModelInfo(BaseModel):
    model: BeatriceV2Model
    voice: Dict[str, BeatriceV2Voice]


class BeatriceV2SlotInfo(SlotInfo):
    voice_changer_type: VoiceChangerType = "Beatrice_v2"

    toml_file: Path = None

    dst_id: int = 0

    pitch_shift: int = 0

    pitch_shifts: list[int] = []

    formant_shift: float = 0

    waveform_generator_file: Path = []

    chunk_sec: float = 0.1

    use_merged_speaker_embedding: bool = False

    merged_speaker_id: int = 0

    merged_speaker_weights_list: list[list[float]] = [[] for _ in range(MAX_BEATRICE_MERGED_SPEAKER_WEIGHTS_SLOT)]

    merged_speaker_pitch_shifts: list[int] = [0] * MAX_BEATRICE_MERGED_SPEAKER_WEIGHTS_SLOT

    merged_speaker_formant_shifts: list[float] = [0] * MAX_BEATRICE_MERGED_SPEAKER_WEIGHTS_SLOT

    auto_pitch_shift: bool = False


SlotInfoMember = SlotInfo | ReservedForSampleSlotInfo | RVCSlotInfo | BeatriceV2SlotInfo


class MoveMergedModelParam(BaseModel):
    dst: int | None = None


class MoveExportedOnnxModelParam(BaseModel):
    dst: int | None = None


class MoveModelParam(BaseModel):
    src: int
    dst: int


class SetIconParam(BaseModel):
    slot_index: int
    icon_file: Path


class SetBeatriceV2VoiceIconFileParam(BaseModel):
    slot_index: int
    voice_index: int
    icon_file: Path


class SetBeatriceV2VoiceNameParam(BaseModel):
    slot_index: int
    voice_index: int
    voice_name: str


class SetBeatriceV2VoiceDescriptionParam(BaseModel):
    slot_index: int
    voice_index: int
    voice_description: str
