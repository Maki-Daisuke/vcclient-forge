from unittest.mock import MagicMock

import numpy as np

from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline import RVCPipeline


def _create_mock_pipeline() -> RVCPipeline:
    slot_info = RVCSlotInfo(
        slot_index=998,
        voice_changer_type="RVC",
        model_file="dummy.onnx",
        pitch_estimator="rmvpe",
        index_ratio=0.0,
        sample_rate=16000,
        is_f0=False,
    )
    pipeline = RVCPipeline.__new__(RVCPipeline)
    pipeline._slot_info = slot_info
    pipeline.slot_index = 998
    pipeline.gpu_device_id = -1
    pipeline.pitch_estimator_type = "rmvpe"
    pipeline.processing_window = 160
    pipeline.audio_buffer = np.zeros(0, dtype=np.float32)
    pipeline.pitchf_buffer = None
    pipeline.feature_buffer = None
    pipeline.index_data = None
    pipeline.is_gate_open = True
    pipeline.noise_gate_below_threshold_samples = 0

    pipeline.pitch_estimator = MagicMock()
    pipeline.pitch_estimator.estimate.return_value = (None, None)
    pipeline.embedder = MagicMock()
    pipeline.onnx_upscaler = MagicMock()
    pipeline.rvc = MagicMock()

    return pipeline


def test_volume_sqrt_scaling_zero_converted_does_not_produce_nan():
    """Verify that sqrt volume scaling keeps zero model output finite without NaN."""
    pipeline = _create_mock_pipeline()
    input_sample_num = 4000
    # Input audio has positive volume so it passes noise gate
    audio = np.ones(input_sample_num, dtype=np.float32) * 0.2

    T = 50
    pipeline.embedder.extract_features.return_value = np.zeros((1, T, 768), dtype=np.float32)
    pipeline.onnx_upscaler.run.return_value = [np.zeros((1, 768, 2 * T), dtype=np.float32)]

    # Simulate model returning silence / all zeros (e.g. 22,480 samples as in code review)
    output_len = 22480

    def mock_infer(feats, feats_len, pitch_coarse, pitch, sid, convert_length):
        return np.zeros(output_len, dtype=np.float32)

    pipeline.rvc.infer.side_effect = mock_infer

    output = pipeline.run(audio, real_crossfade_sec=0.02)

    assert isinstance(output, np.ndarray)
    assert output.shape[0] > 0
    assert not np.isnan(output).any(), "Output must not contain NaN"
    assert np.isfinite(output).all(), "Output must be finite"
    assert np.all(output == 0.0), "Output should be all zeros"


def test_volume_sqrt_scaling_normal_positive_scaling():
    """Verify that RVCPipeline scales converted audio by sqrt(input_rms)."""
    pipeline = _create_mock_pipeline()
    input_sample_num = 4000
    input_amplitude = 0.25
    audio = np.ones(input_sample_num, dtype=np.float32) * input_amplitude

    T = 50
    pipeline.embedder.extract_features.return_value = np.zeros((1, T, 768), dtype=np.float32)
    pipeline.onnx_upscaler.run.return_value = [np.zeros((1, 768, 2 * T), dtype=np.float32)]

    # Model outputs a constant 0.2
    model_output_amplitude = 0.2

    def mock_infer(feats, feats_len, pitch_coarse, pitch, sid, convert_length):
        return np.ones(convert_length, dtype=np.float32) * model_output_amplitude

    pipeline.rvc.infer.side_effect = mock_infer

    output = pipeline.run(audio, real_crossfade_sec=0.0)

    # Expected scaling: 0.2 * sqrt(0.25) = 0.1
    assert np.allclose(output, 0.1, atol=1e-4)
    assert np.isfinite(output).all()


def test_output_finite_check_cleans_model_nan_and_infinities():
    """Verify that np.nan_to_num with posinf=0.0 and neginf=0.0 replaces NaN and ±Inf with 0.0,
    preventing extreme float amplitude replacements (~3.4e38) that cause square operations to overflow.
    """
    pipeline = _create_mock_pipeline()
    input_sample_num = 4000
    audio = np.ones(input_sample_num, dtype=np.float32) * 0.2

    T = 50
    pipeline.embedder.extract_features.return_value = np.zeros((1, T, 768), dtype=np.float32)
    pipeline.onnx_upscaler.run.return_value = [np.zeros((1, 768, 2 * T), dtype=np.float32)]

    # Model returns NaN, +Inf, and -Inf values
    def mock_infer(feats, feats_len, pitch_coarse, pitch, sid, convert_length):
        ret = np.ones(convert_length, dtype=np.float32) * 0.1
        ret[10:20] = np.nan
        ret[20:30] = np.inf
        ret[30:40] = -np.inf
        return ret

    pipeline.rvc.infer.side_effect = mock_infer

    output = pipeline.run(audio, real_crossfade_sec=0.0)

    assert not np.isnan(output).any(), "Output must not contain any NaN values"
    assert not np.isinf(output).any(), "Output must not contain any Inf values"
    assert np.isfinite(output).all(), "Output must be completely finite"

    # Verify that NaN, +Inf, and -Inf were replaced by 0.0, NOT extreme floats (~3.4e38)
    assert np.all(output[10:20] == 0.0), "NaN elements must be converted to 0.0"
    assert np.all(output[20:30] == 0.0), "+Inf elements must be converted to 0.0"
    assert np.all(output[30:40] == 0.0), "-Inf elements must be converted to 0.0"

    # Subsequent downstream square operations (e.g. SOLA / RMS) must not overflow
    squared = np.square(output)
    assert np.isfinite(squared).all(), "Downstream squared operation must not overflow"
