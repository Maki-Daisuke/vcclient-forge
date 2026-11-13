import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnxruntime as ort
import pytest
from onnx import TensorProto, helper, numpy_helper

from vcclient.device import (
    DeviceConfig,
    find_openvino_ep_device,
    reload_gpu_devices,
)
from vcclient.device import device_manager as dm_module
from vcclient.device.openvino_patch import (
    patch_rmvpe_model_for_openvino,
    patch_rvc_model_for_openvino,
)
from vcclient.device.providers.openvino import OpenVinoCacheDir
from vcclient.voice_changer.voice_changer_const import SettingsDir


def test_openvino_device_constants():
    assert OpenVinoCacheDir.name == "openvino_cache"
    assert OpenVinoCacheDir.exists()
    assert OpenVinoCacheDir != SettingsDir / "openvino_cache"
    assert Path(tempfile.gettempdir()) in OpenVinoCacheDir.parents


def verify_3d_to_4d_resize_parity(scale_factor: float) -> float:
    """Validate numerical equivalence between 3D linear Resize and 4D Unsqueeze+Resize+Squeeze."""
    x_3d = np.linspace(-1.0, 1.0, 16, dtype=np.float32).reshape(1, 1, 16)

    # 1. 3D reference graph
    sc3_init = numpy_helper.from_array(np.array([1.0, 1.0, scale_factor], dtype=np.float32), name="sc3")
    r3 = helper.make_node(
        "Resize",
        ["x3", "", "sc3"],
        ["y3"],
        mode="linear",
        coordinate_transformation_mode="half_pixel",
    )
    g3 = helper.make_graph(
        [r3],
        "ref3d",
        [helper.make_tensor_value_info("x3", onnx.TensorProto.FLOAT, [1, 1, 16])],
        [helper.make_tensor_value_info("y3", onnx.TensorProto.FLOAT, [1, 1, None])],
        [sc3_init],
    )
    m3 = helper.make_model(g3, opset_imports=[helper.make_opsetid("", 18)], ir_version=9)

    # 2. 4D patched graph
    ax_init = numpy_helper.from_array(np.array([2], dtype=np.int64), name="ax")
    sc4_init = numpy_helper.from_array(np.array([1.0, 1.0, 1.0, scale_factor], dtype=np.float32), name="sc4")
    unsq = helper.make_node("Unsqueeze", ["x4", "ax"], ["x4_4d"])
    r4 = helper.make_node(
        "Resize",
        ["x4_4d", "", "sc4"],
        ["y4_4d"],
        mode="linear",
        coordinate_transformation_mode="half_pixel",
    )
    sq = helper.make_node("Squeeze", ["y4_4d", "ax"], ["y4"])
    g4 = helper.make_graph(
        [unsq, r4, sq],
        "patch4d",
        [helper.make_tensor_value_info("x4", onnx.TensorProto.FLOAT, [1, 1, 16])],
        [helper.make_tensor_value_info("y4", onnx.TensorProto.FLOAT, [1, 1, None])],
        [ax_init, sc4_init],
    )
    m4 = helper.make_model(g4, opset_imports=[helper.make_opsetid("", 18)], ir_version=9)

    so = ort.SessionOptions()
    so.log_severity_level = 3
    s3 = ort.InferenceSession(m3.SerializeToString(), so, providers=["CPUExecutionProvider"])
    s4 = ort.InferenceSession(m4.SerializeToString(), so, providers=["CPUExecutionProvider"])

    y3 = s3.run(None, {"x3": x_3d})[0]
    y4 = s4.run(None, {"x4": x_3d})[0]

    max_diff = float(np.max(np.abs(y3 - y4)))
    if max_diff > 1e-5:
        raise ValueError(f"3D-to-4D Resize transformation parity check failed (max diff: {max_diff} > 1e-5)")
    return max_diff


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
    dev_ov = DeviceConfig(
        id=1,
        canonical_id="openvino:gpu:0",
        provider="openvino",
        device_index=0,
        device_type="GPU",
        name="[OpenVINO] Intel Arc",
        metadata={"ov_device": "GPU.0"},
    )

    # 1. When OpenVINO is available
    monkeypatch.setattr("vcclient.device.providers.openvino.is_openvino_available", lambda: True)
    providers, provider_options = dev_ov._resolve_provider()

    assert "OpenVINOExecutionProvider" in providers
    assert "CPUExecutionProvider" in providers
    assert len(provider_options) == 2
    assert provider_options[0]["device_type"] == "GPU.0"
    assert "EXECUTION_MODE_HINT" in provider_options[0]["load_config"]
    assert provider_options[0]["cache_dir"] == str(OpenVinoCacheDir.resolve())

    # 2. When OpenVINO is unavailable, fallback safely to CPU (even if DirectML is present)
    monkeypatch.setattr("vcclient.device.providers.openvino.is_openvino_available", lambda: False)
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["DmlExecutionProvider", "CPUExecutionProvider"])
    providers_fallback, _ = dev_ov._resolve_provider()
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


