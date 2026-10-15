from abc import abstractmethod

import numpy as np

from .inferencer import Inferencer


class RVCInferencer(Inferencer):
    @abstractmethod
    def infer(
        self,
        feats: np.ndarray,
        pitch_length: np.ndarray,
        pitch: np.ndarray | None = None,
        pitchf: np.ndarray | None = None,
        sid: np.ndarray | None = None,
        convert_length: int | None = None,
    ) -> np.ndarray:
        """音声を推論する (純粋 NumPy / ONNX)"""
        pass
