from __future__ import annotations

import numpy as np

from vcclient.device import DeviceConfig, get_device
from vcclient.logger import logger
from vcclient.voice_changer.data_types.voice_changer_data_types import RVCInferencerInfo

from .rvc_inferencer import RVCInferencer


class RVCInferencerOnnxF0(RVCInferencer):
    def load_model(
        self,
        file=None,
        device: DeviceConfig | int | None = None,
        inferencer_type_version=None,
        *,
        device_id: DeviceConfig | int | None = None,
        target_frames: int | None = None,
        sample_rate: int = 40000,
    ):
        target = device if device is not None else (device_id if device_id is not None else 0)
        self.device = get_device(target) if isinstance(target, int) else target
        self.file = file
        self.device_id = self.device.id
        self.target_frames = target_frames
        self.sample_rate = sample_rate
        upsample_rate = sample_rate // 100 if sample_rate > 0 else 400
        self.onnx_session, self.candidate_onnx_providers, self.candidate_onnx_provider_options = (
            self.device.create_session(
                self.file,
                patch_type="rvc",
                target_frames=target_frames,
                upsample_rate=upsample_rate,
            )
        )

        first_input_type = self.onnx_session.get_inputs()[0].type
        if first_input_type == "tensor(float)":
            self.isHalf = False
        else:
            self.isHalf = True

        logger.info("ONNX model loaded: %s, first_input_type: %s", self.file, first_input_type)
        self.inferencer_type_version = inferencer_type_version
        return self

    def infer(
        self,
        feats: np.ndarray,
        pitch_length: np.ndarray,
        pitch: np.ndarray,
        pitchf: np.ndarray,
        sid: np.ndarray,
        convert_length: int | None = None,
    ) -> np.ndarray:
        try:
            if self.target_frames is not None:
                if feats.shape[1] < self.target_frames:
                    pad_len = self.target_frames - feats.shape[1]
                    feats = np.pad(feats, ((0, 0), (0, pad_len), (0, 0)))
                    pitch = np.pad(pitch, ((0, 0), (0, pad_len)))
                    pitchf = np.pad(pitchf, ((0, 0), (0, pad_len)))
                elif feats.shape[1] > self.target_frames:
                    feats = feats[:, : self.target_frames, :]
                    pitch = pitch[:, : self.target_frames]
                    pitchf = pitchf[:, : self.target_frames]
                pitch_length = np.array([self.target_frames], dtype=np.int64)
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

    def get_info(self) -> RVCInferencerInfo:
        return RVCInferencerInfo(
            inferencer_type="onnxRVC",
            model_file=self.file,
            device_id=self.device_id,
            candidate_onnx_providers=self.candidate_onnx_providers,
            candidate_onnx_provider_options=str(self.candidate_onnx_provider_options),
            onnx_providers=self.onnx_session.get_providers(),
            onnx_provider_options=str(self.onnx_session.get_provider_options()),
        )
