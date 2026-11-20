from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

from ..voice_changer_const import (
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


class RVCModelImportParam(ModelImportParam):
    voice_changer_type: VoiceChangerType = "RVC"
    model_file: Path
    index_file: Path | None = None
    embedder: EmbedderType | None = None


ModelImportParamMember = ModelImportParam | RVCModelImportParam


class SlotInfo(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    slot_index: int = -1
    voice_changer_type: VoiceChangerType | None = None
    name: str = ""
    description: str = ""
    credit: str = ""
    terms_of_use_url: str = ""
    icon_file: Path | None = None


class RVCSlotInfo(SlotInfo):
    voice_changer_type: VoiceChangerType = "RVC"
    model_file: Path | None = None
    index_file: Path | None = None
    is_onnx: bool = False
    inferencer_type: InferencerType = "onnxRVC"
    sample_rate: int = -1
    is_f0: bool = True
    embedder: EmbedderType = "hubert_base_l12"
    pitch_estimator: PitchEstimatorType = "rmvpe"
    version: str = ""
    chunk_sec: float = 0.5
    pitch_shift: int = 0
    index_ratio: float = 0

    @field_validator("pitch_estimator", mode="before")
    @classmethod
    def normalize_pitch_estimator(cls, v: str) -> str:
        if v not in ("rmvpe", "fcpe"):
            return "rmvpe"
        return v

    @field_validator("inferencer_type", mode="before")
    @classmethod
    def normalize_inferencer_type(cls, v: str) -> str:
        if v in ("onnxRVC", "onnxRVCNono"):
            return v
        if isinstance(v, str) and "Nono" in v:
            return "onnxRVCNono"
        return "onnxRVC"


class ReservedForSampleSlotInfo(SlotInfo):
    voice_changer_type: VoiceChangerType = "RESERVED_FOR_SAMPLE"
    progress: float


SlotInfoMember = SlotInfo | ReservedForSampleSlotInfo | RVCSlotInfo
