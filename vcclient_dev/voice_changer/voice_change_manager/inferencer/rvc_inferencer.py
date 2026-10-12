from abc import abstractmethod

import numpy as np
import torch

from .inferencer import Inferencer


class RVCInferencer(Inferencer):
    def infer(
        self,
        feats,
        pitch_length=None,
        pitch=None,
        pitchf=abstractmethod,
        sid=(None,),
        convert_length=(
            "feats",
            np.ndarray | torch.Tensor,
            "pitch_length",
            np.ndarray | torch.Tensor,
            "pitch",
            np.ndarray | torch.Tensor | None,
            "pitchf",
            np.ndarray | torch.Tensor | None,
            "sid",
            np.ndarray | torch.Tensor,
            "convert_length",
            int | None,
            "return",
            torch.Tensor | np.ndarray,
        ),
    ):
        """音声を推論する



        ・音声を推論する



        Args:

            feats: Any: np.array(np.float32) か torch.Tensor(torch.float32かtorch.float16)。[1,n,768/256]

            featsLength: Any: np.array(np.int64) か torch.Tensor(torch.int64)。[1]

            pitch: Any: np.array(np.int64)かtorch.Tensor(torch.int32) [1,n]

            pitchFloat: Any: np.array(np.float32, np.float64) か torch.Tensor(torch.float32) [1,n]

            sid: Any: np.array(np.int64)かtorch.Tensor(torch.int64) [1]

            convert_length: int: 出力する音声の長さ。

        Returns:

            audio:  torch.Tensor[n]



        """

        pass

    infer = abstractmethod(infer)
