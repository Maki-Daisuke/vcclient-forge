from __future__ import annotations

import numpy as np
import pytest

from vcclient.voice_changer.voice_change_manager.inferencer.rvc_inferencer_onnx_f0 import RVCInferencerOnnxF0
from vcclient.voice_changer.voice_change_manager.inferencer.rvc_inferencer_onnx_nof0 import RVCInferencerOnnxNoF0


@pytest.mark.parametrize("inferencer_cls", [RVCInferencerOnnxF0, RVCInferencerOnnxNoF0])
@pytest.mark.parametrize("version", ["v2", "v1", "", None, "v2.1", "v3.0"])
@pytest.mark.parametrize(
    "raw_output",
    [
        np.array([1.5, -1.5, 0.25], dtype=np.float32),
        np.array([[1.5, -1.5, 0.25]], dtype=np.float32),
        np.array([[[1.5, -1.5, 0.25]]], dtype=np.float32),
    ],
)
def test_onnx_inferencers_normalize_audio_output_by_shape(
    inferencer_cls: type[RVCInferencerOnnxF0] | type[RVCInferencerOnnxNoF0],
    version: str | None,
    raw_output: np.ndarray,
) -> None:
    """Verify ONNX inferencers return clipped 1D float32 audio regardless of stored version metadata."""

    class _DummySession:
        def run(self, _output_names, _input_feed, run_options=None):
            return [raw_output]

    inferencer = inferencer_cls()
    inferencer.onnx_session = _DummySession()
    inferencer.isHalf = False
    inferencer.target_frames = None
    inferencer.inferencer_type_version = version

    result = inferencer.infer(
        feats=np.zeros((1, 4, 768), dtype=np.float32),
        pitch_length=np.array([4], dtype=np.int64),
        pitch=np.zeros((1, 4), dtype=np.int64),
        pitchf=np.zeros((1, 4), dtype=np.float32),
        sid=np.array([0], dtype=np.int64),
    )

    assert result.shape == (3,)
    assert result.dtype == np.float32
    np.testing.assert_allclose(result, np.array([1.0, -1.0, 0.25], dtype=np.float32))


@pytest.mark.parametrize("inferencer_cls", [RVCInferencerOnnxF0, RVCInferencerOnnxNoF0])
def test_onnx_inferencers_reject_unexpected_output_shape(
    inferencer_cls: type[RVCInferencerOnnxF0] | type[RVCInferencerOnnxNoF0],
) -> None:
    """Verify unexpected batch output shapes fail cleanly with a RuntimeError."""

    class _BadSession:
        def run(self, _output_names, _input_feed, run_options=None):
            return [np.zeros((2, 3), dtype=np.float32)]

    inferencer = inferencer_cls()
    inferencer.onnx_session = _BadSession()
    inferencer.isHalf = False
    inferencer.target_frames = None
    inferencer.inferencer_type_version = "v2.1"

    with pytest.raises(RuntimeError, match="Unexpected ONNX audio output shape"):
        inferencer.infer(
            feats=np.zeros((1, 4, 768), dtype=np.float32),
            pitch_length=np.array([4], dtype=np.int64),
            pitch=np.zeros((1, 4), dtype=np.int64),
            pitchf=np.zeros((1, 4), dtype=np.float32),
            sid=np.array([0], dtype=np.int64),
        )
