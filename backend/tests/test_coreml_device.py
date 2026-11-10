import tempfile
from pathlib import Path

import onnxruntime as ort
import pytest

from vcclient.device import DeviceConfig
from vcclient.device.providers.coreml import CoreMLCacheDir
from vcclient.voice_changer.voice_changer_const import SettingsDir


def test_coreml_device_constants():
    assert CoreMLCacheDir.name == "coreml_cache"
    assert CoreMLCacheDir.exists()
    assert CoreMLCacheDir != SettingsDir / "coreml_cache"
    assert Path(tempfile.gettempdir()) in CoreMLCacheDir.parents


def test_device_manager_coreml_provider_configuration(monkeypatch: pytest.MonkeyPatch):
    dev_ane = DeviceConfig(
        id=1,
        canonical_id="coreml:ane:0",
        provider="coreml",
        device_index=0,
        device_type="NPU",
        name="[CoreML] Apple M2 (ANE + GPU + CPU)",
        metadata={"compute_units": "ALL"},
    )
    dev_gpu = DeviceConfig(
        id=2,
        canonical_id="coreml:gpu:0",
        provider="coreml",
        device_index=0,
        device_type="GPU",
        name="[CoreML] Apple M2 (GPU + CPU)",
        metadata={"compute_units": "CPUAndGPU"},
    )

    # 1. When CoreMLExecutionProvider is available (e.g. on macOS)
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["CoreMLExecutionProvider", "CPUExecutionProvider"])
    providers, provider_options = dev_ane._resolve_provider()

    assert "CoreMLExecutionProvider" in providers
    assert "CPUExecutionProvider" in providers
    assert len(provider_options) == 2
    assert provider_options[0]["ModelFormat"] == "NeuralNetwork"
    assert provider_options[0]["MLComputeUnits"] == "ALL"
    assert provider_options[0]["RequireStaticInputShapes"] == "0"
    assert provider_options[0]["EnableOnSubgraphs"] == "0"
    assert provider_options[0]["ModelCacheDirectory"] == str((CoreMLCacheDir / "all_neuralnetwork_dynamic").resolve())

    # 1b. When GPU preferred, MLComputeUnits should be CPUAndGPU
    providers_gpu, provider_options_gpu = dev_gpu._resolve_provider()
    assert provider_options_gpu[0]["MLComputeUnits"] == "CPUAndGPU"
    assert provider_options_gpu[0]["ModelCacheDirectory"] == str(
        (CoreMLCacheDir / "cpuandgpu_neuralnetwork_dynamic").resolve()
    )

    # 2. When CoreMLExecutionProvider is unavailable, fallback safely to CPU
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["CPUExecutionProvider"])
    providers_fallback, _ = dev_ane._resolve_provider()
    assert "CoreMLExecutionProvider" not in providers_fallback
    assert "CPUExecutionProvider" in providers_fallback


def test_coreml_two_tier_provider_resolution(monkeypatch: pytest.MonkeyPatch):
    dev = DeviceConfig(
        id=2,
        canonical_id="coreml:gpu:0",
        provider="coreml",
        device_index=0,
        device_type="GPU",
        name="[CoreML] Apple M2 (GPU + CPU)",
        metadata={"compute_units": "CPUAndGPU"},
    )
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["CoreMLExecutionProvider", "CPUExecutionProvider"])

    # Tier 1: MLProgram with static shapes
    providers_tier1, opts_tier1 = dev._resolve_provider(model_format="MLProgram", require_static_shapes=True)
    assert opts_tier1[0]["ModelFormat"] == "MLProgram"
    assert opts_tier1[0]["RequireStaticInputShapes"] == "1"
    assert opts_tier1[0]["MLComputeUnits"] == "CPUAndGPU"

    # Tier 2: NeuralNetwork with dynamic shapes
    providers_tier2, opts_tier2 = dev._resolve_provider(model_format="NeuralNetwork", require_static_shapes=False)
    assert opts_tier2[0]["ModelFormat"] == "NeuralNetwork"
    assert opts_tier2[0]["RequireStaticInputShapes"] == "0"
    assert opts_tier2[0]["MLComputeUnits"] == "CPUAndGPU"


