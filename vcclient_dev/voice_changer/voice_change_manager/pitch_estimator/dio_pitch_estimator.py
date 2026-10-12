
import numpy as np
import torch

from ...data_types.voice_changer_data_types import PitchEstimatorInfo
from .pitch_estimator import PitchEstimator


class DioPitchEstimator(PitchEstimator):
    def __init__(self=None):

        super().__init__()

        self.f0_min = 50

        self.f0_max = 1100

        self.f0_mel_min = 1127 * np.log(1 + self.f0_min / 700)

        self.f0_mel_max = 1127 * np.log(1 + self.f0_max / 700)

    def estimate(
        self,
        audio,
        prev_pitch=None,
        up_key=None,
        sample_rate=None,
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
            tuple[np.ndarray, np.ndarray],
        ),
    ):

        pass

    # WARNING: Decompyle incomplete

    def get_info(self=None):

        info = PitchEstimatorInfo(
            pitch_estimator_type="dio",
            model_file=None,
            device_id=-1,
            candidate_onnx_providers=None,
            candidate_onnx_provider_options=None,
            onnx_providers=None,
            onnx_provider_options=None,
        )

        return info
