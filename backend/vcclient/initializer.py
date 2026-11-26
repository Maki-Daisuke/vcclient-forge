from __future__ import annotations

import gc
import re
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from vcclient.device import DeviceConfig, get_device_catalog
from vcclient.logger import logger
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.module_manager_data_types import ModuleDownloadStatus
from vcclient.voice_changer.data_types.sample_manager_data_types import SampleDownloadStatus
from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.model_catalog import get_probe_slot_info, list_models
from vcclient.voice_changer.module_manager import download_rvc_modules, is_rvc_ready
from vcclient.voice_changer.sample_manager import download_initial_samples

DownloadStatus = TypeVar("DownloadStatus", ModuleDownloadStatus, SampleDownloadStatus)

if TYPE_CHECKING:
    from vcclient.voice_changer.data_types.data_types import VoiceChangerConfiguration
    from vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline import RVCPipeline


def _download_progress(label_for_id: Callable[[str], str]) -> Callable[[list[DownloadStatus]], None]:
    last_update = 0.0
    previous_states: dict[str, str] = {}
    displayed_lines = 0

    def update(status: list[DownloadStatus]) -> None:
        nonlocal last_update, previous_states, displayed_lines
        if not status:
            return

        now = time.monotonic()
        states: dict[str, str] = {item.id: item.status for item in status}
        if states == previous_states and now - last_update < 0.1:
            return
        last_update = now
        previous_states = states

        lines = []
        for item in status:
            progress = min(1.0, max(0.0, item.progress))
            filled = int(progress * 20)
            bar = "=" * filled + (">" if filled < 20 else "")
            state = {"done": " [OK]", "error": " [ERROR]", "validating": " [VERIFY]"}.get(item.status, "")
            label = label_for_id(item.id)[:24]
            lines.append(f"\r\x1b[2K{label:<24} [{bar:<20}] {int(progress * 100):>3}%{state}")

        cursor_up = f"\x1b[{displayed_lines}A" if displayed_lines else ""
        print(cursor_up + "\n".join(lines), flush=True)
        displayed_lines = len(lines)

    return update


def _initial_device_candidates(devices: list[DeviceConfig]) -> list[DeviceConfig]:
    # Discrete GPUs outrank integrated ones; within a tier, OpenVINO's tuned kernels beat DirectML and generic Vulkan.
    gpu_rank = {"openvino": 0, "directml": 1, "webgpu": 2}

    def priority(device: DeviceConfig) -> tuple[int, int, int]:
        if device.provider == "cuda" and device.device_type == "GPU":
            return (0, 0, -device.device_index)
        if device.provider == "coreml" and device.metadata.get("compute_units") == "ALL":
            return (1, 0, -device.device_index)
        if device.provider in gpu_rank and device.device_type == "GPU":
            index = -device.device_index
            if device.provider == "openvino":
                match = re.fullmatch(r"GPU\.(\d+)", str(device.metadata.get("ov_device", "")), re.IGNORECASE)
                index = -int(match.group(1)) if match else index
            elif device.provider == "webgpu":
                index = device.device_index
            return (2 if device.metadata.get("discrete") else 3, gpu_rank[device.provider], index)
        if device.provider == "cpu":
            return (4, 0, 0)
        return (5, 0, 0)

    return sorted((device for device in devices if priority(device)[0] < 5), key=priority)


def _verify_device_sessions(pipeline: "RVCPipeline", device: DeviceConfig) -> None:
    expected_provider = {
        "cpu": "CPUExecutionProvider",
        "cuda": "CUDAExecutionProvider",
        "coreml": "CoreMLExecutionProvider",
        "openvino": "OpenVINOExecutionProvider",
        "directml": "DmlExecutionProvider",
        "webgpu": "WebGpuExecutionProvider",
    }[device.provider]
    sessions = [
        getattr(component, "onnx_session") for component in (pipeline.pitch_estimator, pipeline.embedder, pipeline.rvc)
    ]
    sessions.append(pipeline.onnx_upscaler)
    for session in sessions:
        providers = session.get_providers()
        if expected_provider not in providers:
            raise RuntimeError(f"Expected {expected_provider}, got {providers}")
        session.disable_fallback()


def _probe_first_working_device(conf: VoiceChangerConfiguration, slot: RVCSlotInfo) -> DeviceConfig:
    """Test ranked compute devices against `slot` and return the first device whose pipeline warms up cleanly."""
    from vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline import RVCPipeline

    for device in _initial_device_candidates(get_device_catalog()):
        conf.gpu_device_id_int = device.id
        print(f"Testing inference device: {device.name}", flush=True)
        pipeline: RVCPipeline | None = None
        try:
            pipeline = RVCPipeline(slot)
            _verify_device_sessions(pipeline, device)
            pipeline.warmup()
            _verify_device_sessions(pipeline, device)
            return device
        except Exception as e:
            logger.warning("Initial device test failed for %s: %s", device.canonical_id, e, exc_info=True)
            print(f"Inference device test failed: {device.name}", flush=True)
        # Collect only after leaving `except`: the live traceback keeps the failed pipeline's sessions alive,
        # and WebGPU cannot switch adapters while any session from the previous one remains.
        pipeline = None
        gc.collect()

    conf.gpu_device_id_int = 0
    raise RuntimeError("No inference device passed the initial pipeline test; see vcclient.log for details.")


def recommend_compute_device() -> DeviceConfig:
    """Probe available compute devices against a valid model and return the recommended device without persisting."""
    manager = ConfigurationManager.get_instance()
    conf = manager.get_voice_changer_configuration()
    slot = get_probe_slot_info(conf.model_id)
    if slot is None:
        raise LookupError("No valid RVC model is available for compute device auto-selection.")

    original_device_id = conf.gpu_device_id_int
    try:
        device = _probe_first_working_device(conf, slot)
    finally:
        conf.gpu_device_id_int = original_device_id

    logger.info("Recommended compute device selected: %s", device.canonical_id)
    print(f"Inference device selected: {device.name}", flush=True)
    return device


def _select_initial_compute_device() -> bool:
    manager = ConfigurationManager.get_instance()
    conf = manager.get_voice_changer_configuration()
    slot = get_probe_slot_info(conf.model_id)
    if slot is None:
        logger.warning("Skipping initial device selection: the initial model is unavailable.")
        print("Initial model is unavailable; automatic device selection skipped.", flush=True)
        return False

    device = _probe_first_working_device(conf, slot)
    logger.info("Initial inference device selected: %s", device.canonical_id)
    print(f"Inference device selected: {device.name}", flush=True)
    return True


def _check_and_download_rvc_modules() -> None:
    if not is_rvc_ready():
        logger.info("RVC is not ready. Downloading RVC modules.")
        print("RVC is not ready. Downloading RVC modules (parallel)...", flush=True)

        download_rvc_modules(_download_progress(lambda name: name.replace(".onnx", "").replace("-f", "")))
        logger.info("RVC is not ready. Downloading RVC modules. Done.")
        print("\nRVC is not ready. Downloading RVC modules. Done.\n", flush=True)


def _check_and_download_initial_samples() -> None:
    if len(list_models()) == 0:
        logger.info("Sample is not ready. Downloading initial samples.")
        print("Sample is not ready. Downloading initial samples (parallel)...", flush=True)

        download_initial_samples(_download_progress(lambda name: name.replace("_o", "")))
        logger.info("Sample is not ready. Downloading initial samples. Done.")
        print("\nSample is not ready. Downloading initial samples. Done.\n", flush=True)
