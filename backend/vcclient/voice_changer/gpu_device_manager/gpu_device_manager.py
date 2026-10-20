import json
import logging
import platform
import re
import subprocess

from ...const import LOGGER_NAME
from ..data_types.data_types import GPUInfo


def _detect_nvidia_gpus() -> list[GPUInfo]:
    gpu_list: list[GPUInfo] = []
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
                name = parts[1]
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
        logging.getLogger(LOGGER_NAME).debug(f"NVIDIA GPU detection skipped: {e}")
    return gpu_list


def _detect_windows_gpus() -> list[GPUInfo]:
    gpu_list: list[GPUInfo] = []
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_VideoController | Select-Object -Property Name, DeviceID, AdapterRAM | ConvertTo-Json",
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            if isinstance(data, dict):
                data = [data]
            for idx, item in enumerate(data):
                name = item.get("Name", "")
                dev_id = item.get("DeviceID", str(idx))
                vram = int(item.get("AdapterRAM") or 0)
                gpu_list.append(
                    GPUInfo(
                        name=name,
                        device_id=dev_id,
                        adapter_ram=vram,
                        device_id_int=idx,
                    )
                )
    except Exception as e:
        logging.getLogger(LOGGER_NAME).debug(f"Windows GPU detection skipped: {e}")
    return gpu_list


def _detect_macos_gpus() -> list[GPUInfo]:
    gpu_list: list[GPUInfo] = []
    try:
        cmd = ["system_profiler", "SPDisplaysDataType", "-json"]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            displays = data.get("SPDisplaysDataType", [])
            for idx, item in enumerate(displays):
                name = item.get("sppci_model") or item.get("_name", "Apple GPU")
                vram_str = item.get("spdisplays_vram", "")
                vram = 0
                if "GB" in vram_str:
                    try:
                        vram = int(vram_str.replace("GB", "").strip()) * 1024 * 1024 * 1024
                    except Exception:
                        pass
                gpu_list.append(
                    GPUInfo(
                        name=name,
                        device_id=str(idx),
                        adapter_ram=vram,
                        device_id_int=idx,
                    )
                )
    except Exception as e:
        logging.getLogger(LOGGER_NAME).debug(f"macOS GPU detection skipped: {e}")
    return gpu_list


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
        logging.getLogger(LOGGER_NAME).debug(f"Linux GPU detection skipped: {e}")
    return gpu_list


def get_driver_and_cuda_version() -> tuple[str | None, str | None]:
    driver_version = None
    cuda_version = None
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            m_cuda = re.search(r"CUDA.*?Version:\s*([0-9.]+)", line)
            if m_cuda and cuda_version is None:
                cuda_version = m_cuda.group(1)
            m_driver = re.search(r"(?:Driver Version:|NVIDIA-SMI)\s*([0-9.]+)", line)
            if m_driver and driver_version is None:
                driver_version = m_driver.group(1)
    except Exception:
        pass
    return driver_version, cuda_version


class GPUDeviceManager:
    _instance: GPUDeviceManager | None = None
    gpu_info: list[GPUInfo]
    cuda_info: list[GPUInfo]
    cuda_available: bool
    cuda_gpu_num: int
    cuda_driver_version: str | None
    cuda_version: str | None
    cudnn_version: str | None
    cuda_mps_enabled: bool

    @classmethod
    def get_instance(cls) -> GPUDeviceManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.reload()

    def reload(self) -> list[GPUInfo]:
        logging.getLogger(LOGGER_NAME).info("Reloading GPU info")

        # 1. NVIDIA GPU の検出 (Windows / Linux 共通)
        nvidia_gpus = _detect_nvidia_gpus()

        # 2. プラットフォームごとのシステムGPU検出
        system = platform.system()
        if system == "Windows":
            sys_gpus = _detect_windows_gpus()
        elif system == "Darwin":
            sys_gpus = _detect_macos_gpus()
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
        self.gpu_info = all_sys

        # CUDA/アクセラレータGPUリスト
        all_cuda = [cpu_entry]
        for g in nvidia_gpus:
            all_cuda.append(g)
        self.cuda_info = all_cuda

        self.cuda_available = len(nvidia_gpus) > 0
        self.cuda_gpu_num = len(nvidia_gpus)
        self.cuda_driver_version, self.cuda_version = get_driver_and_cuda_version()
        self.cudnn_version = None
        self.cuda_mps_enabled = system == "Darwin"

        logging.getLogger(LOGGER_NAME).info(f"GPU[sys]: {self.gpu_info}")
        logging.getLogger(LOGGER_NAME).info(
            f"GPU[cuda]: available:{self.cuda_available}, num:{self.cuda_gpu_num}, driver_version:{self.cuda_driver_version}"
        )
        logging.getLogger(LOGGER_NAME).info(f"GPU[cuda_info]: {self.cuda_info}")
        return self.gpu_info

    def get_gpu_info(self) -> list[GPUInfo]:
        return self.gpu_info

    def get_cuda_info(self) -> list[GPUInfo]:
        return self.cuda_info

    def is_cuda_available(self) -> bool:
        return self.cuda_available
