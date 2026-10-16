import logging
from pathlib import Path

import numpy as np
import onnxruntime

from ....const import LOGGER_NAME
from ...data_types.voice_changer_data_types import EmbedderInfo
from ..device_manager.device_manager import DeviceManager
from .embedder import Embedder


class ContentvecOnnx(Embedder):
    def load_model(
        self,
        model_file=None,
        device_id=None,
        layer=None,
        use_final_proj=("model_file", Path, "device_id", int, "layer", int, "use_final_proj", bool, "return", Embedder),
    ):

        self.model_file = model_file

        self.deviceId = device_id

        self.layer = layer

        self.useFinalProj = use_final_proj

        (onnx_providers, onnx_provider_options) = DeviceManager.get_instance().get_onnx_execution_provider(
            self.deviceId
        )

        self.candidate_onnx_providers = onnx_providers

        self.candidate_onnx_provider_options = onnx_provider_options

        so = onnxruntime.SessionOptions()

        so.log_severity_level = 3

        self.onnx_session = onnxruntime.InferenceSession(
            str(model_file), sess_options=so, providers=onnx_providers, provider_options=onnx_provider_options
        )

        first_input_type = self.onnx_session.get_inputs()[0].type

        if first_input_type == "tensor(float)":
            self.isHalf = False

            return self

        self.isHalf = None

        return self

    def extract_features(self, audio: np.ndarray) -> np.ndarray:
        try:
            assert isinstance(audio, np.ndarray)
            if audio.ndim != 1:
                logging.getLogger(LOGGER_NAME).error(
                    f"Exeption in {self.__class__.__name__} audio.dim is not 1 (size :{audio.ndim}, {audio.shape})"
                )
                raise RuntimeError(
                    f"Exeption in {self.__class__.__name__} audio.ndim is not 1 (size :{audio.ndim}, {audio.shape})"
                )
            audio = audio.reshape(1, -1)
            if self.isHalf:
                unit = self.onnx_session.run(["units9", "unit12", "unit12s"], {"audio": audio.astype(np.float16)})
            else:
                unit = self.onnx_session.run(["units9", "unit12", "unit12s"], {"audio": audio.astype(np.float32)})
            if self.layer == 9:
                res = unit[0]
                return res
            else:
                res = unit[1]
                return res
        except Exception as e:
            raise RuntimeError(f"Exeption in {self.__class__.__name__}", e)

    def get_info(self):

        info = EmbedderInfo(
            embedder_type="contentvec",
            model_file=self.model_file,
            device_id=self.deviceId,
            candidate_onnx_providers=self.candidate_onnx_providers,
            candidate_onnx_provider_options=str(self.candidate_onnx_provider_options),
            onnx_providers=self.onnx_session.get_providers(),
            onnx_provider_options=str(self.onnx_session.get_provider_options()),
        )

        return info
