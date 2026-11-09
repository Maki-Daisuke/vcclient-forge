from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from vcclient.logger import logger
from vcclient.voice_changer.data_types.data_types import GPUInfo

from ..data_types import DeviceConfig

CoreMLCacheDir = Path(tempfile.gettempdir()) / "vcclient" / "coreml_cache"
CoreMLCacheDir.mkdir(parents=True, exist_ok=True)

_coreml_runtime_initialized = False


def setup_coreml_runtime() -> None:
    """Setup CoreML runtime environment and ensure cache directory exists."""
    global _coreml_runtime_initialized
    if _coreml_runtime_initialized:
        return
    _coreml_runtime_initialized = True

    try:
        CoreMLCacheDir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.debug("Failed to create CoreML cache dir: %s", e)


def detect_macos_gpus() -> list[GPUInfo]:
    """Detect available GPUs on macOS via system_profiler."""
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
                        name=f"[CoreML] {name} (ALL / ANE Preferred)",
                        device_id=str(idx * 2),
                        adapter_ram=vram,
                        device_id_int=idx * 2,
                    )
                )
                gpu_list.append(
                    GPUInfo(
                        name=f"[CoreML] {name} (CPU + GPU / GPU Preferred)",
                        device_id=str(idx * 2 + 1),
                        adapter_ram=vram,
                        device_id_int=idx * 2 + 1,
                    )
                )
    except Exception as e:
        logger.debug("macOS GPU detection skipped: %s", e)
    return gpu_list


def resolve_coreml_device_provider(
    device: DeviceConfig | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Resolve CoreMLExecutionProvider options for a typed DeviceConfig."""
    compute_units = device.metadata.get("compute_units", "ALL") if device and device.metadata else "ALL"
    coreml_options: dict[str, Any] = {
        "ModelFormat": "NeuralNetwork",
        "MLComputeUnits": compute_units,
        "RequireStaticInputShapes": "0",
        "EnableOnSubgraphs": "0",
    }
    try:
        CoreMLCacheDir.mkdir(parents=True, exist_ok=True)
        coreml_options["ModelCacheDirectory"] = str(CoreMLCacheDir.resolve())
    except Exception as e:
        logger.debug("Failed to set CoreML cache dir: %s", e)
    return (["CoreMLExecutionProvider", "CPUExecutionProvider"], [coreml_options, {}])


def resolve_coreml_provider(
    device_id: int, available_providers: list[str]
) -> tuple[list[str], list[dict[str, Any]]] | None:
    """Resolve CoreMLExecutionProvider if applicable, or None if not supported."""
    if device_id >= 0 and "CoreMLExecutionProvider" in available_providers:
        compute_units = "CPUAndGPU" if device_id % 2 == 1 else "ALL"
        fake_dev = DeviceConfig(
            id=device_id,
            canonical_id=f"coreml:{device_id}",
            provider="coreml",
            device_index=device_id,
            metadata={"compute_units": compute_units},
        )
        return resolve_coreml_device_provider(fake_dev)
    return None
