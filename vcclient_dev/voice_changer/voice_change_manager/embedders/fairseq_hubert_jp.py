

from ...data_types.voice_changer_data_types import EmbedderInfo
from ..embedders.fairseq_hubert import FairseqHubert


class FairseqHubertJp(FairseqHubert):
    def load_model(self=None, file=None, device_id=None, layer=None, use_final_proj=None):

        super().load_model(file, device_id, layer, use_final_proj)

        return self

    def get_info(self=None):

        if self.layer == 9:
            embedder_type = "hubert_base_japanese_l9fp"

        elif self.layer == 12:
            embedder_type = "hubert_base_japanese_l12"

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
