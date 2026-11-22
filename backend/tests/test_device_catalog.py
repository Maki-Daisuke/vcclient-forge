from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from vcclient.device.data_types import DeviceConfig
from vcclient.device.device_manager import (
    get_device,
    get_device_catalog,
    reload_device_catalog,
)
from vcclient.voice_changer.data_types.data_types import GPUInfo


def test_device_config_model_serialization() -> None:
    """Verify DeviceConfig schema and JSON serialization."""
    dev = DeviceConfig(
        id=2,
        canonical_id="openvino:gpu:0",
        provider="openvino",
        device_index=0,
        device_type="GPU",
        name="[OpenVINO] Intel Arc Graphics",
        adapter_ram=0,
        metadata={"ov_device": "GPU.0"},
    )

    dumped = dev.model_dump()
    assert dumped["id"] == 2
    assert dumped["canonical_id"] == "openvino:gpu:0"
    assert "device_id_int" not in dumped
    assert "device_id" not in dumped
    assert not dev.is_cpu()

    # JSON serialization contract check
    json_str = dev.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["id"] == 2
    assert parsed["canonical_id"] == "openvino:gpu:0"
    assert "device_id_int" not in parsed
    assert "device_id" not in parsed

    cpu_dev = DeviceConfig(
        id=0,
        canonical_id="cpu",
        provider="cpu",
        device_index=0,
        device_type="CPU",
        name="CPU",
    )
    assert cpu_dev.is_cpu()


def test_device_catalog_index_0_is_strictly_cpu() -> None:
    """Verify that catalog index 0 is deterministically and unconditionally host CPU."""
    catalog = reload_device_catalog()
    assert len(catalog) >= 1
    cpu = catalog[0]
    assert cpu.id == 0
    assert cpu.canonical_id == "cpu"
    assert cpu.provider == "cpu"
    assert cpu.device_type == "CPU"
    assert cpu.is_cpu()


def test_get_device_bounds_and_fallbacks() -> None:
    """Verify O(1) lookup and out-of-bounds fallback to CPU (index 0)."""
    catalog = get_device_catalog()
    cpu = catalog[0]

    # Valid index 0
    assert get_device(0) == cpu

    # Legacy negative sentinel (-1) -> CPU
    assert get_device(-1) == cpu

    # Extremely high out-of-bounds index -> CPU
    assert get_device(99999) == cpu


def test_catalog_enumeration_with_mock_hardware() -> None:
    """Verify sequential IDs are assigned across heterogeneous backends."""
    mock_nvidia = [
        GPUInfo(name="[CUDA] NVIDIA GeForce RTX 4090", device_id="0", adapter_ram=24000000000, device_id_int=0),
    ]
    mock_ov_devices = [
        DeviceConfig(
            id=0,
            canonical_id="openvino:gpu:0",
            provider="openvino",
            device_index=0,
            device_type="GPU",
            name="[OpenVINO] Intel(R) Arc(TM) 140V GPU",
            metadata={"ov_device": "GPU.0"},
        ),
        DeviceConfig(
            id=0,
            canonical_id="openvino:npu:0",
            provider="openvino",
            device_index=0,
            device_type="NPU",
            name="[OpenVINO] Intel(R) AI Boost",
            metadata={"ov_device": "NPU"},
        ),
    ]

    with (
        patch("vcclient.device.device_manager.is_cuda_available", return_value=True),
        patch("vcclient.device.providers.cuda.detect_nvidia_gpus", return_value=mock_nvidia),
        patch("platform.system", return_value="Windows"),
        patch("vcclient.device.providers.directml.detect_windows_gpus", return_value=[]),
        patch("vcclient.device.device_manager.is_openvino_available", return_value=True),
        patch("vcclient.device.providers.openvino.detect_openvino_devices", return_value=mock_ov_devices),
    ):
        catalog = reload_device_catalog()
        assert len(catalog) == 4
        assert catalog[0].id == 0
        assert catalog[0].canonical_id == "cpu"
        assert catalog[1].id == 1
        assert catalog[1].canonical_id == "cuda:0"
        assert catalog[2].id == 2
        assert catalog[2].canonical_id == "openvino:gpu:0"
        assert catalog[3].id == 3
        assert catalog[3].canonical_id == "openvino:npu:0"


