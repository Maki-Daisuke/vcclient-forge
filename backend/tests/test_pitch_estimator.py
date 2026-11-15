from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.voice_change_manager.pitch_estimator.onnxfcpe_pitch_estimator import (
    FCPEOnnxPitchEstimator,
)
from vcclient.voice_changer.voice_change_manager.pitch_estimator.onnxrmvpe_pitch_estimator import (
    RMVPEOnnxPitchEstimator,
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


def test_rmvpe_onnx_estimation_handles_short_audio():
    """Verify RMVPE does not crash on ultra-short audio (< 0.139s / 2224 samples, e.g. 1920 samples)."""
    rmvpe_path = Path("modules/rmvpe/rmvpe_20231006.onnx")
    if not rmvpe_path.exists():
        pytest.skip("modules/rmvpe/rmvpe_20231006.onnx is not present")

    estimator = RMVPEOnnxPitchEstimator(pitch_estimator_type="rmvpe", file=str(rmvpe_path), device_id=-1)

    sr = 16000
    # Test short chunks: 0.05s (800 samples) and 0.12s (1920 samples) where Pad reflect previously crashed
    for duration in [0.05, 0.12, 0.5]:
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

        expected_frames = len(audio) // 160
        assert pitch_coarse.shape == (1, expected_frames)
        assert pitch.shape == (1, expected_frames)
        if duration == 0.5:
            assert 430.0 < pitch[0, expected_frames // 2] < 450.0


@pytest.mark.parametrize(
    ("samples", "aligned_samples"),
    [
        (160, 4960),
        (3200, 4960),
        (4800, 4960),
        (4960, 4960),
        (4961, 4960),
        (5120, 4960),
        (10080, 10080),
        (10240, 10080),
    ],
)
def test_rmvpe_aligns_mel_frames_preserving_latest_audio_and_pitch(samples, aligned_samples):
    estimator = RMVPEOnnxPitchEstimator.__new__(RMVPEOnnxPitchEstimator)
    estimator.f0_mel_min = 1127 * np.log(1 + 50 / 700)
    estimator.f0_mel_max = 1127 * np.log(1 + 1100 / 700)
    estimator.onnx_session = MagicMock()
    estimated_pitch = np.arange(aligned_samples // 160 + 1, dtype=np.float32) + 100
    estimator.onnx_session.run.return_value = [estimated_pitch[None, :]]
    audio = np.arange(samples, dtype=np.float32) + 1

    coarse, pitch = estimator.estimate(audio, sample_rate=16000, window_length=160, silence_front_sec=0.32)

    inputs = estimator.onnx_session.run.call_args.args[1]
    model_audio = inputs["waveform"][0]
    assert model_audio.shape == (aligned_samples,)
    assert (aligned_samples // 160 + 1) % 32 == 0
    retained = min(samples, aligned_samples)
    np.testing.assert_array_equal(model_audio[-retained:], audio[-retained:])
    if aligned_samples > samples:
        assert not np.any(model_audio[: aligned_samples - samples])
    assert coarse.shape == pitch.shape == (1, samples // 160)
    expected_frames = samples // 160
    if len(estimated_pitch) < expected_frames:
        expected = np.pad(estimated_pitch, (expected_frames - len(estimated_pitch), 0))
    else:
        expected = estimated_pitch[-expected_frames:]
    np.testing.assert_array_equal(pitch[0], expected)


@pytest.mark.parametrize(("extra_sec", "expected_samples"), [(0.0, 10080), (0.009, 10080), (0.01, 4960)])
def test_rmvpe_preserves_current_chunk_when_extra_is_too_short(extra_sec, expected_samples):
    estimator = RMVPEOnnxPitchEstimator.__new__(RMVPEOnnxPitchEstimator)
    estimator.f0_mel_min = 1127 * np.log(1 + 50 / 700)
    estimator.f0_mel_max = 1127 * np.log(1 + 1100 / 700)
    estimator.onnx_session = MagicMock()
    estimator.onnx_session.run.return_value = [np.full((1, expected_samples // 160 + 1), 440, dtype=np.float32)]
    audio = np.arange(5120, dtype=np.float32) + 1

    estimator.estimate(audio, sample_rate=16000, window_length=160, silence_front_sec=extra_sec)

    model_audio = estimator.onnx_session.run.call_args.args[1]["waveform"][0]
    assert len(model_audio) == expected_samples
    retained = min(len(audio), expected_samples)
    np.testing.assert_array_equal(model_audio[-retained:], audio[-retained:])


def test_fcpe_onnx_estimation_handles_short_audio():
    """Verify FCPE does not crash on ultra-short audio chunks."""
    fcpe_path = Path("modules/fcpe/fcpe.onnx")
    if not fcpe_path.exists():
        pytest.skip("modules/fcpe/fcpe.onnx is not present")

    estimator = FCPEOnnxPitchEstimator(pitch_estimator_type="fcpe", file=str(fcpe_path), device_id=-1)

    sr = 16000
    for duration in [0.05, 0.12, 0.5]:
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

        expected_frames = len(audio) // 160
        assert pitch_coarse.shape == (1, expected_frames)
        assert pitch.shape == (1, expected_frames)


def test_pitch_estimator_manager_load():
    """Verify that PitchEstimatorManager correctly dispatches to FCPE, RMVPE, and falls back for unsupported types."""
    with (
        patch(
            "vcclient.voice_changer.voice_change_manager.pitch_estimator.pitch_estimator_manager.get_module_filepath",
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
