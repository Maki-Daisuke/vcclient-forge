from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import onnxruntime

from vcclient.logger import logger

from ..data_types import DeviceConfig

OpenVinoCacheDir = Path(tempfile.gettempdir()) / "vcclient" / "openvino_cache"
OpenVinoCacheDir.mkdir(parents=True, exist_ok=True)

_openvino_runtime_initialized = False


def setup_openvino_runtime() -> None:
    """Setup platform-specific OpenVINO Execution Provider runtime and register plugin."""
    global _openvino_runtime_initialized
    if _openvino_runtime_initialized:
        return
    _openvino_runtime_initialized = True

    try:
        import onnxruntime_ep_openvino as openvino_ep

        pkg_dir = Path(openvino_ep.__file__).parent
        if sys.platform == "win32":
            os.add_dll_directory(str(pkg_dir))
            os.environ["PATH"] = str(pkg_dir) + os.pathsep + os.environ.get("PATH", "")
        elif sys.platform == "linux":
            existing = os.environ.get("LD_LIBRARY_PATH", "")
            os.environ["LD_LIBRARY_PATH"] = os.pathsep.join([str(pkg_dir)] + ([existing] if existing else []))

        if hasattr(onnxruntime, "register_execution_provider_library"):
            lib_path = openvino_ep.get_library_path()
            ep_name = openvino_ep.get_ep_name()
            onnxruntime.register_execution_provider_library(ep_name, lib_path)
    except Exception as e:
        logger.warning("Failed to register OpenVINO EP library: %s", e)


def is_openvino_available() -> bool:
    """Check if OpenVINOExecutionProvider is available in the current runtime environment."""
    setup_openvino_runtime()
    available = onnxruntime.get_available_providers()
    if "OpenVINOExecutionProvider" in available:
        return True
    if hasattr(onnxruntime, "get_ep_devices"):
        try:
            for d in onnxruntime.get_ep_devices():
                if getattr(d, "ep_name", "") == "OpenVINOExecutionProvider":
                    return True
        except Exception:
            pass
    return False


def _extract_ov_device(ep_device: Any) -> str:
    """Extract uppercase OpenVINO device name (e.g. 'GPU.0', 'NPU') from an OrtEpDevice."""
    if hasattr(ep_device, "ep_metadata") and isinstance(ep_device.ep_metadata, dict):
        ov_dev = ep_device.ep_metadata.get("ov_device")
        if ov_dev:
            return str(ov_dev).upper()
    dev = getattr(ep_device, "device", None)
    meta = getattr(dev, "metadata", None) if dev is not None else None
    if isinstance(meta, dict) and meta.get("ov_device"):
        return str(meta["ov_device"]).upper()
    return ""


def _get_device_ov_name(device: DeviceConfig) -> str:
    """Return uppercase OpenVINO device identifier (e.g. 'GPU.0', 'NPU') for a DeviceConfig."""
    ov_dev = device.metadata.get("ov_device")
    assert ov_dev, f"OpenVINO DeviceConfig is missing metadata['ov_device']: {device.canonical_id}"
    return str(ov_dev).upper()


def find_openvino_ep_device(
    preferred_type: str = "GPU",
    preferred_ov_device: str | None = None,
) -> Any | None:
    """Find the OpenVINO EP device matching an exact ov_device or preferred device type."""
    if not hasattr(onnxruntime, "get_ep_devices"):
        return None
    try:
        pref_ov = preferred_ov_device.upper() if preferred_ov_device else ""
        pref_type = preferred_type.upper()
        preferred_match = None
        gpu_dev = None
        other_dev = None
        cpu_dev = None
        for d in onnxruntime.get_ep_devices():
            if getattr(d, "ep_name", "") != "OpenVINOExecutionProvider":
                continue
            ov_dev = _extract_ov_device(d)
            if pref_ov:
                if ov_dev == pref_ov:
                    return d
                continue

            dev_type = str(getattr(getattr(d, "device", None), "type", "")).upper()
            if preferred_match is None and (pref_type in dev_type or pref_type in ov_dev):
                preferred_match = d
            if gpu_dev is None and ("GPU" in dev_type or "GPU" in ov_dev):
                gpu_dev = d
            elif cpu_dev is None and ("CPU" in dev_type or "CPU" in ov_dev):
                cpu_dev = d
            elif other_dev is None:
                other_dev = d

        if pref_ov:
            return None
        return preferred_match or gpu_dev or other_dev or cpu_dev
    except Exception as e:
        logger.debug("Failed to inspect OpenVINO ep_devices: %s", e)
        return None


def _build_openvino_load_config(
    ov_device: str,
    cache_dir: str | None = None,
) -> str:
    """Build OpenVINO load_config JSON for the specified target device."""
    target_cfg: dict[str, Any] = {
        # Keep FP32 precision to avoid f16/f32 element-type mismatches on mixed ops (e.g. Gather + ScatterNDUpdate)
        "EXECUTION_MODE_HINT": "ACCURACY",
    }
    if cache_dir:
        target_cfg["CACHE_DIR"] = cache_dir
    return json.dumps({ov_device: target_cfg})


