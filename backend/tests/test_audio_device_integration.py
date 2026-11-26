"""Exercise real PortAudio device discovery, probing, and local converter stream startup in an isolated process."""

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

        from vcclient.exception import VCClientError
        from vcclient.voice_changer.audio_device_manager import (
            check_available_sample_rate,
            get_audio_input_devices,
            get_audio_output_devices,
            get_default_sample_rate,
            reload_audio_devices,
        )

        try:
            inputs, outputs = reload_audio_devices()
        except VCClientError as exc:
            print(f"Audio backend unavailable: {exc}")
            raise SystemExit(77)
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

        import threading
        import numpy as np

        from vcclient.voice_changer.data_types.voice_changer_data_types import PipelineInfo
        from vcclient.voice_changer.session_manager import session_manager as session_manager_mod
        from vcclient.voice_changer.session_manager.data_types import SessionSnapshot
        from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import (
            LocalVoiceChangerInterface,
        )
        from vcclient.voice_changer.voice_change_manager.vc_pipelines.vc_pipeline import VCPipeline
        from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger
        from vcclient.voice_changer.voice_changer_const import PitchEstimatorType

        class _SilentPipeline(VCPipeline):
            def __init__(self) -> None:
                self._pitch_estimator: PitchEstimatorType = "rmvpe"

            def get_input_sample_rate(self) -> int:
                return 16000

            def get_output_sample_rate(self) -> int:
                return 40000

            def get_input_bitdepth(self) -> type[np.generic]:
                return np.float32

            def get_output_bitdepth(self) -> type[np.generic]:
                return np.float32

            def get_chunk_sec(self) -> float:
                return 0.2

            def needs_crossfade(self) -> bool:
                return False

            def get_pitch_estimator_type(self) -> PitchEstimatorType:
                return self._pitch_estimator

            def get_gpu_device_id(self) -> int:
                return 0

            def set_pitch_estimator_type(self, pitch_estimator_type: PitchEstimatorType) -> None:
                self._pitch_estimator = pitch_estimator_type

            def get_pipeline_info(self) -> PipelineInfo:
                return PipelineInfo(
                    slot_index=-1,
                    model_id="integration-test",
                    input_sample_rate=16000,
                    output_sample_rate=40000,
                    chunk_sec=0.2,
                )

            def run(self, audio: np.ndarray, real_crossfade_sec: float) -> np.ndarray:
                out_len = int(round(self.get_output_sample_rate() * self.get_chunk_sec()))
                return np.zeros(out_len, dtype=np.float32)

        input_device = choose(reloaded_inputs)
        output_device = choose(reloaded_outputs)
        input_rate = round(get_default_sample_rate(input_device.index, "audioinput"))
        output_rate = round(get_default_sample_rate(output_device.index, "audiooutput"))
        assert input_rate > 0
        assert output_rate > 0

        snapshot = SessionSnapshot(
            model_id="integration-test",
            input_mode="server",
            compute_device_id=0,
            audio_input_device_index=input_device.index,
            audio_output_device_index=output_device.index,
            audio_monitor_device_index=-1,
            output_gain=0.0,
        )
        vc = VoiceChanger.get_or_create_raw()
        vc.configure_for_session(
            snapshot,
            _SilentPipeline(),
            input_sample_rate=input_rate,
            output_sample_rate=output_rate,
            monitor_sample_rate=None,
        )
        vc.start_convert_chunk_bulk()

        local = LocalVoiceChangerInterface.get_instance()
        local.vc = vc
        local.start()

        streams_opened = threading.Event()
        cached_reads_ok = threading.Event()
        orig_notify = session_manager_mod.notify_audio_started

        def on_audio_started() -> None:
            orig_notify()
            streams_opened.set()

        session_manager_mod.notify_audio_started = on_audio_started

        def control_loop() -> None:
            try:
                assert streams_opened.wait(timeout=10.0), "Local audio streams did not open in time"
                assert local.stream_running is True
                assert get_audio_input_devices() == reloaded_inputs
                assert get_audio_output_devices() == reloaded_outputs
                cached_reads_ok.set()
            finally:
                local.stop()

        controller = threading.Thread(target=control_loop)
        controller.start()
        try:
            # Must succeed from the main thread even though PortAudio was initialized on audio-device-worker.
            local.run()
        finally:
            local.stop()
            controller.join(timeout=5.0)
            session_manager_mod.notify_audio_started = orig_notify

        assert not controller.is_alive()
        assert streams_opened.is_set()
        assert cached_reads_ok.is_set()
        assert not local.stream_running
        assert not vc.is_convert_chunk_bulk_started()
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