def test_device_config_resolve_provider() -> None:
    """Verify execution provider options resolved by DeviceConfig._resolve_provider()."""
    cpu_dev = DeviceConfig(id=0, canonical_id="cpu", provider="cpu", device_type="CPU", name="CPU")
    providers, opts = cpu_dev._resolve_provider()
    assert providers == ["CPUExecutionProvider"]
    assert "intra_op_num_threads" in opts[0]

    cuda_dev = DeviceConfig(
        id=1,
        canonical_id="cuda:0",
        provider="cuda",
        device_index=0,
        device_type="GPU",
        name="NVIDIA GPU",
    )
    with patch("onnxruntime.get_available_providers", return_value=["CUDAExecutionProvider", "CPUExecutionProvider"]):
        providers, opts = cuda_dev._resolve_provider()
        assert providers == ["CUDAExecutionProvider"]
        assert opts == [{"device_id": 0}]

    dml_dev = DeviceConfig(
        id=2,
        canonical_id="dml:1",
        provider="directml",
        device_index=1,
        device_type="GPU",
        name="DirectML GPU",
    )
    with patch("onnxruntime.get_available_providers", return_value=["DmlExecutionProvider", "CPUExecutionProvider"]):
        providers, opts = dml_dev._resolve_provider()
        assert providers == ["DmlExecutionProvider", "CPUExecutionProvider"]
        assert opts[0] == {"device_id": 1}

    ov_npu_dev = DeviceConfig(
        id=3,
        canonical_id="openvino:npu:0",
        provider="openvino",
        device_index=0,
        device_type="NPU",
        name="Intel AI Boost",
        metadata={"ov_device": "NPU"},
    )
    with patch("vcclient.device.providers.openvino.is_openvino_available", return_value=True):
        providers, opts = ov_npu_dev._resolve_provider()
        assert providers == ["OpenVINOExecutionProvider", "CPUExecutionProvider"]
        assert opts[0]["device_type"] == "NPU"


def test_device_config_create_session_npu_rvc_fallback() -> None:
    """Verify that NPU target deterministically falls back to CPU for RVC vocoder sessions."""
    npu_dev = DeviceConfig(
        id=3,
        canonical_id="openvino:npu:0",
        provider="openvino",
        device_index=0,
        device_type="NPU",
        name="Intel AI Boost",
        metadata={"ov_device": "NPU"},
    )

    with (
        patch("onnxruntime.InferenceSession") as mock_session_cls,
        patch("vcclient.device.device_manager.get_device_catalog") as mock_catalog,
        patch("vcclient.device.providers.openvino.is_openvino_available", return_value=True),
    ):
        mock_cpu = DeviceConfig(id=0, canonical_id="cpu", provider="cpu", device_type="CPU", name="CPU")
        mock_catalog.return_value = [mock_cpu, npu_dev]
        mock_session = MagicMock()
        mock_session.get_providers.return_value = ["CPUExecutionProvider"]
        mock_session_cls.return_value = mock_session

        # 1. RVC Vocoder on NPU -> CPU fallback via create_session
        sess, providers, opts = npu_dev.create_session(
            model_payload="dummy.onnx",
            patch_type="rvc",
        )
        assert providers == ["CPUExecutionProvider"]

        # 2. RMVPE Pitch Estimator on NPU -> Allowed on NPU via create_session
        import onnx
        from onnx import TensorProto, helper

        x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 2])
        y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 2])
        node = helper.make_node("Identity", inputs=["x"], outputs=["y"])
        graph = helper.make_graph([node], "rmvpe_dummy", [x], [y])
        rmvpe_bytes = onnx.helper.make_model(
            graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9
        ).SerializeToString()

        mock_session.get_providers.return_value = ["OpenVINOExecutionProvider", "CPUExecutionProvider"]
        sess_rmvpe, providers_rmvpe, opts_rmvpe = npu_dev.create_session(
            model_payload=rmvpe_bytes,
            patch_type="rmvpe",
        )
        assert providers_rmvpe == ["OpenVINOExecutionProvider", "CPUExecutionProvider"]


def test_rest_api_compute_devices_returns_catalog() -> None:
    """Verify that GET /api/devices/compute returns DeviceConfig catalog."""
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from vcclient.server.vcserver_rest_api_devices import RestAPIDevices

    app = FastAPI()
    api = RestAPIDevices()
    app.include_router(api.router)

    client = TestClient(app)
    resp = client.get("/api/devices/compute")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    first = data[0]
    assert first["id"] == 0
    assert first["canonical_id"] == "cpu"
    assert "device_id_int" not in first
    assert "device_id" not in first
    assert first["name"] == "CPU"
