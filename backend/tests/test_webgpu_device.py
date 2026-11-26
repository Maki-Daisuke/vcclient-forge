from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from vcclient.device.data_types import DeviceConfig
from vcclient.device.device_manager import find_webgpu_ep_device, reload_device_catalog
from vcclient.device.providers.openvino import _is_discrete_gpu
from vcclient.device.providers.webgpu import (
    _VK_PHYSICAL_DEVICE_TYPE_CPU,
    _VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU,
    _VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU,
    configure_webgpu_session_options,
    detect_webgpu_devices,
)


def test_detect_webgpu_devices_orders_and_filters_software(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("vcclient.device.providers.webgpu.is_webgpu_available", lambda: True)
    monkeypatch.setattr("vcclient.device.providers.webgpu.find_webgpu_ep_device", lambda: MagicMock())
    monkeypatch.delenv("VCCLIENT_WEBGPU_ALLOW_SOFTWARE", raising=False)

    # Deliberately return CPU (llvmpipe), integrated GPU, and discrete GPU out of order.
    raw_vulkan = [
        {
            "loader_index": 0,
            "name": "llvmpipe (LLVM 20.1.2, 256 bits)",
            "vk_device_type": _VK_PHYSICAL_DEVICE_TYPE_CPU,
            "vendor_id": 0x10005,
            "vk_device_id": 0x0000,
            "vram_bytes": 16_000_000_000,
        },
        {
            "loader_index": 1,
            "name": "AMD Radeon Graphics (RADV GFX1150)",
            "vk_device_type": _VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU,
            "vendor_id": 0x1002,
            "vk_device_id": 0x150E,
            "vram_bytes": 512_000_000,
        },
        {
            "loader_index": 2,
            "name": "AMD Radeon RX 7900 XTX (RADV NAVI31)",
            "vk_device_type": _VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU,
            "vendor_id": 0x1002,
            "vk_device_id": 0x744C,
            "vram_bytes": 24_000_000_000,
        },
    ]
    monkeypatch.setattr(
        "vcclient.device.providers.webgpu.enumerate_vulkan_physical_devices",
        lambda: raw_vulkan,
    )

    devices = detect_webgpu_devices()
    assert [(d.canonical_id, d.device_index, d.name, d.adapter_ram) for d in devices] == [
        ("webgpu:0", 0, "[WebGPU] AMD Radeon RX 7900 XTX (RADV NAVI31)", 24_000_000_000),
        ("webgpu:1", 1, "[WebGPU] AMD Radeon Graphics (RADV GFX1150)", 512_000_000),
    ]
    assert devices[0].metadata["vulkan_device_type"] == "DISCRETE_GPU"
    assert devices[0].metadata["vendor_id"] == "0x1002"
    assert [d.metadata["discrete"] for d in devices] == [True, False]

    # OpenVINO GPUs on Linux learn discreteness by matching PCI IDs against Vulkan.
    monkeypatch.setattr("sys.platform", "linux")
    assert _is_discrete_gpu(SimpleNamespace(metadata={}, vendor_id=0x1002, device_id=0x744C))
    assert not _is_discrete_gpu(SimpleNamespace(metadata={}, vendor_id=0x1002, device_id=0x150E))
    assert _is_discrete_gpu(SimpleNamespace(metadata={"Discrete": "1"}, vendor_id=0, device_id=0))

    # Opt-in env exposes software renderer at the end with matching Dawn adapterIndex=2.
    monkeypatch.setenv("VCCLIENT_WEBGPU_ALLOW_SOFTWARE", "1")
    with_software = detect_webgpu_devices()
    assert [d.device_index for d in with_software] == [0, 1, 2]
    assert with_software[2].name == "[WebGPU] llvmpipe (LLVM 20.1.2, 256 bits)"
    assert with_software[2].metadata["vulkan_device_type"] == "CPU"


def test_detect_webgpu_devices_returns_empty_outside_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Windows")
    assert detect_webgpu_devices() == []


def test_webgpu_provider_resolution_and_session_options(monkeypatch: pytest.MonkeyPatch) -> None:
    dev = DeviceConfig(
        id=1,
        canonical_id="webgpu:1",
        provider="webgpu",
        device_index=1,
        device_type="GPU",
        name="[WebGPU] AMD Radeon RX 7900 XTX",
    )

    monkeypatch.setattr("vcclient.device.providers.webgpu.is_webgpu_available", lambda: True)
    providers, opts = dev._resolve_provider()
    assert providers == ["WebGpuExecutionProvider", "CPUExecutionProvider"]

    monkeypatch.setattr("vcclient.device.providers.webgpu.is_webgpu_available", lambda: False)
    fb_providers, _ = dev._resolve_provider()
    assert fb_providers == ["CPUExecutionProvider"]

    ep_dev = SimpleNamespace(ep_name="WebGpuExecutionProvider")
    monkeypatch.setattr("onnxruntime.get_ep_devices", lambda: [ep_dev])
    assert find_webgpu_ep_device() is ep_dev

    so = MagicMock()
    configure_webgpu_session_options(so, device=dev)
    so.add_provider_for_devices.assert_called_once_with(
        [ep_dev],
        {"adapterIndex": "1", "powerPreference": "high-performance"},
    )


def test_device_catalog_includes_webgpu_on_linux() -> None:
    mock_webgpu = [
        DeviceConfig(
            id=0,
            canonical_id="webgpu:0",
            provider="webgpu",
            device_index=0,
            device_type="GPU",
            name="[WebGPU] AMD Radeon RX 7800 XT",
            adapter_ram=16_000_000_000,
        )
    ]

    with (
        patch("vcclient.device.device_manager.is_cuda_available", return_value=False),
        patch("platform.system", return_value="Linux"),
        patch("vcclient.device.device_manager.is_openvino_available", return_value=False),
        patch("vcclient.device.device_manager.is_webgpu_available", return_value=True),
        patch("vcclient.device.providers.webgpu.detect_webgpu_devices", return_value=mock_webgpu),
    ):
        catalog = reload_device_catalog()
        assert [d.canonical_id for d in catalog] == ["cpu", "webgpu:0"]
        assert catalog[1].id == 1
        assert catalog[1].provider == "webgpu"
        assert catalog[1].adapter_ram == 16_000_000_000


def test_device_config_create_session_uses_configured_webgpu_options(monkeypatch: pytest.MonkeyPatch) -> None:
    dev = DeviceConfig(
        id=1,
        canonical_id="webgpu:0",
        provider="webgpu",
        device_index=0,
        device_type="GPU",
        name="[WebGPU] AMD Radeon RX 7800 XT",
    )
    ep_dev = SimpleNamespace(ep_name="WebGpuExecutionProvider")
    monkeypatch.setattr("vcclient.device.providers.webgpu.is_webgpu_available", lambda: True)
    monkeypatch.setattr("onnxruntime.get_ep_devices", lambda: [ep_dev])

    mock_so = MagicMock()
    mock_so.has_providers.return_value = True
    mock_session = MagicMock()
    mock_session.get_providers.return_value = ["WebGpuExecutionProvider", "CPUExecutionProvider"]

    with patch("onnxruntime.InferenceSession", return_value=mock_session) as mock_cls:
        sess, providers, _opts = dev.create_session("dummy.onnx", so=mock_so)
        assert sess is mock_session
        assert providers == ["WebGpuExecutionProvider", "CPUExecutionProvider"]
        mock_so.add_provider_for_devices.assert_called_once_with(
            [ep_dev],
            {"adapterIndex": "0", "powerPreference": "high-performance"},
        )
        # Must pass sess_options without overriding providers/provider_options kwargs.
        mock_cls.assert_called_once_with("dummy.onnx", sess_options=mock_so)
