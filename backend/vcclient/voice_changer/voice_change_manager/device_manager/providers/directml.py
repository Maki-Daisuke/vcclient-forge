from __future__ import annotations

import json
import subprocess
from typing import Any

import onnxruntime

from vcclient.logger import logger
from vcclient.voice_changer.data_types.data_types import GPUInfo

from .util import parse_vram_string

_directml_runtime_initialized = False


def setup_directml_runtime() -> None:
    """Setup DirectML runtime environment (reserved for future DML configuration)."""
    global _directml_runtime_initialized
    if _directml_runtime_initialized:
        return
    _directml_runtime_initialized = True


def _filter_directml_devices(
    raw_devices: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Filter out virtual/duplicate DXGI compute adapters, preferring physical discrete GPUs."""
    from collections import defaultdict

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for meta in raw_devices:
        desc = meta.get("Description", "DirectML GPU")
        grouped[desc].append(meta)

    filtered: list[dict[str, str]] = []
    for desc, items in grouped.items():
        discrete_items = [it for it in items if it.get("Discrete") == "1"]
        candidate_pool = discrete_items if discrete_items else items

        def sort_key(meta: dict[str, str]) -> tuple[int, int]:
            try:
                perf_idx = int(meta.get("DxgiHighPerformanceIndex", 999))
            except Exception:
                perf_idx = 999
            try:
                adapter_num = int(meta.get("DxgiAdapterNumber", 999))
            except Exception:
                adapter_num = 999
            return (perf_idx, adapter_num)

        candidate_pool.sort(key=sort_key)
        if discrete_items:
            seen_luids = set()
            for it in candidate_pool:
                luid = it.get("LUID")
                if luid and luid not in seen_luids:
                    seen_luids.add(luid)
                    filtered.append(it)
                elif not luid:
                    filtered.append(it)
        else:
            filtered.append(candidate_pool[0])

    return filtered


def detect_windows_gpus() -> list[GPUInfo]:
    """Detect available GPUs on Windows.

    Prioritizes pure-ONNX native device enumeration via ort.get_ep_devices()
    (matching DXGI adapter indexes directly and deduplicating virtual compute adapters),
    falling back to PowerShell CIM if native EP inspection is unavailable.
    """
    gpu_list: list[GPUInfo] = []

    # 1. Native ONNX Runtime EP device discovery (fast, accurate DXGI adapter index)
    if hasattr(onnxruntime, "get_ep_devices"):
        try:
            raw_metas: list[dict[str, str]] = []
            for d in onnxruntime.get_ep_devices():
                if getattr(d, "ep_name", "") == "DmlExecutionProvider":
                    dev = getattr(d, "device", None)
                    meta = getattr(dev, "metadata", {}) if dev is not None else {}
                    raw_metas.append(meta)

            if raw_metas:
                filtered_metas = _filter_directml_devices(raw_metas)
                for meta in filtered_metas:
                    raw_name = meta.get("Description") or "DirectML GPU"
                    name = raw_name if raw_name.startswith("[DirectML]") else f"[DirectML] {raw_name}"
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
            logger.debug("Native DirectML EP device detection failed: %s", e)

    # 2. Fallback via PowerShell CIM
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
                raw_name = item.get("Name", "")
                name = raw_name if raw_name.startswith("[DirectML]") else f"[DirectML] {raw_name}"
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
