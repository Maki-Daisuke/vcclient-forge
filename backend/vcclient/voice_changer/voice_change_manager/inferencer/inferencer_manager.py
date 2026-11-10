from __future__ import annotations

from pathlib import Path

from vcclient.device import DeviceConfig

from ...voice_changer_const import InferencerType, RVCInferencerOnnxVersion
from .inferencer import Inferencer
from .rvc_inferencer_onnx_f0 import RVCInferencerOnnxF0
from .rvc_inferencer_onnx_nof0 import RVCInferencerOnnxNoF0


class InferencerManager:
    current_inferencer: Inferencer | None = None

    @classmethod
    def get_inferencer(
        cls,
        inferencer_type: InferencerType,
        model_path: Path,
        device: DeviceConfig | int | None = None,
        inferencer_type_version: RVCInferencerOnnxVersion | None = None,
        *,
        device_id: DeviceConfig | int | None = None,
        target_frames: int | None = None,
        sample_rate: int = 40000,
    ) -> Inferencer:
        target = device if device is not None else (device_id if device_id is not None else 0)
        try:
            cls.current_inferencer = cls.load_inferencer(
                inferencer_type,
                model_path,
                target,
                inferencer_type_version,
                target_frames=target_frames,
                sample_rate=sample_rate,
            )
            return cls.current_inferencer
        except Exception as e:
            raise RuntimeError(e)

    @classmethod
    def load_inferencer(
        cls,
        inferencer_type: InferencerType,
        model_path: Path,
        device: DeviceConfig | int | None = None,
        inferencer_type_version: RVCInferencerOnnxVersion | None = None,
        *,
        device_id: DeviceConfig | int | None = None,
        target_frames: int | None = None,
        sample_rate: int = 40000,
    ) -> Inferencer:
        target = device if device is not None else (device_id if device_id is not None else 0)
        inferencer: Inferencer
        if inferencer_type == "onnxRVC":
            inferencer = RVCInferencerOnnxF0()
        elif inferencer_type == "onnxRVCNono":
            inferencer = RVCInferencerOnnxNoF0()
        else:
            raise RuntimeError(f"Unknown InferencerType {inferencer_type}")
        inferencer.load_model(
            model_path,
            target,
            inferencer_type_version,
            target_frames=target_frames,
            sample_rate=sample_rate,
        )
        return inferencer
