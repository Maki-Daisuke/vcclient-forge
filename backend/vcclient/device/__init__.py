from __future__ import annotations

from . import providers
from .data_types import DeviceConfig
from .device_manager import (
    configure_session_options,
    create_inference_session,
    create_pipeline_session,
    find_openvino_ep_device,
    get_cuda_info,
    get_device,
    get_device_catalog,
    get_driver_and_cuda_version,
    get_gpu_info,
    get_onnx_execution_provider,
    is_cuda_available,
    is_openvino_available,
    reload,
    reload_device_catalog,
    reload_gpu_devices,
    resolve_legacy_device_id,
    resolve_provider_for_device,
)
from .openvino_patch import (
    patch_rmvpe_model_for_openvino,
    patch_rvc_model_for_openvino,
)
from .runtime_env import setup_runtime_env

__all__ = [
    "DeviceConfig",
    "configure_session_options",
    "create_inference_session",
    "create_pipeline_session",
    "find_openvino_ep_device",
    "get_cuda_info",
    "get_device",
    "get_device_catalog",
    "get_driver_and_cuda_version",
    "get_gpu_info",
    "get_onnx_execution_provider",
    "is_cuda_available",
    "is_openvino_available",
    "patch_rmvpe_model_for_openvino",
    "patch_rvc_model_for_openvino",
    "providers",
    "reload",
    "reload_device_catalog",
    "reload_gpu_devices",
    "resolve_legacy_device_id",
    "resolve_provider_for_device",
    "setup_runtime_env",
]