def test_calculate_target_feats_length():
    from vcclient.device.coreml_patch import calculate_target_feats_length

    # Table driven tests for standard chunk configurations
    cases = [
        (0.15, 24),
        (0.25, 34),
        (0.30, 40),
        (0.35, 44),
        (0.40, 50),
        (0.50, 60),
    ]
    for chunk_sec, expected_frames in cases:
        frames = calculate_target_feats_length(
            chunk_sec, crossfade_sec=0.05, extra_frame_sec=0.34, sola_search_frame_sec=0.012
        )
        assert frames == expected_frames, f"chunk_sec={chunk_sec} expected {expected_frames}, got {frames}"


def test_patch_rvc_model_for_coreml():
    import onnx
    from onnx import TensorProto, helper

    from vcclient.device.coreml_patch import patch_rvc_model_for_coreml

    # Construct a minimal RVC-like graph with dynamic time dimensions
    feats = helper.make_tensor_value_info("feats", TensorProto.FLOAT, [1, None, 768])
    pitch = helper.make_tensor_value_info("pitch", TensorProto.INT64, [1, None])
    pitchf = helper.make_tensor_value_info("pitchf", TensorProto.FLOAT, [1, None])
    p_len = helper.make_tensor_value_info("p_len", TensorProto.INT64, [None])
    sid = helper.make_tensor_value_info("sid", TensorProto.INT64, [None])
    out = helper.make_tensor_value_info("audio", TensorProto.FLOAT, [None])

    # Simple Identity node
    node = helper.make_node("Identity", inputs=["pitchf"], outputs=["audio"])
    graph = helper.make_graph([node], "test_rvc", [feats, pitch, pitchf, p_len, sid], [out])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])

    patched_bytes = patch_rvc_model_for_coreml(model.SerializeToString(), target_frames=34)
    patched_model = onnx.load_model_from_string(patched_bytes)

    inps = {inp.name: inp for inp in patched_model.graph.input}
    assert inps["feats"].type.tensor_type.shape.dim[0].dim_value == 1
    assert inps["feats"].type.tensor_type.shape.dim[1].dim_value == 34
    assert inps["feats"].type.tensor_type.shape.dim[2].dim_value == 768

    assert inps["pitch"].type.tensor_type.shape.dim[1].dim_value == 34
    assert inps["pitchf"].type.tensor_type.shape.dim[1].dim_value == 34
    assert inps["p_len"].type.tensor_type.shape.dim[0].dim_value == 1
    assert inps["sid"].type.tensor_type.shape.dim[0].dim_value == 1


def test_device_config_create_session_coreml_two_tier(monkeypatch: pytest.MonkeyPatch):
    from onnx import TensorProto, helper

    dev = DeviceConfig(
        id=2,
        canonical_id="coreml:gpu:0",
        provider="coreml",
        device_index=0,
        device_type="GPU",
        name="[CoreML] Apple M2 (GPU + CPU)",
        metadata={"compute_units": "CPUAndGPU"},
    )
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["CoreMLExecutionProvider", "CPUExecutionProvider"])

    feats = helper.make_tensor_value_info("feats", TensorProto.FLOAT, [1, None, 768])
    pitchf = helper.make_tensor_value_info("pitchf", TensorProto.FLOAT, [1, None])
    out = helper.make_tensor_value_info("audio", TensorProto.FLOAT, [None])
    node = helper.make_node("Identity", inputs=["pitchf"], outputs=["audio"])
    graph = helper.make_graph([node], "test_rvc", [feats, pitchf], [out])
    model_bytes = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)]).SerializeToString()

    recorded_options = []

    class DummySession:
        def __init__(self, path_or_bytes, providers=None, provider_options=None, sess_options=None):
            recorded_options.append((providers, provider_options))

        def get_providers(self):
            return ["CoreMLExecutionProvider", "CPUExecutionProvider"]

    monkeypatch.setattr(ort, "InferenceSession", DummySession)

    # 1. Tier 1: target_frames=24 * 400 = 9600 <= 16384 -> MLProgram
    dev.create_session(model_bytes, patch_type="rvc", target_frames=24, upsample_rate=400)
    assert len(recorded_options) == 1
    providers, opts = recorded_options[-1]
    assert opts[0]["ModelFormat"] == "MLProgram"
    assert opts[0]["RequireStaticInputShapes"] == "1"
    assert "frames_24" in opts[0]["ModelCacheDirectory"]

    # 2. Tier 2: target_frames=60 * 400 = 24000 > 16384 -> NeuralNetwork fallback
    dev.create_session(model_bytes, patch_type="rvc", target_frames=60, upsample_rate=400)
    assert len(recorded_options) == 2
    providers2, opts2 = recorded_options[-1]
    assert opts2[0]["ModelFormat"] == "NeuralNetwork"
    assert opts2[0]["RequireStaticInputShapes"] == "0"
    assert "dynamic" in opts2[0]["ModelCacheDirectory"]


