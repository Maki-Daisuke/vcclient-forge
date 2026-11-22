from __future__ import annotations

import json
import threading
import time
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient
from onnx import TensorProto, helper
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from vcclient.device import DeviceConfig
from vcclient.server import api_common, vcserver_rest_api, vcserver_rest_api_devices
from vcclient.server.vcserver_rest_api import get_rest_api
from vcclient.voice_changer import session_manager, voice_changer_const
from vcclient.voice_changer.configuration_manager import configuration_manager as configuration_manager_mod
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.data_types import AudioDevice
from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.model_catalog import model_catalog_manager
from vcclient.voice_changer.session_manager import LOCKED_SESSION_FIELDS
from vcclient.voice_changer.session_manager import session_manager as session_manager_mod
from vcclient.voice_changer.voice_change_manager import voice_changer as voice_changer_mod
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from vcclient.voice_changer.voice_change_manager.vc_pipelines.pipeline_manager import PipelineManager
from vcclient.voice_changer.voice_change_manager.vc_pipelines.vc_pipeline import VCPipeline
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger
from vcclient.voice_changer.voice_changer_const import PitchEstimatorType


def _make_rvc_onnx_bytes(*, sample_rate: int = 40000, is_f0: bool = True) -> bytes:
    graph = helper.make_graph(
        [helper.make_node("Identity", ["x"], ["y"])],
        "test_rvc",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 1])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 1])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9)
    meta = model.metadata_props.add()
    meta.key = "metadata"
    meta.value = json.dumps(
        {
            "version": "3.0",
            "f0": 1 if is_f0 else 0,
            "samplingRate": sample_rate,
            "embedder": "hubert_base_l9fp",
        }
    )
    return model.SerializeToString()


class _DummyPipeline(VCPipeline):
    def __init__(self, slot_info: RVCSlotInfo, *, snapshot_getter=None, extra_frame_sec: float | None = None) -> None:
        self._slot_info = slot_info
        self._snapshot_getter = snapshot_getter
        self._fixed_extra_frame_sec = extra_frame_sec
        self.observed_runs: list[dict[str, object]] = []

    def get_input_sample_rate(self) -> int:
        return 16000

    def get_output_sample_rate(self) -> int:
        return self._slot_info.sample_rate

    def get_input_bitdepth(self) -> type[np.generic]:
        return np.float32

    def get_output_bitdepth(self) -> type[np.generic]:
        return np.float32

    def get_chunk_sec(self) -> float:
        snap = self._snapshot_getter() if self._snapshot_getter is not None else None
        if snap is not None:
            return float(snap.chunk_sec)
        return self._slot_info.chunk_sec

    def needs_crossfade(self) -> bool:
        return False

    def get_pitch_estimator_type(self) -> PitchEstimatorType:
        snap = self._snapshot_getter() if self._snapshot_getter is not None else None
        if snap is not None:
            return snap.pitch_estimator
        return self._slot_info.pitch_estimator

    def get_gpu_device_id(self) -> int:
        return 0

    def set_pitch_estimator_type(self, pitch_estimator_type: PitchEstimatorType) -> None:
        self._slot_info.pitch_estimator = pitch_estimator_type

    def get_pipeline_info(self) -> dict[str, object]:
        return {"model_id": getattr(self._slot_info, "model_id", None)}

    def run(self, audio: np.ndarray, real_crossfade_sec: float) -> np.ndarray:
        snap = self._snapshot_getter() if self._snapshot_getter is not None else None
        if snap is not None:
            self.observed_runs.append(
                {
                    "model_id": snap.model_id,
                    "pitch_shift": snap.pitch_shift,
                    "index_ratio": snap.index_ratio,
                    "noise_gate": snap.noise_gate,
                    "extra_frame_sec": snap.extra_frame_sec,
                    "chunk_sec": snap.chunk_sec,
                }
            )
        out_len = int(round(self.get_output_sample_rate() * self.get_chunk_sec()))
        return np.full(out_len, 0.25, dtype=np.float32)


