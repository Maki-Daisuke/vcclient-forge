"""Exercise real PortAudio device discovery and probing in an isolated process."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest


def test_real_audio_device_discovery_and_probing() -> None:
    # PortAudio initialization is process-wide. Keep its termination and
    # reinitialization separate from the rest of the test suite.
    probe = dedent(
        """
        from concurrent.futures import ThreadPoolExecutor

        from vcclient.voice_changer.audio_device_manager import (
            check_available_sample_rate,
            get_audio_input_devices,
            get_audio_output_devices,
            get_default_sample_rate,
            reload_audio_devices,
        )

        inputs, outputs = reload_audio_devices()
        if not inputs or not outputs:
            print(f"Audio devices unavailable: {len(inputs)} inputs, {len(outputs)} outputs")
            raise SystemExit(77)

        def choose(devices):
            return next((device for device in devices if "WASAPI" in device.host_api.upper()), devices[0])

        selected = [(choose(inputs), "audioinput"), (choose(outputs), "audiooutput")]

        def check_device(item):
            device, kind = item
            rate = get_default_sample_rate(device.index, kind)
            assert rate > 0, f"Cannot open {kind} device {device.index}: {device.name}"
            assert check_available_sample_rate(device.index, round(rate), kind), (
                f"Cannot reopen {kind} device {device.index} at {rate} Hz"
            )
            print(f"{kind}: {device.name}, {device.host_api}, {rate} Hz")

        with ThreadPoolExecutor(max_workers=2) as callers:
            list(callers.map(check_device, selected))

        reloaded_inputs, reloaded_outputs = reload_audio_devices()
        assert get_audio_input_devices() == reloaded_inputs
        assert get_audio_output_devices() == reloaded_outputs
        for item in [(choose(reloaded_inputs), "audioinput"), (choose(reloaded_outputs), "audiooutput")]:
            check_device(item)
        """
    )
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(backend_dir), env.get("PYTHONPATH", "")]))
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=backend_dir.parent,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if result.returncode == 77:
        pytest.skip(result.stdout.strip())
    assert result.returncode == 0, f"PortAudio integration failed:\n{result.stdout}\n{result.stderr}"
