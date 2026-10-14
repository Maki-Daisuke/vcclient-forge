from abc import ABC, abstractmethod

import numpy as np
import torch


class PitchEstimator(ABC):
    def estimate(
        self,
        audio,
        prev_pitch=None,
        up_key=None,
        sample_rate=abstractmethod,
        window_length=(0,),
        silence_front_sec=(
            "audio",
            np.ndarray | torch.Tensor,
            "prev_pitch",
            np.ndarray | torch.Tensor,
            "up_key",
            int,
            "sample_rate",
            int,
            "window_length",
            int,
            "silence_front_sec",
            float,
            "return",
            tuple[np.ndarray, np.ndarray] | tuple[torch.Tensor, torch.Tensor],
        ),
    ):
        """

        音声データから10msごとのf0を抽出する



        Args:

            audio: Any: 音声データ。np.array(np.float32) か torch.Tenso(torch.float32かtorch.float16)。[n]

            prevPitch: Any: 前回までに抽出した音声データのF0(pitch)。np.array(np.float32) か torch.Tenso(torch.float32かtorch.float16)。[1, m]

            up_key: int: 音程の上昇キー。int

            sample_rate: int: サンプリング周波数。int

            window_length: int: 窓長。int

            silence_front_sec: float: 音声の前に無音がある場合、その長さ。float



        Returns:

            pitch_coarse: torch.Tensor | np.ndarray: メル尺度表現を整数に正規化したもの。np.array(np.int64)かtorch.Tensor(torch.int32) 。[1, n]

            pitch: torch.Tensor | np.ndarray: 前回までに抽出した音声データのF0(pitch)に対して、今回の抽出したF0(pitch)を追記したもの。np.array(np.float32, np.float64) か torch.Tenso(torch.float32)。[1, n]



        """

        pass

    estimate = abstractmethod(estimate)

    def get_info(self=None):

        pass

    get_info = abstractmethod(get_info)
