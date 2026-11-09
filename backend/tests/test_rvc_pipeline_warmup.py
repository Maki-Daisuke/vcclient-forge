from unittest.mock import MagicMock

import numpy as np
import pytest

from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline import RVCPipeline


@pytest.fixture
def mock_rvc_pipeline():
    pipeline = RVCPipeline.__new__(RVCPipeline)
    slot_info = RVCSlotInfo(
        slot_index=9999,
        voice_changer_type="RVC",
        model_file="dummy.onnx",
        chunk_sec=0.2,
        embedder="hubert_base_l12",
        pitch_estimator="rmvpe",
    )
    pipeline._slot_info = slot_info
    pipeline.slot_index = 9999
    pipeline.gpu_device_id = 0
    pipeline.pitch_estimator_type = "rmvpe"
    pipeline.embedder = MagicMock()
    pipeline.rvc = MagicMock()
    pipeline.onnx_upscaler = MagicMock()
    pipeline.pitch_estimator = MagicMock()
    pipeline.index_data = None
    pipeline._reset_buffers()
    return pipeline


def test_warmup_invokes_run_with_synthetic_audio(mock_rvc_pipeline: RVCPipeline):
    """Verify that _warmup generates a 440Hz sine wave matching chunk_sec and calls run()."""
    executed_audio: list[np.ndarray] = []

    def mock_run(audio: np.ndarray, real_crossfade_sec: float) -> np.ndarray:
        executed_audio.append(audio.copy())
        # Simulate dirty buffers during inference
        mock_rvc_pipeline.audio_buffer = np.ones(16384, dtype=float) * 999.0
        mock_rvc_pipeline.prev_vol = 123.0
        mock_rvc_pipeline.is_gate_open = False
        return np.zeros(100, dtype=float)

    mock_rvc_pipeline.run = mock_run

    mock_rvc_pipeline._warmup()

    assert len(executed_audio) == 1
    audio = executed_audio[0]
    expected_sample_count = int(round(0.2 * 16000))  # 3200 samples
    assert len(audio) == expected_sample_count
    assert audio.dtype == np.float32
    # Ensure it's not silent (e.g. max amplitude near 0.1)
    assert np.max(np.abs(audio)) > 0.05

    # Verify that buffers were fully reset after warmup
    assert np.all(mock_rvc_pipeline.audio_buffer == 0.0)
    assert mock_rvc_pipeline.prev_vol == 0
    assert mock_rvc_pipeline.is_gate_open is True
    assert mock_rvc_pipeline.noise_gate_below_threshold_samples == 0


def test_warmup_recovers_gracefully_from_error(mock_rvc_pipeline: RVCPipeline):
    """Verify that _warmup catches exceptions and still resets internal buffers."""

    def mock_run_fail(audio: np.ndarray, real_crossfade_sec: float) -> np.ndarray:
        mock_rvc_pipeline.audio_buffer = np.ones(16384, dtype=float) * 42.0
        raise RuntimeError("Simulated inference engine failure")

    mock_rvc_pipeline.run = mock_run_fail

    # Should not raise
    mock_rvc_pipeline._warmup()

    # Buffers must still be reset
    assert np.all(mock_rvc_pipeline.audio_buffer == 0.0)
    assert mock_rvc_pipeline.is_gate_open is True


def test_warmup_skips_when_pipeline_incomplete():
    """Verify that _warmup safely skips when pipeline components are not yet initialized."""
    pipeline = RVCPipeline.__new__(RVCPipeline)
    # Does not have embedder, rvc, etc.
    pipeline._warmup()  # Must not crash
