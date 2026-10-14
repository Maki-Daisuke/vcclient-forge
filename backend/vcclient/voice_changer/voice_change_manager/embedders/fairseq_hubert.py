from pathlib import Path

try:
    from fairseq import checkpoint_utils
except ImportError:
    checkpoint_utils = None


from ...data_types.voice_changer_data_types import EmbedderInfo
from ..device_manager.device_manager import DeviceManager
from .embedder import Embedder


class FairseqHubert(Embedder):
    def load_model(
        self,
        file=None,
        device_id=None,
        layer=None,
        use_final_proj=("file", Path, "device_id", int, "layer", int, "use_final_proj", bool, "return", Embedder),
    ):

        self.model_file = file

        self.deviceId = device_id

        self.dev = DeviceManager.get_instance().get_pytorch_device(device_id)

        self.isHalf = DeviceManager.get_instance().half_precision_available(device_id)

        self.layer = layer

        self.useFinalProj = use_final_proj

    # WARNING: Decompyle incomplete

    def extract_features(self=None, audio=None):
        """

        音声データから20msごとの特徴を抽出する

        Args:

            audio: np.array(np.float32 or np.float64) or torch.Tensor(torch.float32 or torch.float16) [n]



        Returns:

            feats: torch.Tensor or np.array [1, n, 768] or [1, n, 256]

        """

        pass

    # WARNING: Decompyle incomplete

    def get_info(self=None):

        if self.layer == 9:
            embedder_type = "hubert_base_l9fp"

        elif self.layer == 12:
            embedder_type = "hubert_base_l12"

        else:
            raise RuntimeError(f"""Unknown layer {self.layer}""")

        info = EmbedderInfo(
            embedder_type=embedder_type,
            model_file=self.model_file,
            device_id=self.deviceId,
            candidate_onnx_providers=None,
            candidate_onnx_provider_options=None,
            onnx_providers=None,
            onnx_provider_options=None,
        )

        return info
