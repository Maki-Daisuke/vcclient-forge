from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime

from vcclient.device import DeviceConfig, create_pipeline_session, get_device
from vcclient.logger import logger

from ...data_types.voice_changer_data_types import EmbedderInfo
from .embedder import Embedder


class ContentvecOnnx(Embedder):
    model_file: Path
    deviceId: int = 0
    layer: int = 12
    useFinalProj: bool = True
    candidate_onnx_providers: list[str] = []
    candidate_onnx_provider_options: Any = None
    onnx_session: onnxruntime.InferenceSession
    isHalf: bool | None = None
    device: DeviceConfig | None = None

    def load_model(
        self,
        model_file: Path,
        device: DeviceConfig | int = 0,
        layer: int = 12,
        use_final_proj: bool = True,
        *,
        device_id: DeviceConfig | int | None = None,
    ) -> Embedder:
        target = device if device_id is None else device_id
        self.device = get_device(target) if isinstance(target, int) else target
        self.model_file = model_file
        self.deviceId = self.device.id
        self.layer = layer
        self.useFinalProj = use_final_proj

        self.onnx_session, self.candidate_onnx_providers, self.candidate_onnx_provider_options = (
            create_pipeline_session(model_file, self.device)
        )

        first_input_type = self.onnx_session.get_inputs()[0].type
        if first_input_type == "tensor(float)":
            self.isHalf = False
        else:
            self.isHalf = None

        return self

    def extract_features(self, audio: np.ndarray) -> np.ndarray:
        try:
            if not isinstance(audio, np.ndarray):
                raise TypeError(f"audio must be a numpy array, got {type(audio).__name__}")
            if audio.ndim != 1:
                logger.error(
                    "Exception in %s audio.ndim is not 1 (size: %s, %s)",
                    self.__class__.__name__,
                    audio.ndim,
                    audio.shape,
                )
                raise RuntimeError(
                    f"Exeption in {self.__class__.__name__} audio.ndim is not 1 (size :{audio.ndim}, {audio.shape})"
                )
            audio = audio.reshape(1, -1)
            if self.isHalf:
                unit = self.onnx_session.run(["units9", "unit12", "unit12s"], {"audio": audio.astype(np.float16)})
            else:
                unit = self.onnx_session.run(["units9", "unit12", "unit12s"], {"audio": audio.astype(np.float32)})
            if self.layer == 9:
                res = unit[0]
                return res
            else:
                res = unit[1]
                return res
        except Exception as e:
            raise RuntimeError(f"Exeption in {self.__class__.__name__}", e)

    def get_info(self):
        return EmbedderInfo(
            embedder_type="contentvec",
            model_file=self.model_file,
            device_id=self.deviceId,
            candidate_onnx_providers=self.candidate_onnx_providers,
            candidate_onnx_provider_options=str(self.candidate_onnx_provider_options),
            onnx_providers=self.onnx_session.get_providers(),
            onnx_provider_options=str(self.onnx_session.get_provider_options()),
        )
