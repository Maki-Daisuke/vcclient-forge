from unittest.mock import MagicMock

import numpy as np

from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline import RVCPipeline


def _create_mock_pipeline() -> RVCPipeline:
    slot_info = RVCSlotInfo(
        slot_index=999,
        voice_changer_type="RVC",
        model_file="dummy.onnx",
        pitch_estimator="rmvpe",
        index_ratio=0.0,
        sample_rate=16000,
        is_f0=False,
    )
    pipeline = RVCPipeline.__new__(RVCPipeline)
    pipeline._slot_info = slot_info
    pipeline.slot_index = 999
    pipeline.gpu_device_id = -1
    pipeline.pitch_estimator_type = "rmvpe"
    pipeline.processing_window = 160
    pipeline.audio_buffer = np.zeros(0, dtype=np.float32)
    pipeline.pitchf_buffer = None
    pipeline.feature_buffer = None
    pipeline.index_data = None
    pipeline.prev_vol = 0
    pipeline.is_gate_open = True

    pipeline.pitch_estimator = MagicMock()
    pipeline.pitch_estimator.estimate.return_value = (None, None)
    pipeline.embedder = MagicMock()
    pipeline.embedder.extract_features.return_value = np.zeros((1, 10, 768), dtype=np.float32)
    pipeline.onnx_upscaler = MagicMock()
    pipeline.onnx_upscaler.run.return_value = [np.zeros((1, 768, 20), dtype=np.float32)]
    pipeline.rvc = MagicMock()
    pipeline.rvc.infer.return_value = np.ones(4000, dtype=np.float32)

    return pipeline


def test_noise_gate_disabled_when_below_minus_100_db():
    """Verify that noise_gate <= -100.0 disables the gate and keeps it open."""
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
    original_gate = conf.noise_gate
    conf.noise_gate = -100.0

    try:
        pipeline = _create_mock_pipeline()
        pipeline.is_gate_open = False  # Start closed

        # Extremely low volume (practically silent)
        audio = np.zeros(4000, dtype=np.float32)
        pipeline.run(audio, real_crossfade_sec=0.0)

        # Gate should be forced open because threshold is <= -100.0
        assert pipeline.is_gate_open is True
    finally:
        conf.noise_gate = original_gate


def test_noise_gate_hysteresis_open_and_close_behavior():
    """Verify OBS-style noise gate hysteresis:

    - Open Threshold: conf.noise_gate (e.g. -40 dB)
    - Close Threshold: conf.noise_gate - 5.0 dB (e.g. -45 dB)
    - If closed, requires >= Open Threshold to open.
    - If open, stays open until level falls below Close Threshold.
    """
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
    original_gate = conf.noise_gate
    conf.noise_gate = -40.0  # Open = -40 dB, Close = -45 dB

    try:
        pipeline = _create_mock_pipeline()
        pipeline.is_gate_open = False  # Initially closed

        # 1. Input at -50 dB (< -45 dB): Should stay closed
        # vol = 10^(-50/20) ~= 0.003162
        audio_minus_50db = np.ones(4000, dtype=np.float32) * (10 ** (-50.0 / 20.0))
        out = pipeline.run(audio_minus_50db, real_crossfade_sec=0.0)
        assert pipeline.is_gate_open is False
        assert np.all(out == 0.0)
        pipeline.rvc.infer.assert_not_called()

        # 2. Input at -42 dB (in hysteresis zone: -45 dB <= vol < -40 dB):
        # Was closed, so should STAY closed
        audio_minus_42db = np.ones(4000, dtype=np.float32) * (10 ** (-42.0 / 20.0))
        out = pipeline.run(audio_minus_42db, real_crossfade_sec=0.0)
        assert pipeline.is_gate_open is False
        assert np.all(out == 0.0)
        pipeline.rvc.infer.assert_not_called()

        # 3. Input at -35 dB (>= -40 dB): Should OPEN
        audio_minus_35db = np.ones(4000, dtype=np.float32) * (10 ** (-35.0 / 20.0))
        out = pipeline.run(audio_minus_35db, real_crossfade_sec=0.0)
        assert pipeline.is_gate_open is True
        assert pipeline.rvc.infer.called

        # 4. Input at -42 dB (in hysteresis zone again):
        # Was open, so should STAY open (prevents chattering)
        pipeline.rvc.infer.reset_mock()
        out = pipeline.run(audio_minus_42db, real_crossfade_sec=0.0)
        assert pipeline.is_gate_open is True
        assert pipeline.rvc.infer.called

        # 5. Input at -48 dB (< -45 dB Close Threshold): Should CLOSE
        pipeline.rvc.infer.reset_mock()
        audio_minus_48db = np.ones(4000, dtype=np.float32) * (10 ** (-48.0 / 20.0))
        out = pipeline.run(audio_minus_48db, real_crossfade_sec=0.0)
        assert pipeline.is_gate_open is False
        assert np.all(out == 0.0)
        pipeline.rvc.infer.assert_not_called()
    finally:
        conf.noise_gate = original_gate


def test_noise_gate_zero_volume_closes_gate():
    """Verify that pure zero input (-inf dB) properly closes an active gate."""
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
    original_gate = conf.noise_gate
    conf.noise_gate = -40.0

    try:
        pipeline = _create_mock_pipeline()
        pipeline.is_gate_open = True  # Initially open

        zero_audio = np.zeros(4000, dtype=np.float32)
        out = pipeline.run(zero_audio, real_crossfade_sec=0.0)

        assert pipeline.is_gate_open is False
        assert np.all(out == 0.0)
    finally:
        conf.noise_gate = original_gate
