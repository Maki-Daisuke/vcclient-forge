from __future__ import annotations

import re
import subprocess
from typing import Any

import onnxruntime

from vcclient.logger import logger
from vcclient.utils.runtime_env import setup_runtime_env
from vcclient.voice_changer.data_types.data_types import GPUInfo

from .directml import _parse_vram_string


def is_cuda_available() -> bool:
    """Check if CUDAExecutionProvider is available in the current runtime environment."""
    setup_runtime_env()
    available = onnxruntime.get_available_providers()
    if "CUDAExecutionProvider" in available:
        return True
    if hasattr(onnxruntime, "get_ep_devices"):
        try:
            for d in onnxruntime.get_ep_devices():
                if getattr(d, "ep_name", "") == "CUDAExecutionProvider":
                    return True
        except Exception:
            pass
    return False


def detect_nvidia_gpus() -> list[GPUInfo]:
    """Detect available NVIDIA GPUs via ONNX Runtime CUDA EP (falling back to nvidia-smi)."""
    if not is_cuda_available():
        return []

    gpu_list: list[GPUInfo] = []

    # 1. Native ONNX Runtime EP discovery
    if hasattr(onnxruntime, "get_ep_devices"):
        try:
            for d in onnxruntime.get_ep_devices():
                if getattr(d, "ep_name", "") == "CUDAExecutionProvider":
                    dev = getattr(d, "device", None)
                    meta = getattr(dev, "metadata", {}) if dev is not None else {}
                    raw_name = meta.get("Description") or "NVIDIA GPU"
                    name = raw_name if raw_name.startswith("[CUDA]") else f"[CUDA] {raw_name}"
                    try:
                        adapter_idx = int(meta.get("DxgiAdapterNumber", len(gpu_list)))
                    except Exception:
                        adapter_idx = len(gpu_list)
                    vram = _parse_vram_string(meta.get("DxgiVideoMemory"))
                    gpu_list.append(
                        GPUInfo(
                            name=name,
                            device_id=str(adapter_idx),
                            adapter_ram=vram,
                            device_id_int=adapter_idx,
                        )
                    )
            if gpu_list:
                gpu_list.sort(key=lambda g: g.device_id_int)
                return gpu_list
        except Exception as e:
            logger.debug("Native CUDA EP device detection failed: %s", e)

    # 2. Fallback via nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=5,
        )
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                idx = int(parts[0])
                raw_name = parts[1]
                name = raw_name if raw_name.startswith("[CUDA]") else f"[CUDA] {raw_name}"
                vram_mb = int(parts[2])
                vram_bytes = vram_mb * 1024 * 1024
                gpu_list.append(
                    GPUInfo(
                        name=name,
                        device_id=str(idx),
                        adapter_ram=vram_bytes,
                        device_id_int=idx,
                    )
                )
    except Exception as e:
        logger.debug("NVIDIA GPU detection skipped: %s", e)
    return gpu_list


def get_driver_and_cuda_version() -> tuple[str | None, str | None]:
    """Query nvidia-smi to obtain driver and supported CUDA versions."""
    driver_version = None
    cuda_version = None
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            m_driver = re.search(r"Driver Version:\s*([0-9.]+)", line)
            if m_driver and driver_version is None:
                driver_version = m_driver.group(1)
            m_cuda = re.search(r"CUDA.*?Version:\s*([0-9.]+)", line)
            if m_cuda and cuda_version is None:
                cuda_version = m_cuda.group(1)
            if driver_version and cuda_version:
                break
    except Exception as e:
        logger.debug("Failed to query driver/CUDA version via nvidia-smi: %s", e)
    return driver_version, cuda_version


def resolve_cuda_provider(
    device_id: int, gpu_num: int, available_providers: list[str]
) -> tuple[list[str], list[dict[str, Any]]] | None:
    """Resolve CUDAExecutionProvider if applicable, or None if not supported."""
    if device_id < 0 or "CUDAExecutionProvider" not in available_providers or gpu_num <= 0:
        return None
    if device_id < gpu_num:
        return (["CUDAExecutionProvider"], [{"device_id": device_id}])

    logger.info("device detection error, fallback to cpu. device_id: %s >= dev_num: %s", device_id, gpu_num)
    from .cpu import resolve_cpu_provider

    return resolve_cpu_provider()
