from ...module_manager.module_manager import ModuleManager
from ...voice_chanager_const import PitchEstimatorType
from .pitch_estimator import PitchEstimator


class PitchEstimatorManager:
    current_pitch_estimator: PitchEstimator | None = None

    @classmethod
    def get_pitch_estimator(cls, pitch_estimator_type: PitchEstimatorType, device_id: int) -> PitchEstimator:
        try:
            cls.current_pitch_estimator = cls.load_pitch_estimator(pitch_estimator_type, device_id)
            return cls.current_pitch_estimator
        except Exception as e:
            raise RuntimeError(e)

    @classmethod
    def load_pitch_estimator(cls, pitch_estimator_type: PitchEstimatorType, device_id: int) -> PitchEstimator:
        if pitch_estimator_type == "harvest":
            from .harvest_pitch_estimator import HarvestPitchEstimator

            return HarvestPitchEstimator()
        elif pitch_estimator_type == "dio":
            from .dio_pitch_estimator import DioPitchEstimator

            return DioPitchEstimator()
        elif pitch_estimator_type.startswith("crepe_"):
            raise RuntimeError(f"Pitch estimator '{pitch_estimator_type}' is deprecated. Please use 'rmvpe_onnx'.")
        elif pitch_estimator_type == "rmvpe":
            raise RuntimeError("PyTorch RMVPE ('rmvpe') is deprecated. Please use 'rmvpe_onnx'.")
        elif pitch_estimator_type == "rmvpe_onnx":
            from .onnxrmvpe_pitch_estimator import RMVPEOnnxPitchEstimator

            path = ModuleManager.get_instance().get_module_filepath("rmvpe_20231006.onnx")
            return RMVPEOnnxPitchEstimator("rmvpe_onnx", path, device_id)
        elif pitch_estimator_type == "fcpe":
            from .fcpe_pitch_estimator import FCPEPitchEstimator

            return FCPEPitchEstimator("fcpe", device_id)
        else:
            raise RuntimeError(f"Unknown PitchEstimatorType {pitch_estimator_type}")
