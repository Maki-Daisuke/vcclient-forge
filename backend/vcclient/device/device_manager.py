from __future__ import annotations

import platform
from typing import Any

from vcclient.logger import logger

from . import providers
from .data_types import DeviceConfig, DeviceType

# --- Hardware Detection & GPU Device Management ---

_device_catalog: list[DeviceConfig] = []


def reload_device_catalog() -> list[DeviceConfig]:
    """Discover available execution providers and construct sequential DeviceConfig catalog."""
    global _device_catalog
    catalog: list[DeviceConfig] = []

    # 1. Index 0 is strictly CPU
    catalog.append(
        DeviceConfig(
            id=0,
            canonical_id="cpu",
            provider="cpu",
            device_index=0,
            device_type="CPU",
            name="CPU",
            adapter_ram=0,
        )
    )

    # 2. NVIDIA GPUs (CUDA)
    if is_cuda_available():
        nvidia_gpus = providers.cuda.detect_nvidia_gpus()
        for g in nvidia_gpus:
            catalog.append(
                DeviceConfig(
                    id=len(catalog),
                    canonical_id=f"cuda:{g.device_id_int}",
                    provider="cuda",
                    device_index=g.device_id_int,
                    device_type="GPU",
                    name=g.name,
                    adapter_ram=g.adapter_ram,
                )
            )

    # 3. DirectML (Windows) / CoreML (macOS)
    system = platform.system()
    if system == "Windows":
        sys_gpus = providers.directml.detect_windows_gpus()
        for g in sys_gpus:
            catalog.append(
                DeviceConfig(
                    id=len(catalog),
                    canonical_id=f"dml:{g.device_id_int}",
                    provider="directml",
                    device_index=g.device_id_int,
                    device_type="GPU",
                    name=g.name,
                    adapter_ram=g.adapter_ram,
                    metadata={"discrete": g.discrete},
                )
            )
    elif system == "Darwin":
        sys_gpus = providers.coreml.detect_macos_gpus()
        for g in sys_gpus:
            is_ane = g.device_id_int % 2 == 0
            compute_units = "ALL" if is_ane else "CPUAndGPU"
            dtype: DeviceType = "NPU" if is_ane else "GPU"
            canonical_id = f"coreml:ane:{g.device_id_int // 2}" if is_ane else f"coreml:gpu:{g.device_id_int // 2}"
            catalog.append(
                DeviceConfig(
                    id=len(catalog),
                    canonical_id=canonical_id,
                    provider="coreml",
                    device_index=g.device_id_int,
                    device_type=dtype,
                    name=g.name,
                    adapter_ram=g.adapter_ram,
                    metadata={"compute_units": compute_units},
                )
            )

    # 4. OpenVINO (Windows / Linux)
    if is_openvino_available():
        try:
            ov_devices = providers.openvino.detect_openvino_devices()
            for dev in ov_devices:
                catalog.append(
                    DeviceConfig(
                        id=len(catalog),
                        canonical_id=dev.canonical_id,
                        provider="openvino",
                        device_index=dev.device_index,
                        device_type=dev.device_type,
                        name=dev.name,
                        adapter_ram=dev.adapter_ram,
                        metadata=dev.metadata,
                    )
                )
        except Exception as e:
            logger.warning("OpenVINO detection failed: %s", e)

    # 5. WebGPU (Linux Vulkan: AMD / Intel / NVIDIA)
    if system == "Linux":
        try:
            for dev in providers.webgpu.detect_webgpu_devices():
                catalog.append(dev.model_copy(update={"id": len(catalog)}))
        except Exception as e:
            logger.warning("WebGPU detection failed: %s", e)

    _device_catalog = catalog
    logger.info(
        "Device catalog initialized with %s targets: %s",
        len(_device_catalog),
        [d.canonical_id for d in _device_catalog],
    )
    return _device_catalog


def get_device_catalog() -> list[DeviceConfig]:
    """Return active device catalog, reloading if empty."""
    if not _device_catalog:
        reload_device_catalog()
    return _device_catalog


def get_device(device_id: int) -> DeviceConfig:
    """Retrieve DeviceConfig by catalog index in O(1) time."""
    catalog = get_device_catalog()
    if 0 <= device_id < len(catalog):
        return catalog[device_id]
    # Negative values (e.g. legacy default -1) or out-of-bounds indices fall back to CPU (Index 0)
    return catalog[0]


def is_cuda_available() -> bool:
    """Check if CUDAExecutionProvider is available in the current runtime environment."""
    return providers.cuda.is_cuda_available()


# --- ONNX Runtime Execution Provider & Session Management ---


def is_openvino_available() -> bool:
    """Check if OpenVINOExecutionProvider is available in the current runtime environment."""
    return providers.openvino.is_openvino_available()


def find_openvino_ep_device(
    preferred_type: str = "GPU",
    preferred_ov_device: str | None = None,
) -> Any | None:
    """Find the OpenVINO EP device matching an exact ov_device or preferred device type."""
    return providers.openvino.find_openvino_ep_device(
        preferred_type=preferred_type,
        preferred_ov_device=preferred_ov_device,
    )


def is_webgpu_available() -> bool:
    """Check if WebGpuExecutionProvider is available in the current runtime environment."""
    return providers.webgpu.is_webgpu_available()


def find_webgpu_ep_device() -> Any | None:
    """Return the registered WebGpuExecutionProvider EP device if available."""
    return providers.webgpu.find_webgpu_ep_device()