def test_device_config_configure_session_options():
    dev_ov = DeviceConfig(
        id=1,
        canonical_id="openvino:gpu:0",
        provider="openvino",
        device_index=0,
        device_type="GPU",
        name="[OpenVINO] Intel Arc",
        metadata={"ov_device": "GPU.0"},
    )
    so = dev_ov._configure_session_options()
    assert so.graph_optimization_level == ort.GraphOptimizationLevel.ORT_DISABLE_ALL

    # CPU or CUDA EP should not force ORT_DISABLE_ALL
    dev_cpu = DeviceConfig(id=0, canonical_id="cpu", provider="cpu", device_type="CPU", name="CPU")
    so2 = dev_cpu._configure_session_options()
    assert so2.graph_optimization_level != ort.GraphOptimizationLevel.ORT_DISABLE_ALL


def test_gpu_device_manager_openvino_device(monkeypatch: pytest.MonkeyPatch):
    # When OpenVINO is available
    mock_ov = [
        DeviceConfig(
            id=1,
            canonical_id="openvino:gpu:0",
            provider="openvino",
            device_index=0,
            device_type="GPU",
            name="[OpenVINO] Intel Arc",
            metadata={"ov_device": "GPU.0"},
        )
    ]
    monkeypatch.setattr(dm_module, "is_openvino_available", lambda: True)
    monkeypatch.setattr(dm_module.providers.openvino, "is_openvino_available", lambda: True)
    monkeypatch.setattr(dm_module.providers.openvino, "detect_openvino_devices", lambda: mock_ov)
    info_list = reload_gpu_devices()
    canonical_ids = [info.device_id for info in info_list]
    assert "openvino:gpu:0" in canonical_ids
    openvino_info = next(info for info in info_list if info.device_id == "openvino:gpu:0")
    assert openvino_info.name.startswith("[OpenVINO]")

    # When OpenVINO is unavailable
    monkeypatch.setattr(dm_module, "is_openvino_available", lambda: False)
    monkeypatch.setattr(dm_module.providers.openvino, "is_openvino_available", lambda: False)
    info_list_no_ov = reload_gpu_devices()
    canonical_ids_no_ov = [info.device_id for info in info_list_no_ov]
    assert "openvino:gpu:0" not in canonical_ids_no_ov


def test_device_config_create_session_avoids_provider_argument_collision(monkeypatch: pytest.MonkeyPatch):
    # Minimal dummy ONNX model bytes
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 2])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 2])
    node = helper.make_node("Identity", inputs=["x"], outputs=["y"])
    graph = helper.make_graph([node], "test", [x], [y])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9)
    model_bytes = model.SerializeToString()

    dev_cpu = DeviceConfig(id=0, canonical_id="cpu", provider="cpu", device_type="CPU", name="CPU")

    # Create session directly via DeviceConfig.create_session
    sess, providers, _ = dev_cpu.create_session(model_bytes)
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

    dev_ov = DeviceConfig(
        id=1,
        canonical_id="openvino:gpu:0",
        provider="openvino",
        device_index=0,
        device_type="GPU",
        name="[OpenVINO] Intel Arc",
        metadata={"ov_device": "GPU.0"},
    )
    monkeypatch.setattr("vcclient.device.providers.openvino.is_openvino_available", lambda: True)

    # 1. When so has providers (mocking add_provider_for_devices having run)
    monkeypatch.setattr(ort.SessionOptions, "has_providers", lambda self: True)
    session, _, _ = dev_ov.create_session(model_bytes)
    assert isinstance(session, DummySession)
    assert "providers" not in captured_kwargs["kwargs"]
    assert "provider_options" not in captured_kwargs["kwargs"]
    assert "sess_options" in captured_kwargs["kwargs"]

    # 2. When so does NOT have providers (standard CPU/CUDA EP path)
    monkeypatch.setattr(ort.SessionOptions, "has_providers", lambda self: False)
    session2, _, _ = dev_cpu.create_session(model_bytes)
    assert isinstance(session2, DummySession)
    assert captured_kwargs["kwargs"]["providers"] == ["CPUExecutionProvider"]
    assert "sess_options" in captured_kwargs["kwargs"]


