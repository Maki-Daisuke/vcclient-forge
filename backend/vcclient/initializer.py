from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from vcclient.logger import logger
from vcclient.voice_changer.data_types.module_manager_data_types import ModuleDownloadStatus
from vcclient.voice_changer.data_types.sample_manager_data_types import SampleDownloadStatus
from vcclient.voice_changer.model_catalog import list_models
from vcclient.voice_changer.module_manager import download_rvc_modules, is_rvc_ready
from vcclient.voice_changer.sample_manager import download_initial_samples

DownloadStatus = TypeVar("DownloadStatus", ModuleDownloadStatus, SampleDownloadStatus)


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
