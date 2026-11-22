from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from ..voice_changer_const import EmbedderType, InferencerType, PitchEstimatorType, VoiceChangerType


class StoredModelParams(BaseModel):
    """Per-model metadata and default conversion settings stored in `params.json`."""

    model_config = ConfigDict(protected_namespaces=())

    id: str
    voice_changer_type: VoiceChangerType = "RVC"
    name: str = ""
    model_file: str | None = None
    index_file: str | None = None
    icon_file: str | None = None
    icon_revision: int = 0
    is_onnx: bool = True
    inferencer_type: InferencerType = "onnxRVC"
    sample_rate: int = -1
    is_f0: bool = True
    embedder: EmbedderType = "hubert_base_l12"
    pitch_estimator: PitchEstimatorType = "rmvpe"
    version: str = ""
    chunk_sec: float = 0.5
    pitch_shift: int = 0
    index_ratio: float = 0.0

    @field_validator("pitch_estimator", mode="before")
    @classmethod
    def normalize_pitch_estimator(cls, value: str) -> str:
        if value not in ("rmvpe", "fcpe"):
            return "rmvpe"
        return value

    @field_validator("inferencer_type", mode="before")
    @classmethod
    def normalize_inferencer_type(cls, value: str) -> str:
        if value in ("onnxRVC", "onnxRVCNono"):
            return value
        if isinstance(value, str) and "Nono" in value:
            return "onnxRVCNono"
        return "onnxRVC"

    def to_model(self, model_dir_has_icon: bool | None = None) -> Model:
        """Convert stored params to the clean wire `Model` DTO."""
        has_icon = model_dir_has_icon if model_dir_has_icon is not None else (self.icon_file is not None)
        return Model(
            id=self.id,
            name=self.name,
            sample_rate=self.sample_rate,
            supports_f0=self.is_f0,
            has_index=self.index_file is not None and self.index_file.strip() != "",
            embedder=self.embedder,
            version=self.version,
            has_icon=has_icon,
            icon_revision=self.icon_revision,
            pitch_shift=self.pitch_shift,
            index_ratio=self.index_ratio,
            chunk_sec=self.chunk_sec,
            pitch_estimator=self.pitch_estimator,
        )


class Model(BaseModel):
    """Domain API model catalog entry."""

    id: str
    name: str
    sample_rate: int
    supports_f0: bool
    has_index: bool
    embedder: EmbedderType
    version: str
    has_icon: bool
    icon_revision: int
    pitch_shift: int
    index_ratio: float
    chunk_sec: float
    pitch_estimator: PitchEstimatorType


class ModelUpdate(BaseModel):
    """Mutable catalog metadata and per-model conversion defaults accepted by `PUT /api/models/{id}`."""

    name: str | None = None
    pitch_shift: int | None = None
    index_ratio: float | None = None
    chunk_sec: float | None = None
    pitch_estimator: PitchEstimatorType | None = None


class ModelOrder(BaseModel):
    """Explicit catalog display ordering payload for `PUT /api/models/order`."""

    model_ids: list[str]
