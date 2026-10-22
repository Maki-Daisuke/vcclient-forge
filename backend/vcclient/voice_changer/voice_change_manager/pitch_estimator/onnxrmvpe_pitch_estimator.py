from pathlib import Path

import numpy as np
import onnxruntime

from ...data_types.voice_changer_data_types import PitchEstimatorInfo
from ...voice_changer_const import PitchEstimatorType
from ..device_manager.device_manager import DeviceManager
from .pitch_estimator import PitchEstimator


class RMVPEOnnxPitchEstimator(PitchEstimator):
    def __init__(self, pitch_estimator_type: PitchEstimatorType, file: Path, device_id: int):
        super().__init__()
        self.device_id = device_id
        self.file = file
        self.pitch_estimator_type = pitch_estimator_type

        self.f0_min = 50
        self.f0_max = 1100
        self.f0_mel_min = 1127 * np.log(1 + self.f0_min / 700)
        self.f0_mel_max = 1127 * np.log(1 + self.f0_max / 700)

        (onnx_providers, onnx_provider_options) = DeviceManager.get_instance().get_onnx_execution_provider(device_id)
        self.candidate_onnx_providers = onnx_providers
        self.candidate_onnx_provider_options = onnx_provider_options

        so = onnxruntime.SessionOptions()
        so.log_severity_level = 3
        self.onnx_session = onnxruntime.InferenceSession(
            str(self.file), sess_options=so, providers=onnx_providers, provider_options=onnx_provider_options
        )

    def estimate(
        self,
        audio: np.ndarray,
        prev_pitch: np.ndarray | None = None,
        up_key: int = 0,
        sample_rate: int = 16000,
        window_length: int = 0,
        silence_front_sec: float = 0.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        try:
            if not isinstance(audio, np.ndarray):
                raise TypeError(f"audio should be np.ndarray, got {type(audio)}")
            if prev_pitch is None:
                prev_pitch = np.zeros([1, 1], dtype=np.float32)
            elif not isinstance(prev_pitch, np.ndarray):
                raise TypeError(f"prev_pitch should be np.ndarray, got {type(prev_pitch)}")

            if audio.ndim != 1:
                raise RuntimeError(
                    f"Exception in {self.__class__.__name__} audio.ndim is not 1 (size: {audio.ndim}, {audio.shape})"
                )
            if prev_pitch.ndim != 2:
                raise RuntimeError(
                    f"Exception in {self.__class__.__name__} prev_pitch.ndim is not 2 (size: {prev_pitch.ndim}, {prev_pitch.shape})"
                )

            pitch_length = audio.shape[0] // window_length
            silence_front_frame = silence_front_sec * sample_rate
            start_window = int(silence_front_frame / window_length)
            slience_front_frame_offset = start_window * window_length
            target_frame_length = len(audio) - slience_front_frame_offset
            minimum_frames = int(round(0.01 * sample_rate))
            target_frame_length = max(minimum_frames, target_frame_length)
            audio = audio[-target_frame_length:]
            audio = np.expand_dims(audio, axis=0)

            output = self.onnx_session.run(
                ["pitchf"],
                {
                    "waveform": audio.astype(np.float32),
                    "threshold": np.array([0.3]).astype(np.float32),
                },
            )
            f0 = output[0].squeeze()
            f0 *= pow(2, up_key / 12)
            pitch = prev_pitch.squeeze(axis=0)
            pitch = np.concatenate([pitch, f0], axis=0)

            if pitch.shape[0] < pitch_length:
                pitch = np.concatenate([np.zeros(pitch_length - pitch.shape[0]), pitch], axis=0)
            else:
                pitch = pitch[-pitch_length:]

            f0_mel = 1127 * np.log(1 + pitch / 700)
            f0_mel[f0_mel > 0] = (f0_mel[f0_mel > 0] - self.f0_mel_min) * 254 / (self.f0_mel_max - self.f0_mel_min) + 1
            f0_mel[f0_mel <= 1] = 1
            f0_mel[f0_mel > 255] = 255
            f0_coarse = np.rint(f0_mel).astype(int)

        except Exception as e:
            raise RuntimeError(f"Exception in {self.__class__.__name__}: {e}") from e

        return f0_coarse.reshape(1, -1), pitch.reshape(1, -1)

    def get_info(self) -> PitchEstimatorInfo:
        return PitchEstimatorInfo(
            pitch_estimator_type=self.pitch_estimator_type,
            model_file=self.file,
            device_id=self.device_id,
            candidate_onnx_providers=self.candidate_onnx_providers,
            candidate_onnx_provider_options=str(self.candidate_onnx_provider_options),
            onnx_providers=self.onnx_session.get_providers(),
            onnx_provider_options=str(self.onnx_session.get_provider_options()),
        )