@pytest.fixture
def session_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[TestClient, str, str], None, None]:
    model_dir = tmp_path / "model_dir"
    model_dir.mkdir(parents=True, exist_ok=True)
    config_file = tmp_path / "vc_conf.json"
    rec_file = str(tmp_path / "output.wav")

    monkeypatch.setattr(voice_changer_const, "ModelDir", model_dir)
    monkeypatch.setattr(voice_changer_const, "ConfigFile", config_file)
    monkeypatch.setattr(configuration_manager_mod, "ConfigFile", config_file)
    monkeypatch.setattr(vcserver_rest_api, "SERVER_IO_RECORDING_FILE_OUT", rec_file)
    monkeypatch.setattr(voice_changer_mod, "SERVER_IO_RECORDING_FILE_OUT", rec_file)

    monkeypatch.setattr(ConfigurationManager, "_instance", None)
    monkeypatch.setattr(VoiceChanger, "_instance", None)
    monkeypatch.setattr(LocalVoiceChangerInterface, "_instance", None)
    monkeypatch.setattr(api_common, "_active_model_id_getter", None)
    monkeypatch.setattr(model_catalog_manager, "_cached_model_dir", None)
    monkeypatch.setattr(model_catalog_manager, "_cached_slot_infos", {})

    devices = [
        DeviceConfig(id=0, canonical_id="cpu:0", provider="cpu", device_index=0, device_type="CPU", name="CPU"),
        DeviceConfig(
            id=1,
            canonical_id="cuda:0",
            provider="cuda",
            device_index=0,
            device_type="GPU",
            name="CUDA GPU",
        ),
    ]
    monkeypatch.setattr(session_manager_mod, "get_device_catalog", lambda: devices)
    monkeypatch.setattr(
        "vcclient.voice_changer.settings_manager.settings_manager.get_device_catalog",
        lambda: devices,
    )
    monkeypatch.setattr(vcserver_rest_api_devices, "get_device_catalog", lambda: devices)

    in_dev = AudioDevice(kind="audioinput", index=1, name="Mic", host_api="WASAPI", default_samplerate=48000)
    out_dev = AudioDevice(kind="audiooutput", index=2, name="Speaker", host_api="WASAPI", default_samplerate=48000)
    mon_dev = AudioDevice(kind="audiooutput", index=3, name="Monitor", host_api="WASAPI", default_samplerate=44100)

    monkeypatch.setattr(session_manager_mod, "get_audio_input_device", lambda idx: in_dev if idx == 1 else None)
    monkeypatch.setattr(
        session_manager_mod,
        "get_audio_output_device",
        lambda idx: out_dev if idx == 2 else (mon_dev if idx == 3 else None),
    )
    monkeypatch.setattr(
        session_manager_mod,
        "check_available_sample_rate",
        lambda idx, rate, kind: rate in (44100, 48000),
    )
    monkeypatch.setattr(
        session_manager_mod,
        "get_default_sample_rate",
        lambda idx, kind: 44100.0 if idx == 3 else 48000.0,
    )

    session_manager.reset_session_state()

    with TestClient(get_rest_api()) as client:
        onnx_bytes = _make_rvc_onnx_bytes()
        r1 = client.post(
            "/api/models",
            data={"name": "Alpha Model"},
            files={"model_file": ("alpha.onnx", onnx_bytes, "application/octet-stream")},
        )
        assert r1.status_code == 201, r1.text
        r2 = client.post(
            "/api/models",
            data={"name": "Beta Model"},
            files={"model_file": ("beta.onnx", onnx_bytes, "application/octet-stream")},
        )
        assert r2.status_code == 201, r2.text
        try:
            yield (client, r1.json()["id"], r2.json()["id"])
        finally:
            session_manager.reset_session_state()


