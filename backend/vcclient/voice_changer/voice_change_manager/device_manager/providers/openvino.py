from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import onnxruntime

from vcclient.logger import logger
from vcclient.utils.runtime_env import setup_runtime_env
from vcclient.voice_changer.data_types.data_types import GPUInfo

OPENVINO_GPU_DEVICE_ID = 1000
OPENVINO_AUTO_DEVICE_ID = OPENVINO_GPU_DEVICE_ID
OpenVinoCacheDir = Path(tempfile.gettempdir()) / "vcclient" / "openvino_cache"
OpenVinoCacheDir.mkdir(parents=True, exist_ok=True)


def is_openvino_available() -> bool:
    """Check if OpenVINOExecutionProvider is available in the current runtime environment."""
    setup_runtime_env()
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


def find_openvino_ep_device(preferred_type: str = "GPU") -> Any | None:
    """Find the most suitable OpenVINO EP device from ort.get_ep_devices().

    Prioritizes GPU devices to ensure RVC models and dynamic audio graphs execute
    on hardware without NPU compiler scheduling limitations or silent CPU fallback.
    """
    if not hasattr(onnxruntime, "get_ep_devices"):
        return None
    try:
        ep_devices = onnxruntime.get_ep_devices()
        gpu_dev = None
        cpu_dev = None
        fallback_dev = None
        for d in ep_devices:
            if getattr(d, "ep_name", "") != "OpenVINOExecutionProvider":
                continue
            dev_type = str(getattr(getattr(d, "device", None), "type", "")).upper()
            ov_dev = ""
            if hasattr(d, "ep_metadata") and isinstance(d.ep_metadata, dict):
                ov_dev = str(d.ep_metadata.get("ov_device", "")).upper()
            elif hasattr(getattr(d, "device", None), "metadata") and isinstance(d.device.metadata, dict):
                ov_dev = str(d.device.metadata.get("ov_device", "")).upper()

            if "GPU" in dev_type or "GPU" in ov_dev:
                gpu_dev = d
                break
            if "CPU" in dev_type or "CPU" in ov_dev:
                cpu_dev = d
            elif fallback_dev is None:
                fallback_dev = d

        if preferred_type == "GPU" and gpu_dev is not None:
            return gpu_dev
        return gpu_dev or fallback_dev or cpu_dev
    except Exception as e:
        logger.debug("Failed to inspect OpenVINO ep_devices: %s", e)
        return None


def configure_openvino_session_options(so: onnxruntime.SessionOptions) -> None:
    """Configure SessionOptions specifically for OpenVINOExecutionProvider."""
    so.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL
    if hasattr(onnxruntime, "get_ep_devices") and hasattr(so, "add_provider_for_devices"):
        try:
            target_dev = find_openvino_ep_device(preferred_type="GPU")
            if target_dev is not None:
                gpu_cfg: dict[str, Any] = {
                    "EXECUTION_MODE_HINT": "ACCURACY",
                }
                try:
                    OpenVinoCacheDir.mkdir(parents=True, exist_ok=True)
                    cache_dir_str = str(OpenVinoCacheDir.resolve())
                    gpu_cfg["CACHE_DIR"] = cache_dir_str
                except Exception as e:
                    logger.debug("Failed to set OpenVINO cache_dir: %s", e)

                opts: dict[str, str] = {
                    "load_config": json.dumps({"GPU": gpu_cfg}),
                }
                if "CACHE_DIR" in gpu_cfg:
                    opts["cache_dir"] = gpu_cfg["CACHE_DIR"]

                so.add_provider_for_devices([target_dev], opts)
                dev_type = getattr(getattr(target_dev, "device", None), "type", "Unknown")
                logger.info("Bound OpenVINO EP device: %s (type=%s)", target_dev, dev_type)
        except Exception as e:
            logger.debug("Failed to bind OpenVINO ep_device: %s", e)


def resolve_openvino_provider(
    device_id: int, available: bool | None = None
) -> tuple[list[str], list[dict[str, Any]]] | None:
    """Resolve OpenVINOExecutionProvider if applicable, or None if not supported."""
    if device_id not in (OPENVINO_GPU_DEVICE_ID, OPENVINO_AUTO_DEVICE_ID):
        return None

    if available is None:
        available = is_openvino_available()

    if available:
        options: dict[str, str] = {
            "device_type": "GPU",
            "load_config": json.dumps({"GPU": {"EXECUTION_MODE_HINT": "ACCURACY"}}),
        }
        try:
            OpenVinoCacheDir.mkdir(parents=True, exist_ok=True)
            options["cache_dir"] = str(OpenVinoCacheDir.resolve())
        except Exception as e:
            logger.debug("Failed to set OpenVINO cache_dir: %s", e)
        return (["OpenVINOExecutionProvider", "CPUExecutionProvider"], [options, {}])

    logger.info("OpenVINO requested but unavailable, fallback to cpu.")
    from .cpu import resolve_cpu_provider

    return resolve_cpu_provider()


def detect_openvino_gpus() -> list[GPUInfo]:
    """Detect OpenVINO (GPU) capability and return an entry if available."""
    gpu_list: list[GPUInfo] = []
    try:
        if is_openvino_available():
            dev_name = "GPU"
            target_dev = find_openvino_ep_device(preferred_type="GPU")
            if target_dev is not None:
                dev = getattr(target_dev, "device", None)
                meta = getattr(dev, "metadata", {}) if dev is not None else {}
                desc = meta.get("Description")
                if not desc and hasattr(target_dev, "ep_metadata") and isinstance(target_dev.ep_metadata, dict):
                    desc = target_dev.ep_metadata.get("FULL_DEVICE_NAME")
                if desc:
                    dev_name = desc

            gpu_list.append(
                GPUInfo(
                    name=f"[OpenVINO] {dev_name}",
                    device_id="openvino_gpu",
                    adapter_ram=0,
                    device_id_int=OPENVINO_GPU_DEVICE_ID,
                )
            )
    except Exception as e:
        logger.debug("OpenVINO detection skipped: %s", e)
    return gpu_list
