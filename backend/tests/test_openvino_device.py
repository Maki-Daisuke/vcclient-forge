import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import onnx
import onnxruntime as ort
import pytest
from onnx import TensorProto, helper

from vcclient.voice_changer.gpu_device_manager.gpu_device_manager import GPUDeviceManager
from vcclient.voice_changer.voice_change_manager.device_manager.device_manager import DeviceManager
from vcclient.voice_changer.voice_change_manager.inferencer.onnx_patch import (
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


def test_device_manager_openvino_provider_configuration(monkeypatch: pytest.MonkeyPatch):
    dev_mgr = DeviceManager.get_instance()

    # 1. When OpenVINO is available
    monkeypatch.setattr(DeviceManager, "is_openvino_available", classmethod(lambda cls: True))
    providers, provider_options = dev_mgr.get_onnx_execution_provider(OPENVINO_GPU_DEVICE_ID)

    assert "OpenVINOExecutionProvider" in providers
    assert "CPUExecutionProvider" in providers
    assert len(provider_options) == 2
    assert provider_options[0]["device_type"] == "GPU"
    assert "EXECUTION_MODE_HINT" in provider_options[0]["load_config"]
    assert provider_options[0]["cache_dir"] == str(OpenVinoCacheDir.resolve())

    # 2. When OpenVINO is unavailable, fallback safely to CPU (even if DirectML is present)
    monkeypatch.setattr(DeviceManager, "is_openvino_available", classmethod(lambda cls: False))
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["DmlExecutionProvider", "CPUExecutionProvider"])
    providers_fallback, _ = dev_mgr.get_onnx_execution_provider(OPENVINO_GPU_DEVICE_ID)
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
    selected = DeviceManager._find_openvino_ep_device(preferred_type="GPU")
    assert selected is gpu_dev


def test_device_manager_configure_session_options():
    dev_mgr = DeviceManager.get_instance()
    so = ort.SessionOptions()

    # OpenVINO EP should disable graph optimization
    dev_mgr.configure_session_options(so, ["OpenVINOExecutionProvider", "CPUExecutionProvider"])
    assert so.graph_optimization_level == ort.GraphOptimizationLevel.ORT_DISABLE_ALL

    # CPU or CUDA EP should not force ORT_DISABLE_ALL
    so2 = ort.SessionOptions()
    dev_mgr.configure_session_options(so2, ["CPUExecutionProvider"])
    assert so2.graph_optimization_level != ort.GraphOptimizationLevel.ORT_DISABLE_ALL


def test_gpu_device_manager_openvino_device(monkeypatch: pytest.MonkeyPatch):
    gpu_mgr = GPUDeviceManager.get_instance()

    # When OpenVINO is available
    monkeypatch.setattr(DeviceManager, "is_openvino_available", classmethod(lambda cls: True))
    info_list = gpu_mgr.reload()
    device_ids = [info.device_id_int for info in info_list]
    assert OPENVINO_GPU_DEVICE_ID in device_ids
    openvino_info = next(info for info in info_list if info.device_id_int == OPENVINO_GPU_DEVICE_ID)
    assert openvino_info.name == "OpenVINO (GPU)"
    assert openvino_info.device_id == "openvino_gpu"

    # When OpenVINO is unavailable
    monkeypatch.setattr(DeviceManager, "is_openvino_available", classmethod(lambda cls: False))
    info_list_no_ov = gpu_mgr.reload()
    device_ids_no_ov = [info.device_id_int for info in info_list_no_ov]
    assert OPENVINO_GPU_DEVICE_ID not in device_ids_no_ov