def test_rvc_inferencer_static_shape_padding_and_slicing():
    import numpy as np

    from vcclient.voice_changer.voice_change_manager.inferencer.rvc_inferencer_onnx_f0 import RVCInferencerOnnxF0
    from vcclient.voice_changer.voice_change_manager.inferencer.rvc_inferencer_onnx_nof0 import RVCInferencerOnnxNoF0

    class MockSession:
        def __init__(self):
            self.last_inputs = {}

        def run(self, output_names, input_feed, run_options=None):
            self.last_inputs = input_feed
            return [np.zeros(100, dtype=np.float32)]

    # Test F0 inferencer
    inf_f0 = RVCInferencerOnnxF0()
    inf_f0.onnx_session = MockSession()
    inf_f0.isHalf = False
    inf_f0.target_frames = 30
    inf_f0.inferencer_type_version = "v2.2"

    # Case 1: feats shorter than target_frames (e.g. 25 frames) -> zero padding to 30
    feats_short = np.ones((1, 25, 768), dtype=np.float32)
    pitch_short = np.ones((1, 25), dtype=np.int64)
    pitchf_short = np.ones((1, 25), dtype=np.float32)
    inf_f0.infer(
        feats_short,
        np.array([25]),
        pitch_short,
        pitchf_short,
        np.array([0]),
    )
    assert inf_f0.onnx_session.last_inputs["feats"].shape == (1, 30, 768)
    assert inf_f0.onnx_session.last_inputs["pitch"].shape == (1, 30)
    assert inf_f0.onnx_session.last_inputs["pitchf"].shape == (1, 30)

    # Case 2: feats longer than target_frames (e.g. 35 frames) -> slice to 30
    feats_long = np.ones((1, 35, 768), dtype=np.float32)
    pitch_long = np.ones((1, 35), dtype=np.int64)
    pitchf_long = np.ones((1, 35), dtype=np.float32)
    inf_f0.infer(
        feats_long,
        np.array([35]),
        pitch_long,
        pitchf_long,
        np.array([0]),
    )
    assert inf_f0.onnx_session.last_inputs["feats"].shape == (1, 30, 768)
    assert inf_f0.onnx_session.last_inputs["pitch"].shape == (1, 30)
    assert inf_f0.onnx_session.last_inputs["pitchf"].shape == (1, 30)

    # Test NoF0 inferencer
    inf_nof0 = RVCInferencerOnnxNoF0()
    inf_nof0.onnx_session = MockSession()
    inf_nof0.isHalf = False
    inf_nof0.target_frames = 20
    inf_nof0.inferencer_type_version = "v2.2"

    inf_nof0.infer(
        feats_short,
        np.array([25]),
        pitch_short,
        pitchf_short,
        np.array([0]),
    )
    assert inf_nof0.onnx_session.last_inputs["feats"].shape == (1, 20, 768)
