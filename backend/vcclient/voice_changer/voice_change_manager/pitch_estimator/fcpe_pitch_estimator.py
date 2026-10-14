import numpy as np
import torch
import torchfcpe

from ...data_types.voice_changer_data_types import PitchEstimatorInfo
from ..device_manager.device_manager import DeviceManager
from .pitch_estimator import PitchEstimator


class FCPEPitchEstimator(PitchEstimator):
    def __init__(self=None, pitch_estimator_type=None, device_id=None):

        super().__init__()

        self.device_id = device_id

        self.f0_min = 50

        self.f0_max = 1100

        self.f0_mel_min = 1127 * np.log(1 + self.f0_min / 700)

        self.f0_mel_max = 1127 * np.log(1 + self.f0_max / 700)

        self.pitch_estimator_type = pitch_estimator_type

        self.device = DeviceManager.get_instance().get_pytorch_device(device_id)

        self.fcpe = torchfcpe.spawn_bundled_infer_model(self.device)

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
            tuple[torch.Tensor, torch.Tensor],
        ),
    ):

        pass

    # WARNING: Decompyle incomplete

    def get_info(self=None):

        info = PitchEstimatorInfo(
            pitch_estimator_type="fcpe",
            model_file=None,
            device_id=self.device_id,
            candidate_onnx_providers=None,
            candidate_onnx_provider_options=None,
            onnx_providers=None,
            onnx_provider_options=None,
        )

        return info