def _wait_for_status(client: TestClient, target: str, timeout: float = 5.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_payload: dict[str, object] = {}
    while time.monotonic() < deadline:
        res = client.get("/api/session")
        assert res.status_code == 200
        last_payload = res.json()
        if last_payload["status"] == target:
            return last_payload
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for session status '{target}'; last={last_payload}")


def test_get_session_is_readonly_when_stopped(
    session_env: tuple[TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _id1, _id2 = session_env
    get_instance_spy = MagicMock(
        side_effect=AssertionError("VoiceChanger.get_instance must not run on GET /api/session")
    )
    pipeline_spy = MagicMock(
        side_effect=AssertionError("PipelineManager.get_pipeline must not run on GET /api/session")
    )
    monkeypatch.setattr(VoiceChanger, "get_instance", get_instance_spy)
    monkeypatch.setattr(PipelineManager, "get_pipeline", pipeline_spy)

    res = client.get("/api/session")
    assert res.status_code == 200
    assert "ETag" in res.headers
    payload = res.json()
    assert payload == {
        "status": "stopped",
        "snapshot": None,
        "locked_fields": list(LOCKED_SESSION_FIELDS),
        "input_sample_rate": None,
        "output_sample_rate": None,
        "monitor_sample_rate": None,
        "last_error": None,
    }


def test_put_session_validates_before_mutating_state(
    session_env: tuple[TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, id1, _id2 = session_env
    pipeline_spy = MagicMock(side_effect=AssertionError("Pipeline build must not start on validation failure"))
    monkeypatch.setattr(PipelineManager, "get_pipeline", pipeline_spy)

    # Missing model -> 404 model_not_found
    r_missing = client.put("/api/session", json={"model_id": "does-not-exist", "input_mode": "client"})
    assert r_missing.status_code == 404
    assert r_missing.json()["code"] == "model_not_found"

    # Out-of-range compute device -> 422 invalid_compute_device
    r_dev = client.put("/api/session", json={"model_id": id1, "compute_device_id": 99, "input_mode": "client"})
    assert r_dev.status_code == 422
    assert r_dev.json()["code"] == "invalid_compute_device"

    # Invalid server audio device / unsupported rate -> 422 invalid_audio_device
    r_audio = client.put(
        "/api/session",
        json={
            "model_id": id1,
            "input_mode": "server",
            "audio_input_device_index": -1,
            "audio_output_device_index": 2,
        },
    )
    assert r_audio.status_code == 422
    assert r_audio.json()["code"] == "invalid_audio_device"

    r_rate = client.put(
        "/api/session",
        json={
            "model_id": id1,
            "input_mode": "server",
            "audio_input_device_index": 1,
            "audio_output_device_index": 2,
            "audio_input_device_sample_rate": 192000,
        },
    )
    assert r_rate.status_code == 422
    assert r_rate.json()["code"] == "invalid_audio_device"

    # Filter cutoffs invalid order / Nyquist violation -> 422 invalid_filter_cutoff
    r_order = client.put(
        "/api/session",
        json={
            "model_id": id1,
            "input_mode": "client",
            "high_pass_filter_cutoff": 5000.0,
            "low_pass_filter_cutoff": 5000.0,
        },
    )
    assert r_order.status_code == 422
    assert r_order.json()["code"] == "invalid_filter_cutoff"

    r_nyquist = client.put(
        "/api/session",
        json={
            "model_id": id1,
            "input_mode": "server",
            "audio_input_device_index": 1,
            "audio_output_device_index": 2,
            "audio_input_device_sample_rate": 44100,
            "enable_low_pass_filter": True,
            "low_pass_filter_cutoff": 22050.0,
        },
    )
    assert r_nyquist.status_code == 422
    assert r_nyquist.json()["code"] == "invalid_filter_cutoff"

    assert client.get("/api/session").json()["status"] == "stopped"
    pipeline_spy.assert_not_called()


def test_put_session_async_startup_and_starting_guards(
    session_env: tuple[TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, id1, _id2 = session_env
    entered = threading.Event()
    release = threading.Event()
    build_calls: list[str | None] = []

    def fake_get_pipeline(cls, slot_info, *, device=None, extra_frame_sec=None, snapshot_getter=None):
        build_calls.append(getattr(slot_info, "model_id", None))
        entered.set()
        assert release.wait(timeout=5.0)
        return _DummyPipeline(slot_info, snapshot_getter=snapshot_getter, extra_frame_sec=extra_frame_sec)

    monkeypatch.setattr(PipelineManager, "get_pipeline", classmethod(fake_get_pipeline))
    original_start = LocalVoiceChangerInterface.start

    def start_and_report_ready(local):
        original_start(local)
        threading.Thread(target=session_manager_mod.notify_audio_started, daemon=True).start()

    monkeypatch.setattr(LocalVoiceChangerInterface, "start", start_and_report_ready)

    snapshot = {
        "model_id": id1,
        "input_mode": "server",
        "compute_device_id": 1,
        "audio_input_device_index": 1,
        "audio_output_device_index": 2,
        "audio_monitor_device_index": 3,
    }
    start_res = client.put("/api/session", json=snapshot)
    assert start_res.status_code == 202, start_res.text
    start_json = start_res.json()
    assert start_json["status"] == "starting"
    assert start_json["input_sample_rate"] is None
    assert start_json["output_sample_rate"] is None
    assert start_json["monitor_sample_rate"] is None
    assert "ETag" in start_res.headers

    assert entered.wait(timeout=5.0)

    # Guards while status == "starting"
    del_sess = client.delete("/api/session")
    assert del_sess.status_code == 409
    assert del_sess.json()["code"] == "session_starting"

    put_sess = client.put("/api/session", json=snapshot)
    assert put_sess.status_code == 409
    assert put_sess.json()["code"] == "session_starting"

    del_model = client.delete(f"/api/models/{id1}")
    assert del_model.status_code == 409
    assert del_model.json()["code"] == "model_in_use"

    rename_model = client.put(f"/api/models/{id1}", json={"name": "Cannot Rename While Starting"})
    assert rename_model.status_code == 409
    assert rename_model.json()["code"] == "model_in_use"

    for device_op in (
        "/api/devices/audio/reload",
        "/api/devices/compute/reload",
        "/api/devices/compute/auto-select",
    ):
        dev_res = client.post(device_op)
        assert dev_res.status_code == 409, f"{device_op} -> {dev_res.status_code} {dev_res.text}"
        assert dev_res.json()["code"] == "session_active"

    release.set()
    running = _wait_for_status(client, "running")
    assert running["input_sample_rate"] == 48000
    assert running["output_sample_rate"] == 48000
    assert running["monitor_sample_rate"] == 44100
    assert build_calls == [id1]

    stop_res = client.delete("/api/session")
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "stopped"


def test_server_audio_open_failure_is_reported(
    session_env: tuple[TestClient, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, model_id, _ = session_env

    def fake_get_pipeline(cls, slot_info, *, device=None, extra_frame_sec=None, snapshot_getter=None):
        return _DummyPipeline(slot_info, snapshot_getter=snapshot_getter, extra_frame_sec=extra_frame_sec)

    monkeypatch.setattr(PipelineManager, "get_pipeline", classmethod(fake_get_pipeline))
    start = client.put(
        "/api/session",
        json={
            "model_id": model_id,
            "input_mode": "server",
            "audio_input_device_index": 1,
            "audio_output_device_index": 2,
        },
    )
    assert start.status_code == 202
    local = LocalVoiceChangerInterface.get_instance()
    deadline = time.monotonic() + 5
    while not local.local_voice_changer_enabled and time.monotonic() < deadline:
        time.sleep(0.01)
    assert local.local_voice_changer_enabled
    assert client.get("/api/session").json()["status"] == "starting"

    def fail_open(*args, **kwargs):
        raise RuntimeError("Audio device unavailable")

    monkeypatch.setattr(
        "vcclient.voice_changer.voice_change_manager.local_voice_changer_interface.sd.InputStream", fail_open
    )
    with pytest.raises(RuntimeError, match="Audio device unavailable") as failure:
        local.run()
    local.stop()
    session_manager_mod.report_audio_failure(failure.value)
    stopped = _wait_for_status(client, "stopped")
    assert stopped["last_error"]["message"] == "Audio device unavailable"
    assert not VoiceChanger.peek_instance().is_convert_chunk_bulk_started()


def test_server_session_is_running_only_after_audio_streams_open(
    session_env: tuple[TestClient, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from vcclient.voice_changer.voice_change_manager import local_voice_changer_interface as local_module

    client, model_id, _ = session_env

    def fake_get_pipeline(cls, slot_info, *, device=None, extra_frame_sec=None, snapshot_getter=None):
        return _DummyPipeline(slot_info, snapshot_getter=snapshot_getter, extra_frame_sec=extra_frame_sec)

    monkeypatch.setattr(PipelineManager, "get_pipeline", classmethod(fake_get_pipeline))
    response = client.put(
        "/api/session",
        json={
            "model_id": model_id,
            "input_mode": "server",
            "audio_input_device_index": 1,
            "audio_output_device_index": 2,
        },
    )
    assert response.status_code == 202
    local = LocalVoiceChangerInterface.get_instance()
    deadline = time.monotonic() + 5
    while not local.local_voice_changer_enabled and time.monotonic() < deadline:
        time.sleep(0.01)
    assert local.local_voice_changer_enabled
    opened: list[str] = []

    class FakeStream:
        samplerate = 48000
        channels = 1
        dtype = "float32"

        def __init__(self, *, device, **kwargs):
            self.device = device

        def __enter__(self):
            assert client.get("/api/session").json()["status"] == "starting"
            opened.append(str(self.device))
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(local_module.sd, "InputStream", FakeStream)
    monkeypatch.setattr(local_module.sd, "OutputStream", FakeStream)
    monkeypatch.setattr(
        local_module, "wait_for_stop", lambda timeout: setattr(local, "local_voice_changer_enabled", False)
    )
    local.run()
    assert opened == ["1", "2"]
    running = client.get("/api/session").json()
    assert running["status"] == "running"
    assert running["input_sample_rate"] == 48000
    assert client.delete("/api/session").status_code == 200


def test_session_startup_failure_cleans_up_and_exposes_last_error(
    session_env: tuple[TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, id1, _id2 = session_env

    def failing_pipeline(cls, slot_info, *, device=None, extra_frame_sec=None, snapshot_getter=None):
        raise RuntimeError("Simulated ONNX load failure")

    monkeypatch.setattr(PipelineManager, "get_pipeline", classmethod(failing_pipeline))

    res = client.put("/api/session", json={"model_id": id1, "input_mode": "client"})
    assert res.status_code == 202

    stopped = _wait_for_status(client, "stopped")
    assert stopped["snapshot"] is None
    assert stopped["input_sample_rate"] is None
    assert stopped["output_sample_rate"] is None
    assert stopped["monitor_sample_rate"] is None
    assert stopped["last_error"] is not None
    assert stopped["last_error"]["code"] == "session_start_failed"
    assert "Simulated ONNX load failure" in stopped["last_error"]["message"]

    vc = VoiceChanger.peek_instance()
    if vc is not None:
        assert vc.vc_pipeline is None
        assert not vc.is_convert_chunk_bulk_started()


def test_session_warmup_failure_is_reported(
    session_env: tuple[TestClient, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from vcclient.voice_changer.voice_change_manager.vc_pipelines import pipeline_manager

    client, model_id, _ = session_env

    class WarmupFailure(_DummyPipeline):
        def __init__(self, slot_info, *, device=None, extra_frame_sec=None, snapshot_getter=None):
            super().__init__(slot_info, snapshot_getter=snapshot_getter, extra_frame_sec=extra_frame_sec)

        def warmup(self):
            raise RuntimeError("Warmup failed")

    monkeypatch.setattr(pipeline_manager, "RVCPipeline", WarmupFailure)
    response = client.put("/api/session", json={"model_id": model_id, "input_mode": "client"})
    assert response.status_code == 202
    stopped = _wait_for_status(client, "stopped")
    assert stopped["last_error"]["message"] == "Warmup failed"


def test_running_session_live_updates_conflict_diff_etag_and_recording(
    session_env: tuple[TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, id1, id2 = session_env
    build_count = 0

    def fake_get_pipeline(cls, slot_info, *, device=None, extra_frame_sec=None, snapshot_getter=None):
        nonlocal build_count
        build_count += 1
        return _DummyPipeline(slot_info, snapshot_getter=snapshot_getter, extra_frame_sec=extra_frame_sec)

    monkeypatch.setattr(PipelineManager, "get_pipeline", classmethod(fake_get_pipeline))

    base_snapshot = {
        "model_id": id1,
        "input_mode": "client",
        "pitch_shift": 0,
        "index_ratio": 0.0,
        "chunk_sec": 0.5,
        "pitch_estimator": "rmvpe",
        "extra_frame_sec": 0.5,
        "compute_device_id": 0,
        "input_gain": 2.0,
        "output_gain": 1.0,
        "enable_high_pass_filter": True,
        "high_pass_filter_cutoff": 100.0,
        "enable_low_pass_filter": True,
        "low_pass_filter_cutoff": 12000.0,
        "noise_gate": -35.0,
        "pass_through": False,
        "recording": True,
        "enable_performance_monitor": True,
        "realtime_process_status_enabled": True,
        "realtime_output_status_enabled": True,
    }
    start_res = client.put("/api/session", json=base_snapshot)
    assert start_res.status_code == 202
    running = _wait_for_status(client, "running")
    assert running["input_sample_rate"] == 48000
    assert running["output_sample_rate"] == 48000
    assert running["monitor_sample_rate"] is None

    etag_res = client.get("/api/session")
    etag = etag_res.headers["ETag"]

    # Recording active -> GET /api/recordings/latest returns 409 recording_in_progress
    rec_busy = client.get("/api/recordings/latest")
    assert rec_busy.status_code == 409
    assert rec_busy.json()["code"] == "recording_in_progress"

    # Push one converted chunk so output_record is non-empty
    vc = VoiceChanger.peek_instance()
    assert vc is not None
    vc._convert_chunk(np.full(24000, 0.25, dtype=np.float32))

    # Stale If-Match rejected
    stale = client.put("/api/session", json={**base_snapshot, "pitch_shift": 3}, headers={"If-Match": '"wrong"'})
    assert stale.status_code == 409
    assert stale.json()["code"] == "etag_mismatch"

    # Live-safe update -> 200 OK without rebuild, and repeating recording=True keeps buffer
    live_snap = {
        **base_snapshot,
        "pitch_shift": 4,
        "index_ratio": 0.7,
        "input_gain": 1.4,
        "output_gain": 0.8,
        "enable_high_pass_filter": False,
        "high_pass_filter_cutoff": 120.0,
        "noise_gate": -45.0,
        "pass_through": True,
        "recording": True,
        "enable_performance_monitor": False,
    }
    live_res = client.put("/api/session", json=live_snap, headers={"If-Match": etag})
    assert live_res.status_code == 200, live_res.text
    assert live_res.headers["ETag"] != etag
    assert build_count == 1
    assert len(vc.output_record) == 1
    assert vc.vc_info.recording_start_flag is True

    # Toggle recording=False -> finalizes WAV and allows GET /api/recordings/latest
    stop_rec_res = client.put("/api/session", json={**live_snap, "recording": False})
    assert stop_rec_res.status_code == 200
    assert vc.vc_info.recording_start_flag is False

    rec_ok = client.get("/api/recordings/latest")
    assert rec_ok.status_code == 200
    assert rec_ok.headers["content-type"].startswith("audio/wav")

    # Rebuild-required changes -> 409 session_rebuild_required
    conflict_res = client.put(
        "/api/session",
        json={
            **live_snap,
            "recording": False,
            "model_id": id2,
            "chunk_sec": 0.8,
        },
    )
    assert conflict_res.status_code == 409
    assert conflict_res.json()["code"] == "session_rebuild_required"
    assert conflict_res.json()["details"]["conflicting_fields"] == ["model_id", "chunk_sec"]
    assert client.get("/api/session").json()["snapshot"]["model_id"] == id1


def test_running_session_is_isolated_from_storage_and_configuration_manager(
    session_env: tuple[TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, id1, _id2 = session_env
    created_pipelines: list[_DummyPipeline] = []

    def fake_get_pipeline(cls, slot_info, *, device=None, extra_frame_sec=None, snapshot_getter=None):
        pipe = _DummyPipeline(slot_info, snapshot_getter=snapshot_getter, extra_frame_sec=extra_frame_sec)
        created_pipelines.append(pipe)
        return pipe

    monkeypatch.setattr(PipelineManager, "get_pipeline", classmethod(fake_get_pipeline))

    snap = {
        "model_id": id1,
        "input_mode": "client",
        "pitch_shift": 2,
        "index_ratio": 0.4,
        "noise_gate": -30.0,
        "extra_frame_sec": 0.5,
        "enable_high_pass_filter": False,
        "enable_low_pass_filter": False,
    }
    assert client.put("/api/session", json=snap).status_code == 202
    _wait_for_status(client, "running")

    # Mutate both /api/settings and /api/models/{id1} on disk while session is running
    cur_settings = client.get("/api/settings").json()
    assert (
        client.put(
            "/api/settings",
            json={**cur_settings, "noise_gate": -90.0, "extra_frame_sec": 1.5, "input_gain": 9.0},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/api/models/{id1}",
            json={"pitch_shift": -12, "index_ratio": 0.95, "chunk_sec": 1.2},
        ).status_code
        == 200
    )

    # Assert ConfigurationManager is not queried during convert_chunk
    cm_spy = MagicMock(
        side_effect=AssertionError("ConfigurationManager.get_voice_changer_configuration must not be called mid-run")
    )
    monkeypatch.setattr(ConfigurationManager, "get_voice_changer_configuration", cm_spy)

    vc = VoiceChanger.peek_instance()
    assert vc is not None
    vc._convert_chunk(np.full(24000, 0.25, dtype=np.float32))
    cm_spy.assert_not_called()

    assert len(created_pipelines) == 1
    assert created_pipelines[0].observed_runs[-1] == {
        "model_id": id1,
        "pitch_shift": 2,
        "index_ratio": 0.4,
        "noise_gate": -30.0,
        "extra_frame_sec": 0.5,
        "chunk_sec": 0.5,
    }


def test_delete_session_finalizes_recording_and_is_idempotent(
    session_env: tuple[TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, id1, _id2 = session_env

    def fake_get_pipeline(cls, slot_info, *, device=None, extra_frame_sec=None, snapshot_getter=None):
        return _DummyPipeline(slot_info, snapshot_getter=snapshot_getter, extra_frame_sec=extra_frame_sec)

    monkeypatch.setattr(PipelineManager, "get_pipeline", classmethod(fake_get_pipeline))

    res = client.put(
        "/api/session",
        json={
            "model_id": id1,
            "input_mode": "client",
            "recording": True,
            "enable_high_pass_filter": False,
            "enable_low_pass_filter": False,
        },
    )
    assert res.status_code == 202
    _wait_for_status(client, "running")

    vc = VoiceChanger.peek_instance()
    assert vc is not None
    vc._convert_chunk(np.full(24000, 0.2, dtype=np.float32))

    stop_res = client.delete("/api/session")
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "stopped"
    assert stop_res.json()["snapshot"] is None
    assert not vc.is_convert_chunk_bulk_started()
    assert vc.vc_info.recording_start_flag is False

    rec = client.get("/api/recordings/latest")
    assert rec.status_code == 200
    assert rec.headers["content-type"].startswith("audio/wav")

    # Idempotent delete when already stopped
    stop_again = client.delete("/api/session")
    assert stop_again.status_code == 200
    assert stop_again.json()["status"] == "stopped"


def test_audio_websocket_requires_client_session_and_supports_superseded_handoff(
    session_env: tuple[TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, id1, _id2 = session_env
    entered = threading.Event()
    release = threading.Event()

    def fake_get_pipeline(cls, slot_info, *, device=None, extra_frame_sec=None, snapshot_getter=None):
        if entered.is_set():
            return _DummyPipeline(slot_info, snapshot_getter=snapshot_getter, extra_frame_sec=extra_frame_sec)
        entered.set()
        release.wait(timeout=5.0)
        return _DummyPipeline(slot_info, snapshot_getter=snapshot_getter, extra_frame_sec=extra_frame_sec)

    monkeypatch.setattr(PipelineManager, "get_pipeline", classmethod(fake_get_pipeline))
    original_start = LocalVoiceChangerInterface.start

    def start_and_report_ready(local):
        original_start(local)
        threading.Thread(target=session_manager_mod.notify_audio_started, daemon=True).start()

    monkeypatch.setattr(LocalVoiceChangerInterface, "start", start_and_report_ready)

    # 1. Stopped -> rejected with 1008
    with client.websocket_connect("/api/ws/audio") as ws:
        with pytest.raises(WebSocketDisconnect) as exc_stopped:
            ws.receive_bytes()
        assert exc_stopped.value.code == 1008

    # 2. Server mode -> rejected with 1008; starting -> rejected with 1008
    assert (
        client.put(
            "/api/session",
            json={
                "model_id": id1,
                "input_mode": "server",
                "audio_input_device_index": 1,
                "audio_output_device_index": 2,
            },
        ).status_code
        == 202
    )
    assert entered.wait(timeout=5.0)
    with client.websocket_connect("/api/ws/audio") as ws_starting:
        with pytest.raises(WebSocketDisconnect) as exc_starting:
            ws_starting.receive_bytes()
        assert exc_starting.value.code == 1008

    release.set()
    _wait_for_status(client, "running")
    with client.websocket_connect("/api/ws/audio") as ws_server:
        with pytest.raises(WebSocketDisconnect) as exc_server:
            ws_server.receive_bytes()
        assert exc_server.value.code == 1008

    assert client.delete("/api/session").status_code == 200

    # 3. Client mode running -> accepts audio frames, hands off with 4001 "superseded", and DELETE closes with 1000
    assert (
        client.put(
            "/api/session",
            json={
                "model_id": id1,
                "input_mode": "client",
                "chunk_sec": 0.1,
                "enable_high_pass_filter": False,
                "enable_low_pass_filter": False,
            },
        ).status_code
        == 202
    )
    _wait_for_status(client, "running")

    # Replace resamplers on vc for fast deterministic PCM conversion in test
    vc = VoiceChanger.peek_instance()
    assert vc is not None
    monkeypatch.setattr(vc, "_exec_resample_in", lambda w: w)
    monkeypatch.setattr(vc, "_exec_resample_out", lambda w: w)
    monkeypatch.setattr(vc, "_exec_resample_monitor", lambda w: w)

    pcm_chunk = np.full(4800, 0.2, dtype="<f4")

    def _send_and_receive_audio(ws: WebSocketTestSession) -> bytes:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and vc.convert_chunk_bulk_queue_out.qsize() == 0:
            ws.send_bytes(pcm_chunk.tobytes())
            time.sleep(0.05)
        assert vc.convert_chunk_bulk_queue_out.qsize() > 0
        ws.send_bytes(pcm_chunk.tobytes())
        return ws.receive_bytes()

    with client.websocket_connect("/api/ws/audio") as ws1:
        received = _send_and_receive_audio(ws1)
        assert len(received) > 0

        with client.websocket_connect("/api/ws/audio") as ws2:
            with pytest.raises(WebSocketDisconnect) as exc_superseded:
                while True:
                    ws1.receive_bytes()
            assert exc_superseded.value.code == 4001
            assert exc_superseded.value.reason == "superseded"

            # Session stays running after handoff and ws2 converts frames
            assert client.get("/api/session").json()["status"] == "running"
            received_2 = _send_and_receive_audio(ws2)
            assert len(received_2) > 0

            # DELETE /api/session closes active ws2 with code 1000
            stop_res = client.delete("/api/session")
            assert stop_res.status_code == 200
            assert stop_res.json()["status"] == "stopped"
            with pytest.raises(WebSocketDisconnect) as exc_clean:
                while True:
                    ws2.receive_bytes()
            assert exc_clean.value.code == 1000


def test_audio_websocket_keeps_session_running_on_unexpected_disconnect(
    session_env: tuple[TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, id1, _id2 = session_env

    def fake_get_pipeline(cls, slot_info, *, device=None, extra_frame_sec=None, snapshot_getter=None):
        return _DummyPipeline(slot_info, snapshot_getter=snapshot_getter, extra_frame_sec=extra_frame_sec)

    monkeypatch.setattr(PipelineManager, "get_pipeline", classmethod(fake_get_pipeline))

    assert (
        client.put(
            "/api/session",
            json={"model_id": id1, "input_mode": "client", "recording": True},
        ).status_code
        == 202
    )
    _wait_for_status(client, "running")

    with client.websocket_connect("/api/ws/audio"):
        pass

    state = client.get("/api/session").json()
    assert state["status"] == "running"
    assert state["snapshot"]["recording"] is True
