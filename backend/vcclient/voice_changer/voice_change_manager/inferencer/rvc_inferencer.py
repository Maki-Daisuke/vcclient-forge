from abc import abstractmethod

import numpy as np

from ...data_types.voice_changer_data_types import RVCInferencerInfo
from .inferencer import Inferencer


def extract_onnx_audio_output(raw_output: np.ndarray) -> np.ndarray:
    """Normalize 1D, (1, N), or (1, 1, N) ONNX vocoder output into a clipped 1D waveform."""
    audio = np.asarray(raw_output)
    if audio.ndim == 1:
        return np.clip(audio, -1, 1)
    if audio.ndim == 2 and audio.shape[0] == 1:
        return np.clip(audio[0], -1, 1)
    if audio.ndim == 3 and audio.shape[0] == 1 and audio.shape[1] == 1:
        return np.clip(audio[0, 0], -1, 1)
    raise ValueError(f"Unexpected ONNX audio output shape: {audio.shape}")


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
