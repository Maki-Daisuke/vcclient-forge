from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.voice_change_manager.pitch_estimator.onnxfcpe_pitch_estimator import (
    FCPEOnnxPitchEstimator,
)
from vcclient.voice_changer.voice_change_manager.pitch_estimator.pitch_estimator_manager import (
    PitchEstimatorManager,
)


def test_normalize_pitch_estimator_whitelist():
    """Validates that only rmvpe and fcpe are retained, and all others fall back to rmvpe."""
    assert RVCSlotInfo.normalize_pitch_estimator("rmvpe") == "rmvpe"
    assert RVCSlotInfo.normalize_pitch_estimator("fcpe") == "fcpe"
    assert RVCSlotInfo.normalize_pitch_estimator("harvest") == "rmvpe"
    assert RVCSlotInfo.normalize_pitch_estimator("dio") == "rmvpe"
    assert RVCSlotInfo.normalize_pitch_estimator("crepe") == "rmvpe"
    assert RVCSlotInfo.normalize_pitch_estimator("pm") == "rmvpe"
    assert RVCSlotInfo.normalize_pitch_estimator("rmvpe_onnx") == "rmvpe"
    assert RVCSlotInfo.normalize_pitch_estimator("unknown_something") == "rmvpe"


def test_fcpe_onnx_estimation():
    fcpe_path = Path("modules/fcpe/fcpe.onnx")
    if not fcpe_path.exists():
        pytest.skip("modules/fcpe/fcpe.onnx is not present")

    estimator = FCPEOnnxPitchEstimator(pitch_estimator_type="fcpe", file=str(fcpe_path), device_id=-1)

    sr = 16000
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    pitch_coarse, pitch = estimator.estimate(
        audio=audio,
        prev_pitch=None,
        up_key=0,
        sample_rate=sr,
        window_length=160,
        silence_front_sec=0.0,
    )

    assert pitch_coarse.ndim == 2
    assert pitch.ndim == 2
    assert pitch_coarse.shape == pitch.shape

    # Check that estimated pitch around the center is approximately 440Hz (+/- 10Hz)
    center_pitch = pitch[0, pitch.shape[1] // 2]
    assert 430.0 < center_pitch < 450.0


def test_pitch_estimator_manager_load():
    """Verify that PitchEstimatorManager correctly dispatches to FCPE, RMVPE, and falls back for unsupported types."""
    with (
        patch(
            "vcclient.voice_changer.module_manager.module_manager.ModuleManager.get_module_filepath",
            return_value="dummy.onnx",
        ),
        patch(
            "vcclient.voice_changer.voice_change_manager.pitch_estimator.onnxfcpe_pitch_estimator.FCPEOnnxPitchEstimator"
        ) as mock_fcpe_cls,
        patch(
            "vcclient.voice_changer.voice_change_manager.pitch_estimator.onnxrmvpe_pitch_estimator.RMVPEOnnxPitchEstimator"
        ) as mock_rmvpe_cls,
    ):
        mock_fcpe_inst = MagicMock()
        mock_fcpe_inst.pitch_estimator_type = "fcpe"
        mock_fcpe_cls.return_value = mock_fcpe_inst

        mock_rmvpe_inst = MagicMock()
        mock_rmvpe_inst.pitch_estimator_type = "rmvpe"
        mock_rmvpe_cls.return_value = mock_rmvpe_inst

        # Test loading fcpe
        fcpe_est = PitchEstimatorManager.load_pitch_estimator("fcpe", device_id=-1)
        mock_fcpe_cls.assert_called_once_with("fcpe", "dummy.onnx", -1)
        assert fcpe_est.pitch_estimator_type == "fcpe"

        # Test loading rmvpe
        rmvpe_est = PitchEstimatorManager.load_pitch_estimator("rmvpe", device_id=-1)
        mock_rmvpe_cls.assert_called_with("rmvpe", "dummy.onnx", -1)
        assert rmvpe_est.pitch_estimator_type == "rmvpe"

        # Test fallback for unsupported type (harvest -> rmvpe)
        mock_rmvpe_cls.reset_mock()
        fallback_est = PitchEstimatorManager.load_pitch_estimator("harvest", device_id=-1)
        mock_rmvpe_cls.assert_called_once_with("rmvpe", "dummy.onnx", -1)
        assert fallback_est.pitch_estimator_type == "rmvpe"
