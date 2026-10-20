from abc import abstractmethod

import numpy as np

from ...data_types.voice_changer_data_types import RVCInferencerInfo
from .inferencer import Inferencer


class RVCInferencer(Inferencer):
    @abstractmethod
    def get_info(self) -> RVCInferencerInfo:
        pass

    @abstractmethod
    def infer(
        self,
        feats: np.ndarray,
        pitch_length: np.ndarray,
        pitch: np.ndarray,
        pitchf: np.ndarray,
        sid: np.ndarray,
        convert_length: int | None = None,
    ) -> np.ndarray:
        """音声を推論する (純粋 NumPy / ONNX)"""
        pass
