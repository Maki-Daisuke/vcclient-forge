from __future__ import annotations

from . import providers
from .data_types import DeviceConfig
from .device_manager import (
    find_openvino_ep_device,
    get_cuda_info,
    get_device,
    get_device_catalog,
    get_driver_and_cuda_version,
    get_gpu_info,
    is_cuda_available,
    is_openvino_available,
    reload,
    reload_device_catalog,
    reload_gpu_devices,
    resolve_legacy_device_id,
)
from .openvino_patch import (
    patch_rmvpe_model_for_openvino,
    patch_rvc_model_for_openvino,
)
from .runtime_env import setup_runtime_env

__all__ = [
    "DeviceConfig",
    "find_openvino_ep_device",
    "get_cuda_info",
    "get_device",
    "get_device_catalog",
    "get_driver_and_cuda_version",
    "get_gpu_info",
    "is_cuda_available",
    "is_openvino_available",
    "patch_rmvpe_model_for_openvino",
    "patch_rvc_model_for_openvino",
    "providers",
    "reload",
    "reload_device_catalog",
    "reload_gpu_devices",
    "resolve_legacy_device_id",
    "setup_runtime_env",
]
