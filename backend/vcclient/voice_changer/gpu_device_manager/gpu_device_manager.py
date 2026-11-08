from __future__ import annotations

import platform
import subprocess

from vcclient.logger import logger
from vcclient.voice_changer.data_types.data_types import GPUInfo
from vcclient.voice_changer.voice_change_manager.device_manager import providers


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


_gpu_info: list[GPUInfo] = []
_cuda_info: list[GPUInfo] = []
_cuda_available: bool = False


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

    cpu_entry = GPUInfo(name="cpu", device_id="-1", adapter_ram=0, device_id_int=-1)

    # システムGPUリスト (CPU + 検出されたGPU)
    all_sys = [cpu_entry]
    detected = nvidia_gpus if nvidia_gpus else sys_gpus
    for g in detected:
        if g.name.lower() != "cpu":
            all_sys.append(g)

    # 3. OpenVINO Execution Provider (GPU)
    try:
        from vcclient.voice_changer.voice_change_manager.device_manager import is_openvino_available

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

    _cuda_available = len(nvidia_gpus) > 0
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
    if not _gpu_info:
        reload_gpu_devices()
    return _cuda_available
