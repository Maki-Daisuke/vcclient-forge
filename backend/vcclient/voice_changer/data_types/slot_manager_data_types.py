from pathlib import Path
from typing import Dict

from pydantic import BaseModel, ConfigDict, field_validator

from ..voice_chanager_const import (
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


class ReservedForSampleModelImportParam(ModelImportParam):
    voice_changer_type: VoiceChangerType = "RESERVED_FOR_SAMPLE"
    progress: float


class RVCModelImportParam(ModelImportParam):
    voice_changer_type: VoiceChangerType = "RVC"
    model_file: Path
    index_file: Path | None = None
    embedder: EmbedderType | None = None


ModelImportParamMember = (
    ModelImportParam | ReservedForSampleModelImportParam | RVCModelImportParam
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
        if v not in ("rmvpe", "fcpe"):
            return "rmvpe"
        return v


class ReservedForSampleSlotInfo(SlotInfo):
    voice_changer_type: VoiceChangerType = "RESERVED_FOR_SAMPLE"
    progress: float


SlotInfoMember = SlotInfo | ReservedForSampleSlotInfo | RVCSlotInfo


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
