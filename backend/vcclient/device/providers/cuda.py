from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import onnxruntime

from vcclient.logger import logger
from vcclient.voice_changer.data_types.data_types import GPUInfo

from .util import parse_vram_string

if TYPE_CHECKING:
    from ..data_types import DeviceConfig

_cuda_runtime_initialized = False


def setup_cuda_runtime() -> None:
    """Setup platform-specific CUDA / cuDNN runtime environment and register plugins."""
    global _cuda_runtime_initialized
    if _cuda_runtime_initialized:
        return
    _cuda_runtime_initialized = True

    if sys.platform == "win32":
        # 1. PyTorch's bundled lib (if CUDA-enabled PyTorch is present)
        try:
            import torch

            torch_lib = Path(torch.__file__).parent / "lib"
            if torch_lib.exists():
                os.add_dll_directory(str(torch_lib))
                os.environ["PATH"] = str(torch_lib) + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass

        # 2. nvidia-* pip packages (for pure-ONNX mode with CPU PyTorch)
        nvidia_pkgs = [
            "nvidia.cublas",
            "nvidia.cudnn",
            "nvidia.cuda_runtime",
            "nvidia.cufft",
            "nvidia.curand",
            "nvidia.cu13",
        ]
        for pkg in nvidia_pkgs:
            try:
                spec = importlib.util.find_spec(pkg)
                if spec and spec.submodule_search_locations:
                    loc = Path(list(spec.submodule_search_locations)[0])
                    bin_dir = loc / "bin"
                    if bin_dir.exists():
                        os.add_dll_directory(str(bin_dir))
                        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                        for arch_dir in bin_dir.iterdir():
                            if arch_dir.is_dir():
                                os.add_dll_directory(str(arch_dir))
                                os.environ["PATH"] = str(arch_dir) + os.pathsep + os.environ.get("PATH", "")
            except Exception:
                pass

        try:
            if hasattr(onnxruntime, "preload_dlls") and getattr(onnxruntime, "cuda_version", None):
                onnxruntime.preload_dlls(directory="")
        except Exception:
            pass
    elif sys.platform == "linux":
        nvidia_pkgs = [
            "nvidia.cublas",
            "nvidia.cudnn",
            "nvidia.cuda_runtime",
            "nvidia.cufft",
            "nvidia.curand",
            "nvidia.cu13",
        ]
        lib_dirs: list[str] = []
        for pkg in nvidia_pkgs:
            try:
                spec = importlib.util.find_spec(pkg)
                if spec and spec.submodule_search_locations:
                    for search_loc in spec.submodule_search_locations:
                        lib_dir = Path(search_loc) / "lib"
                        if lib_dir.is_dir():
                            lib_dirs.append(str(lib_dir))
            except Exception:
                pass
        if lib_dirs:
            existing = os.environ.get("LD_LIBRARY_PATH", "")
            os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(lib_dirs + ([existing] if existing else []))

        try:
            if hasattr(onnxruntime, "preload_dlls") and getattr(onnxruntime, "cuda_version", None):
                onnxruntime.preload_dlls(directory="")
        except Exception:
            pass

    # 3. CUDA Execution Provider Plugin registration (Windows & Linux)
    try:
        if hasattr(onnxruntime, "register_execution_provider_library"):
            capi_dir = Path(onnxruntime.__file__).parent / "capi"
            cuda_lib_name = (
                "onnxruntime_providers_cuda.dll" if sys.platform == "win32" else "libonnxruntime_providers_cuda.so"
            )
            cuda_lib_path = capi_dir / cuda_lib_name
            if cuda_lib_path.exists():
                onnxruntime.register_execution_provider_library("CUDAExecutionProvider", str(cuda_lib_path))
    except Exception as e:
        logger.debug("Failed to register CUDA EP library: %s", e)


def is_cuda_available() -> bool:
    """Check if CUDAExecutionProvider is available in the current runtime environment."""
    setup_cuda_runtime()
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
                    vram = parse_vram_string(meta.get("DxgiVideoMemory"))
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
                try:
                    idx = int(parts[0])
                except ValueError, TypeError:
                    continue
                raw_name = parts[1]
                name = raw_name if raw_name.startswith("[CUDA]") else f"[CUDA] {raw_name}"
                try:
                    vram_mb = int(parts[2])
                    vram_bytes = vram_mb * 1024 * 1024
                except ValueError, TypeError:
                    vram_bytes = 0
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


def resolve_cuda_device_provider(
    device: DeviceConfig,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Resolve CUDAExecutionProvider options for a typed DeviceConfig."""
    import onnxruntime as ort

    if "CUDAExecutionProvider" in ort.get_available_providers():
        return (["CUDAExecutionProvider"], [{"device_id": device.device_index}])
    return device._fallback_to_cpu("CUDAExecutionProvider")
