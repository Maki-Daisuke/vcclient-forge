import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import onnx
import onnxruntime as ort
import pytest
from onnx import TensorProto, helper

from vcclient.device import (
    configure_session_options,
    create_inference_session,
    find_openvino_ep_device,
    get_onnx_execution_provider,
    reload_gpu_devices,
)
from vcclient.device import device_manager as dm_module
from vcclient.voice_changer.voice_change_manager.inferencer.onnx_patch import (
    patch_rmvpe_model_for_openvino,
    patch_rvc_model_for_openvino,
    verify_3d_to_4d_resize_parity,
)
from vcclient.voice_changer.voice_changer_const import (
    OPENVINO_AUTO_DEVICE_ID,
    OPENVINO_GPU_DEVICE_ID,
    OpenVinoCacheDir,
    SettingsDir,
)


def test_openvino_device_constants():
    assert OPENVINO_GPU_DEVICE_ID == 1000
    assert OPENVINO_AUTO_DEVICE_ID == OPENVINO_GPU_DEVICE_ID
    assert OpenVinoCacheDir.name == "openvino_cache"
    assert OpenVinoCacheDir.exists()
    assert OpenVinoCacheDir != SettingsDir / "openvino_cache"
    assert Path(tempfile.gettempdir()) in OpenVinoCacheDir.parents


def test_3d_to_4d_resize_parity():
    # Verify parity between 3D linear resize and 4D unsqueeze+resize+squeeze
    for scale in [2.0, 4.0]:
        diff = verify_3d_to_4d_resize_parity(scale)
        assert diff < 1e-5


def test_patch_rvc_model_for_openvino_detects_and_patches():
    # Build a minimal synthetic ONNX model with a 3D linear Resize (simulating SineGen)
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 1, 10])
    scales = helper.make_tensor("scales", TensorProto.FLOAT, [3], [1.0, 1.0, 2.0])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 1, 20])

    resize_node = helper.make_node(
        "Resize",
        inputs=["x", "", "scales"],
        outputs=["y"],
        mode="linear",
        coordinate_transformation_mode="align_corners",
    )

    graph = helper.make_graph([resize_node], "test_graph", [x], [y], [scales])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9)
    model_bytes = model.SerializeToString()

    patched_bytes = patch_rvc_model_for_openvino(model_bytes)
    assert patched_bytes != model_bytes

    patched_model = onnx.load_model_from_string(patched_bytes)
    op_types = [node.op_type for node in patched_model.graph.node]
    assert "Unsqueeze" in op_types
    assert "Resize" in op_types
    assert "Squeeze" in op_types


def test_patch_rmvpe_model_for_openvino_supplies_min_bound():
    # Build a minimal synthetic ONNX model with a Clip node having empty min
    x = helper.make_tensor_value_info("x", TensorProto.INT64, [1, 5])
    max_val = helper.make_tensor("max_val", TensorProto.INT64, [], [360])
    y = helper.make_tensor_value_info("y", TensorProto.INT64, [1, 5])

    clip_node = helper.make_node(
        "Clip",
        inputs=["x", "", "max_val"],
        outputs=["y"],
        name="/rmvpe/Clip_1",
    )

    graph = helper.make_graph([clip_node], "test_graph", [x], [y], [max_val])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9)
    model_bytes = model.SerializeToString()

    patched_bytes = patch_rmvpe_model_for_openvino(model_bytes)
    assert patched_bytes != model_bytes

    patched_model = onnx.load_model_from_string(patched_bytes)
    patched_clip = next(node for node in patched_model.graph.node if node.op_type == "Clip")
    assert patched_clip.input[1] != ""
    assert patched_clip.input[1] == "/rmvpe/Clip_1_min_zero"

    init_names = [init.name for init in patched_model.graph.initializer]
    assert "/rmvpe/Clip_1_min_zero" in init_names


def test_device_manager_openvino_provider_configuration(monkeypatch: pytest.MonkeyPatch):
    # 1. When OpenVINO is available
    monkeypatch.setattr(dm_module, "is_openvino_available", lambda: True)
    providers, provider_options = get_onnx_execution_provider(OPENVINO_GPU_DEVICE_ID)

    assert "OpenVINOExecutionProvider" in providers
    assert "CPUExecutionProvider" in providers
    assert len(provider_options) == 2
    assert provider_options[0]["device_type"] == "GPU"
    assert "EXECUTION_MODE_HINT" in provider_options[0]["load_config"]
    assert provider_options[0]["cache_dir"] == str(OpenVinoCacheDir.resolve())

    # 2. When OpenVINO is unavailable, fallback safely to CPU (even if DirectML is present)
    monkeypatch.setattr(dm_module, "is_openvino_available", lambda: False)
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["DmlExecutionProvider", "CPUExecutionProvider"])
    providers_fallback, _ = get_onnx_execution_provider(OPENVINO_GPU_DEVICE_ID)
    assert "OpenVINOExecutionProvider" not in providers_fallback
    assert "DmlExecutionProvider" not in providers_fallback
    assert "CPUExecutionProvider" in providers_fallback


