from unittest.mock import MagicMock

import numpy as np
import pytest

from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline import RVCPipeline


def _create_mock_pipeline(is_f0: bool = False, sample_rate: int = 16000) -> RVCPipeline:
    slot_info = RVCSlotInfo(
        slot_index=999,
        voice_changer_type="RVC",
        model_file="dummy.onnx",
        pitch_estimator="rmvpe",
        index_ratio=0.0,
        sample_rate=sample_rate,
        is_f0=is_f0,
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
    pipeline.index = None
    pipeline.big_npy = None

    # Mocks for pipeline components
    pipeline.pitch_estimator = MagicMock()
    pipeline.pitch_estimator.estimate.return_value = (None, None)
    pipeline.embedder = MagicMock()
    pipeline.onnx_upscaler = MagicMock()
    pipeline.rvc = MagicMock()

    return pipeline


def test_pipeline_rejects_invalid_audio_contracts():
    pipeline = _create_mock_pipeline()

    with pytest.raises(ValueError, match="1d"):
        pipeline.run(np.zeros((1, 8), dtype=np.float32), real_crossfade_sec=0)
    with pytest.raises(TypeError, match="float32 or float64"):
        pipeline.run(np.zeros(8, dtype=np.int16), real_crossfade_sec=0)


def test_generate_inputs_zero_crossfade_overlap_produces_finite_volume():
    """Verify that _generate_inputs slices audio_buffer to the end when crossfade_overlap_sec is 0.0.

    Previously, crop_end = -1 * 0 resulted in audio_buffer[crop_offset:0], which is an empty slice
    and caused crop.mean() to produce NaN, contaminating input_volume with NaN.
    """
    pipeline = _create_mock_pipeline()
    input_sample_num = 4000
    # Create audio with known non-zero amplitude
    audio = np.ones(input_sample_num, dtype=np.float32) * 0.1

    audio_buf, pitchf, feat, convert_size, input_volume, real_convert_size = pipeline._generate_inputs(
        audio=audio,
        crossfade_overlap_sec=0.0,
        sola_search_frame_sec=0.01,
        extra_frame_sec=0.02,
    )

    assert np.isfinite(input_volume), f"input_volume must be finite, got: {input_volume}"
    assert not np.isnan(input_volume), "input_volume must not be NaN"
    assert input_volume > 0.0, f"input_volume should be positive for non-zero audio, got: {input_volume}"
    # RMS of constant 0.1 should be 0.1
    assert np.isclose(input_volume, 0.1, atol=1e-5)


def test_pipeline_run_zero_crossfade_returns_finite_audio_4000_samples():
    """Verify that RVCPipeline.run() produces finite outputs without NaN when crossfade is zero.

    When crossfade_sec=0, audio_buffer[crop_offset:crop_end] must not be empty.
    With default volume compensation (sqrt), any NaN in input_volume propagates to
    all output samples (e.g. 4,000 samples becoming all NaN).
    """
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
    original_tuning = conf.volume_tuning_type
    original_sola = conf.sola_search_frame_sec
    conf.volume_tuning_type = "sqrt"
    conf.sola_search_frame_sec = 0.0  # Output size matches input_sample_num exactly
    try:
        pipeline = _create_mock_pipeline(is_f0=False, sample_rate=16000)
        input_sample_num = 4000
        audio = np.ones(input_sample_num, dtype=np.float32) * 0.2

        # Mock embedder feature extraction
        T = 50
        mock_feats = np.zeros((1, T, 768), dtype=np.float32)
        pipeline.embedder.extract_features.return_value = mock_feats

        # Mock onnx upscaler
        pipeline.onnx_upscaler.run.return_value = [np.zeros((1, 768, 2 * T), dtype=np.float32)]

        # Mock rvc inferencer to return normal non-zero converted samples
        def mock_infer(feats, feats_len, pitch_coarse, pitch, sid, convert_length):
            return np.ones(convert_length, dtype=np.float32) * 0.3

        pipeline.rvc.infer.side_effect = mock_infer

        output = pipeline.run(audio, real_crossfade_sec=0.0)

        assert isinstance(output, np.ndarray)
        assert output.shape[0] == 4000, f"Expected 4000 samples, got {output.shape[0]}"
        assert not np.isnan(output).any(), "Output audio must not contain any NaN values"
        assert np.isfinite(output).all(), "Output audio must be entirely finite"
        # Verify non-zero output
        expected_vol = 0.2
        expected_val = 0.3 * np.sqrt(expected_vol)
        assert np.allclose(output, expected_val, atol=1e-4)
    finally:
        conf.volume_tuning_type = original_tuning
        conf.sola_search_frame_sec = original_sola


def test_python_slice_zero_trap_demonstration():
    """Document and demonstrate why crop_end must be None instead of 0 for negative offsets.

    In Python, arr[-4000:0] means slicing from index -4000 up to index 0 (the start of the array),
    which produces an empty slice arr[0:0] with length 0.
    np.mean([]) evaluates to np.nan with a RuntimeWarning, which corrupts sqrt(input_volume) to NaN.
    Using arr[-4000:None] correctly slices from -4000 to the end of the array.
    """
    arr = np.ones(10000, dtype=np.float32)
    # The buggy slicing:
    buggy_slice = arr[-4000:0]
    assert buggy_slice.size == 0

    # The fixed slicing:
    fixed_slice = arr[-4000:None]
    assert fixed_slice.size == 4000
    assert np.all(fixed_slice == 1.0)
