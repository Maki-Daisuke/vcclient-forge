from abc import ABC, abstractmethod

import numpy as np

from vcclient.voice_changer.data_types.voice_changer_data_types import PitchEstimatorInfo


class PitchEstimator(ABC):
    @abstractmethod
    def estimate(
        self,
        audio: np.ndarray,
        prev_pitch: np.ndarray | None = None,
        up_key: int = 0,
        sample_rate: int = 16000,
        window_length: int = 0,
        silence_front_sec: float = 0.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """音声データから10msごとのf0を抽出する

        Args:
            audio: 音声データ (np.ndarray, float32, 1D: [n])
            prev_pitch: 前回までに抽出したF0 (np.ndarray, float32/float64, 2D: [1, m])
            up_key: 音程の上昇キー (半音単位)
            sample_rate: サンプリング周波数 (Hz)
            window_length: 窓長
            silence_front_sec: 音声の前の無音長 (秒)

        Returns:
            pitch_coarse: メル尺度表現を整数に正規化したもの (np.ndarray, int, [1, n])
            pitch: 累積F0 (np.ndarray, float32/float64, [1, n])
        """
        ...

    @abstractmethod
    def get_info(self) -> PitchEstimatorInfo:
        """ピッチ推定器の情報を取得する"""
        ...