def test_device_manager_find_openvino_ep_device_prioritizes_gpu(monkeypatch: pytest.MonkeyPatch):
    @dataclass
    class DummyDevice:
        type: str

    @dataclass
    class DummyEPDevice:
        ep_name: str
        device: DummyDevice
        ep_metadata: dict[str, Any]

    npu_dev = DummyEPDevice(
        ep_name="OpenVINOExecutionProvider", device=DummyDevice(type="NPU"), ep_metadata={"ov_device": "NPU"}
    )
    gpu_dev = DummyEPDevice(
        ep_name="OpenVINOExecutionProvider", device=DummyDevice(type="GPU"), ep_metadata={"ov_device": "GPU"}
    )
    cpu_dev = DummyEPDevice(
        ep_name="OpenVINOExecutionProvider", device=DummyDevice(type="CPU"), ep_metadata={"ov_device": "CPU"}
    )

    # Even if NPU is first in list (as on Lunar Lake), GPU must be selected
    monkeypatch.setattr(ort, "get_ep_devices", lambda: [npu_dev, gpu_dev, cpu_dev])
    selected = find_openvino_ep_device(preferred_type="GPU")
    assert selected is gpu_dev


def test_device_manager_configure_session_options():
    so = ort.SessionOptions()

    # OpenVINO EP should disable graph optimization
    configure_session_options(so, ["OpenVINOExecutionProvider", "CPUExecutionProvider"])
    assert so.graph_optimization_level == ort.GraphOptimizationLevel.ORT_DISABLE_ALL

    # CPU or CUDA EP should not force ORT_DISABLE_ALL
    so2 = ort.SessionOptions()
    configure_session_options(so2, ["CPUExecutionProvider"])
    assert so2.graph_optimization_level != ort.GraphOptimizationLevel.ORT_DISABLE_ALL


def test_gpu_device_manager_openvino_device(monkeypatch: pytest.MonkeyPatch):
    # When OpenVINO is available
    monkeypatch.setattr(dm_module, "is_openvino_available", lambda: True)
    monkeypatch.setattr(dm_module.providers.openvino, "is_openvino_available", lambda: True)
    info_list = reload_gpu_devices()
    device_ids = [info.device_id_int for info in info_list]
    assert OPENVINO_GPU_DEVICE_ID in device_ids
    openvino_info = next(info for info in info_list if info.device_id_int == OPENVINO_GPU_DEVICE_ID)
    assert openvino_info.name.startswith("[OpenVINO]")
    assert openvino_info.device_id == "openvino_gpu"

    # When OpenVINO is unavailable
    monkeypatch.setattr(dm_module, "is_openvino_available", lambda: False)
    monkeypatch.setattr(dm_module.providers.openvino, "is_openvino_available", lambda: False)
    info_list_no_ov = reload_gpu_devices()
    device_ids_no_ov = [info.device_id_int for info in info_list_no_ov]
    assert OPENVINO_GPU_DEVICE_ID not in device_ids_no_ov


def test_device_manager_create_inference_session_avoids_provider_argument_collision(monkeypatch: pytest.MonkeyPatch):
    # Minimal dummy ONNX model bytes
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 2])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 2])
    node = helper.make_node("Identity", inputs=["x"], outputs=["y"])
    graph = helper.make_graph([node], "test", [x], [y])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9)
    model_bytes = model.SerializeToString()

    # Create session directly via module function
    sess = create_inference_session(
        model_bytes,
        providers=["CPUExecutionProvider"],
    )
    assert sess is not None
    assert "CPUExecutionProvider" in sess.get_providers()

    captured_kwargs: dict[str, Any] = {}

    class DummySession:
        def __init__(self, *args, **kwargs):
            captured_kwargs["args"] = args
            captured_kwargs["kwargs"] = kwargs

        def get_providers(self):
            return ["OpenVINOExecutionProvider", "CPUExecutionProvider"]

    monkeypatch.setattr(ort, "InferenceSession", DummySession)

    # 1. When so has providers (mocking add_provider_for_devices having run)
    monkeypatch.setattr(ort.SessionOptions, "has_providers", lambda self: True)
    session = create_inference_session(
        model_bytes,
        providers=["OpenVINOExecutionProvider", "CPUExecutionProvider"],
        provider_options=[{}, {}],
    )
    assert isinstance(session, DummySession)
    assert "providers" not in captured_kwargs["kwargs"]
    assert "provider_options" not in captured_kwargs["kwargs"]
    assert "sess_options" in captured_kwargs["kwargs"]

    # 2. When so does NOT have providers (standard CPU/CUDA EP path)
    monkeypatch.setattr(ort.SessionOptions, "has_providers", lambda self: False)
    session2 = create_inference_session(
        model_bytes,
        providers=["CPUExecutionProvider"],
        provider_options=[{}],
    )
    assert isinstance(session2, DummySession)
    assert captured_kwargs["kwargs"]["providers"] == ["CPUExecutionProvider"]
    assert captured_kwargs["kwargs"]["provider_options"] == [{}]
    assert "sess_options" in captured_kwargs["kwargs"]
