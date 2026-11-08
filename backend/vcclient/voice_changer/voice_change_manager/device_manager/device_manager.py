from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Any

import onnxruntime

from vcclient.logger import logger
from vcclient.voice_changer.data_types.data_types import GPUInfo

from . import providers

# --- Hardware Detection & GPU Device Management ---

_gpu_info: list[GPUInfo] = []
_cuda_info: list[GPUInfo] = []
_cuda_available: bool = False


def _detect_linux_gpus() -> list[GPUInfo]:
    gpu_list: list[GPUInfo] = []
    try:
        cmd = ["lspci"]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            idx = 0
            for line in result.stdout.splitlines():
                if "VGA compatible controller" in line or "3D controller" in line:
                    parts = line.split(":", 2)
                    name = parts[-1].strip() if len(parts) >= 3 else line
                    gpu_list.append(
                        GPUInfo(
                            name=name,
                            device_id=str(idx),
                            adapter_ram=0,
                            device_id_int=idx,
                        )
                    )
                    idx += 1
    except Exception as e:
        logger.debug("Linux GPU detection skipped: %s", e)
    return gpu_list


def get_driver_and_cuda_version() -> tuple[str | None, str | None]:
    return providers.cuda.get_driver_and_cuda_version()


def reload_gpu_devices() -> list[GPUInfo]:
    global _gpu_info, _cuda_info, _cuda_available
    logger.info("Reloading GPU info")

    # 1. NVIDIA GPU の検出 (Windows / Linux 共通)
    nvidia_gpus = providers.cuda.detect_nvidia_gpus()

    # 2. プラットフォームごとのシステムGPU検出
    system = platform.system()
    if system == "Windows":
        sys_gpus = providers.directml.detect_windows_gpus()
    elif system == "Darwin":
        sys_gpus = providers.coreml.detect_macos_gpus()
    elif system == "Linux":
        sys_gpus = _detect_linux_gpus()
    else:
        sys_gpus = []

    cpu_entry = GPUInfo(name="CPU", device_id="-1", adapter_ram=0, device_id_int=-1)

    # システムGPUリスト (CPU + 検出されたGPU)
    all_sys = [cpu_entry]
    detected = nvidia_gpus if nvidia_gpus else sys_gpus
    for g in detected:
        if g.name.lower() != "cpu":
            all_sys.append(g)

    # 3. OpenVINO Execution Provider (GPU)
    try:
        if is_openvino_available():
            all_sys.extend(providers.openvino.detect_openvino_gpus())
    except Exception as e:
        logger.debug("OpenVINO detection skipped: %s", e)

    _gpu_info = all_sys

    # CUDA/アクセラレータGPUリスト
    all_cuda = [cpu_entry]
    for g in nvidia_gpus:
        all_cuda.append(g)
    _cuda_info = all_cuda

    _cuda_available = is_cuda_available()
    cuda_driver_version, _ = get_driver_and_cuda_version()

    logger.info("GPU[sys]: %s", _gpu_info)
    logger.info(
        "GPU[cuda]: available:%s, num:%s, driver_version:%s",
        _cuda_available,
        len(nvidia_gpus),
        cuda_driver_version,
    )
    logger.info("GPU[cuda_info]: %s", _cuda_info)
    return _gpu_info


# Alias for backward-compatibility if needed
reload = reload_gpu_devices


def get_gpu_info() -> list[GPUInfo]:
    if not _gpu_info:
        reload_gpu_devices()
    return _gpu_info


def get_cuda_info() -> list[GPUInfo]:
    if not _cuda_info:
        reload_gpu_devices()
    return _cuda_info


def is_cuda_available() -> bool:
    """Check if CUDAExecutionProvider is available in the current runtime environment."""
    return providers.cuda.is_cuda_available()


# --- ONNX Runtime Execution Provider & Session Management ---


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
