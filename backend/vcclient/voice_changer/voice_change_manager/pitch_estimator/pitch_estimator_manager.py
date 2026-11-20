from __future__ import annotations

from vcclient.device import DeviceConfig
from vcclient.logger import logger

from ...module_manager import get_module_filepath
from ...voice_changer_const import PitchEstimatorType
from .pitch_estimator import PitchEstimator


class PitchEstimatorManager:
    @classmethod
    def get_pitch_estimator(
        cls,
        pitch_estimator_type: PitchEstimatorType,
        device: DeviceConfig | int | None = None,
        *,
        device_id: DeviceConfig | int | None = None,
    ) -> PitchEstimator:
        target = device if device is not None else (device_id if device_id is not None else 0)
        try:
            return cls.load_pitch_estimator(pitch_estimator_type, target)
        except Exception as e:
            raise RuntimeError(e)

    @classmethod
    def load_pitch_estimator(
        cls,
        pitch_estimator_type: PitchEstimatorType,
        device: DeviceConfig | int | None = None,
        *,
        device_id: DeviceConfig | int | None = None,
    ) -> PitchEstimator:
        target = device if device is not None else (device_id if device_id is not None else 0)
        if pitch_estimator_type == "fcpe":
            from .onnxfcpe_pitch_estimator import FCPEOnnxPitchEstimator

            path = get_module_filepath("fcpe.onnx")
            return FCPEOnnxPitchEstimator("fcpe", path, target)

        if pitch_estimator_type != "rmvpe":
            logger.warning(
                "Pitch estimator '%s' is unimplemented or deprecated. Falling back to 'rmvpe'.", pitch_estimator_type
            )
        from .onnxrmvpe_pitch_estimator import RMVPEOnnxPitchEstimator

        path = get_module_filepath("rmvpe_20231006.onnx")
        return RMVPEOnnxPitchEstimator("rmvpe", path, target)
