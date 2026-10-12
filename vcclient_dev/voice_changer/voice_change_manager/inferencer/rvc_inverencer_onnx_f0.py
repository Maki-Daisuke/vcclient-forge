import logging

import numpy as np
import onnxruntime
import torch
from torch import nn

from vcclient_dev.const import LOGGER_NAME
from vcclient_dev.voice_changer.data_types.voice_changer_data_types import RVCInferencerInfo

from ..device_manager.device_manager import DeviceManager
from .rvc_inferencer import RVCInferencer


class RVCInferencerOnnxF0(RVCInferencer):
    model: nn.Module

    def load_model(self=None, file=None, device_id=None, inferencer_type_version=(None,)):

        self.file = file

        self.device_id = device_id

        (onnx_providers, onnx_provider_options) = DeviceManager.get_instance().get_onnx_execution_provider(device_id)

        self.candidate_onnx_providers = onnx_providers

        self.candidate_onnx_provider_options = onnx_provider_options

        so = onnxruntime.SessionOptions()

        so.log_severity_level = 3

        self.onnx_session = onnxruntime.InferenceSession(
            str(self.file), sess_options=so, providers=onnx_providers, provider_options=onnx_provider_options
        )

        first_input_type = self.onnx_session.get_inputs()[0].type

        if first_input_type == "tensor(float)":
            self.isHalf = False

        else:
            self.isHalf = True

        logging.getLogger(LOGGER_NAME).info(f"""ONNX model loaded: {self.file}, first_input_type:{first_input_type}""")

        self.inferencer_type_version = inferencer_type_version

        return self

    def infer(
        self,
        feats: np.ndarray | torch.Tensor,
        pitch_length: np.ndarray | torch.Tensor,
        pitch: np.ndarray | torch.Tensor | None,
        pitchf: np.ndarray | torch.Tensor | None,
        sid: np.ndarray | torch.Tensor,
        convert_length: int | None = None,
    ) -> np.ndarray:
        try:
            if isinstance(feats, torch.Tensor):
                assert isinstance(feats, torch.Tensor)
                feats = feats.cpu().numpy()
            if isinstance(pitch_length, torch.Tensor):
                assert isinstance(pitch_length, torch.Tensor)
                pitch_length = pitch_length.cpu().numpy()
            if isinstance(pitch, torch.Tensor):
                assert isinstance(pitch, torch.Tensor)
                pitch = pitch.cpu().numpy()
            if isinstance(pitchf, torch.Tensor):
                assert isinstance(pitchf, torch.Tensor)
                pitchf = pitchf.cpu().numpy()
            if isinstance(sid, torch.Tensor):
                assert isinstance(sid, torch.Tensor)
                sid = sid.cpu().numpy()

            assert (
                isinstance(feats, np.ndarray)
                and isinstance(pitch_length, np.ndarray)
                and isinstance(pitch, np.ndarray)
                and isinstance(pitchf, np.ndarray)
                and isinstance(sid, np.ndarray)
            )

            if feats.ndim != 3:
                raise RuntimeError(
                    f"Exeption in {self.__class__.__name__} feats.ndim is not 3 (size :{feats.ndim}, {feats.shape})"
                )
            if pitch_length.ndim != 1:
                raise RuntimeError(
                    f"Exeption in {self.__class__.__name__} pitch_length.ndim is not 1 (size :{pitch_length.ndim}, {pitch_length.shape})"
                )
            if pitch.ndim != 2:
                raise RuntimeError(
                    f"Exeption in {self.__class__.__name__} pitch.ndim is not 2 (size :{pitch.ndim}, {pitch.shape})"
                )
            if pitchf.ndim != 2:
                raise RuntimeError(
                    f"Exeption in {self.__class__.__name__} pitchf.ndim is not 2 (size :{pitchf.ndim}, {pitchf.shape})"
                )
            if sid.ndim != 1:
                raise RuntimeError(
                    f"Exeption in {self.__class__.__name__} sid.ndim is not 1 (size :{sid.ndim}, {sid.shape})"
                )

            if self.isHalf:
                audio1 = self.onnx_session.run(
                    ["audio"],
                    {
                        "feats": feats.astype(np.float16),
                        "p_len": pitch_length.astype(np.int64),
                        "pitch": pitch.astype(np.int64),
                        "pitchf": pitchf.astype(np.float32),
                        "sid": sid.astype(np.int64),
                    },
                )
            else:
                audio1 = self.onnx_session.run(
                    ["audio"],
                    {
                        "feats": feats.astype(np.float32),
                        "p_len": pitch_length.astype(np.int64),
                        "pitch": pitch.astype(np.int64),
                        "pitchf": pitchf.astype(np.float32),
                        "sid": sid.astype(np.int64),
                    },
                )

            if (
                self.inferencer_type_version == "v3.0"
                or self.inferencer_type_version == "v2.1"
                or self.inferencer_type_version == "v2.2"
                or self.inferencer_type_version == "v1.1"
            ):
                res = audio1[0]
                return res
            else:
                res = np.array(audio1)[0][0, 0]
                res = np.clip(res, -1, 1)
                return res
        except Exception as e:
            raise RuntimeError(f"Exeption in {self.__class__.__name__}", e)

    def get_info(self=None):

        info = RVCInferencerInfo(
            inferencer_type="onnxRVC",
            model_file=self.file,
            device_id=self.device_id,
            candidate_onnx_providers=self.candidate_onnx_providers,
            candidate_onnx_provider_options=str(self.candidate_onnx_provider_options),
            onnx_providers=self.onnx_session.get_providers(),
            onnx_provider_options=str(self.onnx_session.get_provider_options()),
        )

        return info