def test_device_config_create_session_cpu_and_openvino_patching(monkeypatch):
    # Minimal ONNX model with a 3D linear Resize (simulating SineGen)
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

    # 1. CPU execution: patch_type="rvc" does NOT patch if OpenVINO is not in providers
    dev_cpu = DeviceConfig(id=0, canonical_id="cpu", provider="cpu", device_type="CPU", name="CPU")
    session, providers, provider_opts = dev_cpu.create_session(model_bytes, patch_type="rvc")
    assert "CPUExecutionProvider" in session.get_providers()
    assert providers == ["CPUExecutionProvider"]

    # 2. OpenVINO execution: patch_type="rvc" applies SineGen patch
    received_payload: list[bytes] = []

    class DummySession:
        def get_providers(self):
            return ["OpenVINOExecutionProvider", "CPUExecutionProvider"]

    def mock_inference_session(payload, **kwargs):
        received_payload.append(payload if isinstance(payload, bytes) else str(payload).encode())
        return DummySession()

    monkeypatch.setattr(ort, "InferenceSession", mock_inference_session)
    monkeypatch.setattr("vcclient.device.providers.openvino.is_openvino_available", lambda: True)
    dev_ov = DeviceConfig(
        id=1,
        canonical_id="openvino:gpu:0",
        provider="openvino",
        device_index=0,
        device_type="GPU",
        name="[OpenVINO] Intel Arc",
        metadata={"ov_device": "GPU.0"},
    )

    session_ov, ov_providers, _ = dev_ov.create_session(model_bytes, patch_type="rvc")
    assert isinstance(session_ov, DummySession)
    assert ov_providers[0] == "OpenVINOExecutionProvider"
    assert len(received_payload) == 1
    assert received_payload[0] != model_bytes  # Patched!

    # Verify patched graph contains Unsqueeze & Squeeze
    patched_model = onnx.load_model_from_string(received_payload[0])
    op_types = [node.op_type for node in patched_model.graph.node]
    assert "Unsqueeze" in op_types
    assert "Squeeze" in op_types


@pytest.mark.parametrize(
    ("device_type", "device_index", "ov_device"),
    [
        ("GPU", 0, "GPU.0"),
        ("GPU", 1, "GPU.1"),
        ("NPU", 0, "NPU"),
    ],
)
def test_openvino_device_selection_and_load_config(
    monkeypatch: pytest.MonkeyPatch,
    device_type: str,
    device_index: int,
    ov_device: str,
):
    import json
    from types import SimpleNamespace

    from vcclient.device.providers.openvino import (
        configure_openvino_session_options,
        resolve_openvino_device_provider,
    )

    gpu0_ep = SimpleNamespace(
        ep_name="OpenVINOExecutionProvider",
        device=SimpleNamespace(type="GPU"),
        ep_metadata={"ov_device": "GPU.0"},
    )
    gpu1_ep = SimpleNamespace(
        ep_name="OpenVINOExecutionProvider",
        device=SimpleNamespace(type="GPU"),
        ep_metadata={"ov_device": "GPU.1"},
    )
    npu_ep = SimpleNamespace(
        ep_name="OpenVINOExecutionProvider",
        device=SimpleNamespace(type="NPU"),
        ep_metadata={"ov_device": "NPU"},
    )
    cpu_ep = SimpleNamespace(
        ep_name="OpenVINOExecutionProvider",
        device=SimpleNamespace(type="CPU"),
        ep_metadata={"ov_device": "CPU"},
    )
    ep_by_name = {"GPU.0": gpu0_ep, "GPU.1": gpu1_ep, "NPU": npu_ep}
    monkeypatch.setattr(ort, "get_ep_devices", lambda: [gpu0_ep, gpu1_ep, npu_ep, cpu_ep])

    # Exact type match without ov_device must also select NPU rather than breaking on first GPU
    assert find_openvino_ep_device(preferred_type="NPU") is npu_ep
    # Non-existent ov_device must return None instead of silently falling back to another device
    assert find_openvino_ep_device(preferred_ov_device="GPU.99") is None

    dev = DeviceConfig(
        id=1 + device_index,
        canonical_id=f"openvino:{device_type.lower()}:{device_index}",
        provider="openvino",
        device_index=device_index,
        device_type=device_type,  # type: ignore[arg-type]
        name=f"[OpenVINO] {ov_device}",
        metadata={"ov_device": ov_device},
    )

    # 1. Provider options path
    _, opts_list = resolve_openvino_device_provider(dev)
    assert opts_list[0]["device_type"] == ov_device
    load_cfg = json.loads(opts_list[0]["load_config"])
    assert set(load_cfg.keys()) == {ov_device}
    assert load_cfg[ov_device]["EXECUTION_MODE_HINT"] == "ACCURACY"
    assert load_cfg[ov_device]["CACHE_DIR"] == str(OpenVinoCacheDir.resolve())

    # 2. SessionOptions.add_provider_for_devices path binds the exact EP device and uses its ov_device key
    captured: dict[str, Any] = {}
    so = SimpleNamespace(
        graph_optimization_level=None,
        add_provider_for_devices=lambda devs, opts: captured.update({"devs": devs, "opts": opts}),
    )
    configure_openvino_session_options(so, device=dev)  # type: ignore[arg-type]
    assert captured["devs"] == [ep_by_name[ov_device]]
    so_load_cfg = json.loads(captured["opts"]["load_config"])
    assert set(so_load_cfg.keys()) == {ov_device}
    assert so_load_cfg[ov_device]["EXECUTION_MODE_HINT"] == "ACCURACY"
    assert so_load_cfg[ov_device]["CACHE_DIR"] == str(OpenVinoCacheDir.resolve())