def _get_openvino_cache_dir() -> str | None:
    """Ensure OpenVINO cache directory exists and return its resolved path string."""
    try:
        OpenVinoCacheDir.mkdir(parents=True, exist_ok=True)
        return str(OpenVinoCacheDir.resolve())
    except Exception as e:
        logger.debug("Failed to set OpenVINO cache_dir: %s", e)
        return None


def configure_openvino_session_options(
    so: onnxruntime.SessionOptions,
    device: DeviceConfig,
) -> None:
    """Configure SessionOptions specifically for OpenVINOExecutionProvider."""
    so.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL
    ov_device = _get_device_ov_name(device)
    if hasattr(onnxruntime, "get_ep_devices") and hasattr(so, "add_provider_for_devices"):
        target_dev = find_openvino_ep_device(preferred_ov_device=ov_device)
        if target_dev is not None:
            cache_dir_str = _get_openvino_cache_dir()
            opts: dict[str, str] = {
                "load_config": _build_openvino_load_config(ov_device, cache_dir=cache_dir_str),
            }
            if cache_dir_str:
                opts["cache_dir"] = cache_dir_str

            so.add_provider_for_devices([target_dev], opts)
            dev_type = getattr(getattr(target_dev, "device", None), "type", "Unknown")
            logger.info("Bound OpenVINO EP device: %s (ov_device=%s, type=%s)", target_dev, ov_device, dev_type)


def resolve_openvino_device_provider(
    device: DeviceConfig,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Resolve OpenVINOExecutionProvider options for a given DeviceConfig."""
    ov_device = _get_device_ov_name(device)
    cache_dir_str = _get_openvino_cache_dir()
    options: dict[str, str] = {
        "device_type": ov_device,
        "load_config": _build_openvino_load_config(ov_device, cache_dir=cache_dir_str),
    }
    if cache_dir_str:
        options["cache_dir"] = cache_dir_str
    return (["OpenVINOExecutionProvider", "CPUExecutionProvider"], [options, {}])


def detect_openvino_devices() -> list[DeviceConfig]:
    """Detect available OpenVINO devices (GPU, NPU) and return DeviceConfig templates."""
    if not is_openvino_available() or not hasattr(onnxruntime, "get_ep_devices"):
        return []

    devices: list[DeviceConfig] = []
    gpu_count = 0
    npu_count = 0

    for d in onnxruntime.get_ep_devices():
        if getattr(d, "ep_name", "") != "OpenVINOExecutionProvider":
            continue
        dev = getattr(d, "device", None)
        meta = getattr(dev, "metadata", {}) if dev is not None else {}
        dev_type_str = str(getattr(dev, "type", "")).upper()
        ov_dev = _extract_ov_device(d)

        full_name = ""
        if isinstance(meta, dict):
            full_name = meta.get("Description", "")
        if not full_name and hasattr(d, "ep_metadata") and isinstance(d.ep_metadata, dict):
            full_name = d.ep_metadata.get("FULL_DEVICE_NAME", "")

        if "GPU" in dev_type_str or "GPU" in ov_dev:
            name = f"[OpenVINO] {full_name or 'GPU'}"
            devices.append(
                DeviceConfig(
                    id=0,
                    canonical_id=f"openvino:gpu:{gpu_count}",
                    provider="openvino",
                    device_index=gpu_count,
                    device_type="GPU",
                    name=name,
                    metadata={"ov_device": ov_dev or f"GPU.{gpu_count}"},
                )
            )
            gpu_count += 1
        elif "NPU" in dev_type_str or "NPU" in ov_dev:
            name = f"[OpenVINO] {full_name or 'Intel(R) AI Boost'}"
            devices.append(
                DeviceConfig(
                    id=0,
                    canonical_id=f"openvino:npu:{npu_count}",
                    provider="openvino",
                    device_index=npu_count,
                    device_type="NPU",
                    name=name,
                    metadata={"ov_device": ov_dev or "NPU"},
                )
            )
            npu_count += 1

    return devices


def prepare_openvino_model(
    device: DeviceConfig,
    model_payload: str | bytes | Path,
    patch_type: str | None = None,
) -> tuple[DeviceConfig, str | bytes | Path]:
    """Inspect device limitations and apply OpenVINO-specific graph patches."""
    target_device = device

    # RVC HiFi-GAN vocoder exceeds client NPU SRAM capacity; fall back to CPU if NPU is selected pipeline-wide
    if target_device.device_type == "NPU" and patch_type == "rvc":
        logger.warning("RVC vocoder is not supported on NPU; falling back to CPU for synthesis session.")
        from ..device_manager import get_device

        target_device = get_device(0)
        return target_device, model_payload

    if patch_type == "rvc":
        from ..openvino_patch import patch_rvc_model_for_openvino

        model_payload = patch_rvc_model_for_openvino(model_payload)
    elif patch_type == "rmvpe":
        from ..openvino_patch import patch_rmvpe_model_for_openvino

        model_payload = patch_rmvpe_model_for_openvino(model_payload)

    return target_device, model_payload
