from vcclient.logger import logger

from ...module_manager.module_manager import ModuleManager
from ...voice_changer_const import PitchEstimatorType
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
        if pitch_estimator_type == "fcpe":
            from .onnxfcpe_pitch_estimator import FCPEOnnxPitchEstimator

            path = ModuleManager.get_instance().get_module_filepath("fcpe.onnx")
            return FCPEOnnxPitchEstimator("fcpe", path, device_id)

        if pitch_estimator_type != "rmvpe":
            logger.warning(
                "Pitch estimator '%s' is unimplemented or deprecated. Falling back to 'rmvpe'.", pitch_estimator_type
            )
        from .onnxrmvpe_pitch_estimator import RMVPEOnnxPitchEstimator

        path = ModuleManager.get_instance().get_module_filepath("rmvpe_20231006.onnx")
        return RMVPEOnnxPitchEstimator("rmvpe", path, device_id)
