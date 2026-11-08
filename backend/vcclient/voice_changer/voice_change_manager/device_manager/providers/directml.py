from __future__ import annotations

import json
import subprocess
from typing import Any

from vcclient.logger import logger
from vcclient.voice_changer.data_types.data_types import GPUInfo


def detect_windows_gpus() -> list[GPUInfo]:
    """Detect available GPUs on Windows via PowerShell CIM."""
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
        logger.debug("Windows GPU detection skipped: %s", e)
    return gpu_list


def resolve_directml_provider(
    device_id: int, available_providers: list[str]
) -> tuple[list[str], list[dict[str, Any]]] | None:
    """Resolve DmlExecutionProvider if applicable, or None if not supported."""
    if device_id >= 0 and "DmlExecutionProvider" in available_providers:
        return (["DmlExecutionProvider"], [{"device_id": device_id}])
    return None
