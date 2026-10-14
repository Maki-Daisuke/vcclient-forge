from pathlib import Path

from ...voice_chanager_const import InferencerType, RVCInferencerOnnxVersion
from .inferencer import Inferencer
from .rvc_inverencer_onnx_f0 import RVCInferencerOnnxF0
from .rvc_inverencer_onnx_nof0 import RVCInferencerOnnxNoF0


class InferencerManager:
    current_inferencer: Inferencer | None = None

    @classmethod
    def get_inferencer(
        cls,
        inferencer_type: InferencerType,
        model_path: Path,
        device_id: int,
        inferencer_type_version: RVCInferencerOnnxVersion | None = None,
    ) -> Inferencer:
        try:
            cls.current_inferencer = cls.load_inferencer(
                inferencer_type, model_path, device_id, inferencer_type_version
            )
            return cls.current_inferencer
        except Exception as e:
            raise RuntimeError(e)

    @classmethod
    def load_inferencer(
        cls,
        inferencer_type: InferencerType,
        model_path: Path,
        device_id: int,
        inferencer_type_version: RVCInferencerOnnxVersion | None = None,
    ) -> Inferencer:
        if inferencer_type == "onnxRVC":
            inferencer = RVCInferencerOnnxF0()
            inferencer.load_model(model_path, device_id, inferencer_type_version)
            return inferencer
        elif inferencer_type == "onnxRVCNono":
            inferencer = RVCInferencerOnnxNoF0()
            inferencer.load_model(model_path, device_id, inferencer_type_version)
            return inferencer
        else:
            raise RuntimeError(f"Unknown InferencerType {inferencer_type}")
