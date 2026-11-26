from __future__ import annotations

from . import providers
from .coreml_patch import (
    COREML_CONV_MEMORY_LIMIT,
    calculate_target_feats_length,
    patch_rvc_model_for_coreml,
)
from .data_types import DeviceConfig
from .device_manager import (
    find_openvino_ep_device,
    find_webgpu_ep_device,
    get_device,
    get_device_catalog,
    is_cuda_available,
    is_openvino_available,
    is_webgpu_available,
    reload_device_catalog,
)
from .openvino_patch import (
    patch_rmvpe_model_for_openvino,
    patch_rvc_model_for_openvino,
)
from .runtime_env import setup_runtime_env

__all__ = [
    "COREML_CONV_MEMORY_LIMIT",
    "DeviceConfig",
    "calculate_target_feats_length",
    "find_openvino_ep_device",
    "find_webgpu_ep_device",
    "get_device",
    "get_device_catalog",
    "is_cuda_available",
    "is_openvino_available",
    "is_webgpu_available",
    "patch_rmvpe_model_for_openvino",
    "patch_rvc_model_for_coreml",
    "patch_rvc_model_for_openvino",
    "providers",
    "reload_device_catalog",
    "setup_runtime_env",
]
