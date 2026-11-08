from __future__ import annotations

from pathlib import Path
from typing import Any

import onnxruntime

from vcclient.logger import logger

from . import providers


def is_openvino_available() -> bool:
    """Check if OpenVINOExecutionProvider is available in the current runtime environment."""
    return providers.openvino.is_openvino_available()


def find_openvino_ep_device(preferred_type: str = "GPU") -> Any | None:
    """Find the most suitable OpenVINO EP device from ort.get_ep_devices()."""
    return providers.openvino.find_openvino_ep_device(preferred_type)


def configure_session_options(
    so: onnxruntime.SessionOptions,
    ep_providers: list[str],
) -> onnxruntime.SessionOptions:
    """Configure SessionOptions with hardware/EP-specific performance and stability flags."""
    if any("openvino" in p.lower() for p in ep_providers):
        providers.openvino.configure_openvino_session_options(so)
    return so


def create_inference_session(
    model_payload: str | bytes | Path,
    providers: list[str],
    provider_options: list[dict] | None = None,
    so: onnxruntime.SessionOptions | None = None,
) -> onnxruntime.InferenceSession:
    if so is None:
        so = onnxruntime.SessionOptions()
        so.log_severity_level = 3
    configure_session_options(so, providers)

    path_or_bytes = str(model_payload) if isinstance(model_payload, Path) else model_payload

    # When SessionOptions has already been configured with providers (e.g. via add_provider_for_devices),
    # passing providers or provider_options to InferenceSession causes ONNX Runtime to override
    # and discard the SessionOptions configuration, leading to silent CPU fallback for dynamic plugins like OpenVINO.
    if hasattr(so, "has_providers") and so.has_providers():
        session = onnxruntime.InferenceSession(path_or_bytes, sess_options=so)
    else:
        session = onnxruntime.InferenceSession(
            path_or_bytes,
            sess_options=so,
            providers=providers,
            provider_options=provider_options,
        )

    name = (
        model_payload.name
        if isinstance(model_payload, Path)
        else (model_payload if isinstance(model_payload, str) else "<bytes>")
    )
    logger.info("ONNX session initialized for %s with active providers: %s", name, session.get_providers())
    return session


def _resolve_onnx_execution_provider(device_id: int) -> tuple[list[str], list[dict[str, Any]]]:
    available_providers = onnxruntime.get_available_providers()
    logger.info("available_providers: %s", available_providers)

    # 1. OpenVINO Execution Provider
    ov_res = providers.openvino.resolve_openvino_provider(device_id, available=is_openvino_available())
    if ov_res is not None:
        return ov_res

    # 2. CUDA Execution Provider
    from vcclient.voice_changer.gpu_device_manager import get_cuda_info, get_gpu_info

    cuda_info = get_cuda_info()
    gpu_info = get_gpu_info()
    cuda_len = len(cuda_info)
    gpu_len = len(gpu_info) - 1
    gpu_num = max(cuda_len, gpu_len)
    logger.info("gpu_num: %s, cuda_len: %s, gpu_len: %s", gpu_num, cuda_len, gpu_len)

    cuda_res = providers.cuda.resolve_cuda_provider(device_id, gpu_num, available_providers)
    if cuda_res is not None:
        return cuda_res

    # 3. DirectML Execution Provider
    dml_res = providers.directml.resolve_directml_provider(device_id, available_providers)
    if dml_res is not None:
        return dml_res

    # 4. CoreML Execution Provider
    coreml_res = providers.coreml.resolve_coreml_provider(device_id, available_providers)
    if coreml_res is not None:
        return coreml_res

    # 5. Default CPU Execution Provider
    return providers.cpu.resolve_cpu_provider()


def get_onnx_execution_provider(device_id: int) -> tuple[list[str], list[dict[str, Any]]]:
    res = _resolve_onnx_execution_provider(device_id)
    logger.info("get_onnx_execution_provider: %s", res)
    return res
