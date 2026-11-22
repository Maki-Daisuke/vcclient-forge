from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import Response
from starlette.testclient import TestClient

from vcclient.device import DeviceConfig
from vcclient.server import vcserver_rest_api, vcserver_rest_api_devices
from vcclient.server.api_common import (
    DomainApiError,
    compute_etag,
    set_etag_header,
    verify_if_match,
)
from vcclient.server.vcserver_rest_api import get_rest_api
from vcclient.voice_changer.audio_device_manager import audio_device_manager
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.data_types import AudioDevice
from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from vcclient.voice_changer.voice_change_manager.vc_pipelines import rvc_pipeline
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


@pytest.fixture
def client() -> TestClient:
    return TestClient(get_rest_api())


@pytest.fixture
def stopped_session(monkeypatch: pytest.MonkeyPatch):
    local = LocalVoiceChangerInterface.get_instance()
    monkeypatch.setattr(local, "local_voice_changer_enabled", False)
    monkeypatch.setattr(local, "stream_running", False)
    monkeypatch.setattr(VoiceChanger, "peek_instance", classmethod(lambda cls: None))
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
    monkeypatch.setattr(conf, "recording_started", False)
    return local, conf


def _make_device(index: int, provider: str = "cpu", canonical_id: str | None = None) -> DeviceConfig:
    return DeviceConfig(
        id=index,
        canonical_id=canonical_id or f"{provider}:{index}",
        provider=provider,  # type: ignore[arg-type]
        device_index=0,
        device_type="CPU" if provider == "cpu" else "GPU",
        name=f"{provider}-{index}",
    )


def test_compute_etag_and_verify_if_match() -> None:
    first = compute_etag({"b": 2, "a": 1})
    second = compute_etag({"a": 1, "b": 2})
    assert first == second
    assert first.startswith('"') and first.endswith('"')

    verify_if_match(None, first)
    verify_if_match("", first)
    verify_if_match(first, first)
    verify_if_match(f"W/{first}", first)
    verify_if_match("*", first)
    verify_if_match(f'"other", {first}', first)

    with pytest.raises(DomainApiError) as exc_info:
        verify_if_match('"deadbeef"', first)
    err = exc_info.value
    assert err.status_code == 409
    assert err.code == "etag_mismatch"
    assert err.details == {"current_etag": first}

    resp = Response()
    set_etag_header(resp, first)
    assert resp.headers["ETag"] == first


def test_audio_devices_get_and_reload(
    client: TestClient,
    stopped_session: tuple[LocalVoiceChangerInterface, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached_in = [AudioDevice(kind="audioinput", index=1, name="Mic", host_api="WASAPI")]
    cached_out = [AudioDevice(kind="audiooutput", index=2, name="Speaker", host_api="WASAPI")]
    reloaded_in = [AudioDevice(kind="audioinput", index=3, name="USB Mic", host_api="WASAPI")]
    reloaded_out = [AudioDevice(kind="audiooutput", index=4, name="Headphones", host_api="WASAPI")]

    reload_calls = 0

    def fake_reload() -> tuple[list[AudioDevice], list[AudioDevice]]:
        nonlocal reload_calls
        reload_calls += 1
        return (reloaded_in, reloaded_out)

    monkeypatch.setattr(vcserver_rest_api_devices, "get_audio_input_devices", lambda: cached_in)
    monkeypatch.setattr(vcserver_rest_api_devices, "get_audio_output_devices", lambda: cached_out)
    monkeypatch.setattr(vcserver_rest_api_devices, "reload_audio_devices", fake_reload)

    get_res = client.get("/api/devices/audio")
    assert get_res.status_code == 200
    assert reload_calls == 0
    assert [d["name"] for d in get_res.json()["inputs"]] == ["Mic"]
    assert [d["name"] for d in get_res.json()["outputs"]] == ["Speaker"]

    post_res = client.post("/api/devices/audio/reload")
    assert post_res.status_code == 200
    assert reload_calls == 1
    assert [d["name"] for d in post_res.json()["inputs"]] == ["USB Mic"]
    assert [d["name"] for d in post_res.json()["outputs"]] == ["Headphones"]


def test_audio_device_cache_marks_initialized_even_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_list() -> tuple[list[AudioDevice], list[AudioDevice]]:
        nonlocal calls
        calls += 1
        return ([], [])

    monkeypatch.setattr(audio_device_manager, "_audio_devices_initialized", False)
    monkeypatch.setattr(audio_device_manager, "_audio_input_devices", [])
    monkeypatch.setattr(audio_device_manager, "_audio_output_devices", [])
    monkeypatch.setattr(audio_device_manager, "_list_device", fake_list)

    assert audio_device_manager.get_audio_input_devices() == []
    assert audio_device_manager.get_audio_output_devices() == []
    assert calls == 1


@pytest.mark.parametrize("active_mode", ["local_enabled", "stream_running", "bulk_started"])
def test_device_mutations_return_409_while_session_active(
    client: TestClient,
    stopped_session: tuple[LocalVoiceChangerInterface, object],
    monkeypatch: pytest.MonkeyPatch,
    active_mode: str,
) -> None:
    local, _ = stopped_session
    if active_mode == "local_enabled":
        monkeypatch.setattr(local, "local_voice_changer_enabled", True)
    elif active_mode == "stream_running":
        monkeypatch.setattr(local, "stream_running", True)
    else:
        monkeypatch.setattr(
            VoiceChanger,
            "peek_instance",
            classmethod(lambda cls: SimpleNamespace(is_convert_chunk_bulk_started=lambda: True)),
        )

    for path in (
        "/api/devices/audio/reload",
        "/api/devices/compute/reload",
        "/api/devices/compute/auto-select",
    ):
        res = client.post(path)
        assert res.status_code == 409
        body = res.json()
        assert body["code"] == "session_active"
        assert "message" in body and "details" in body


def test_compute_devices_get_and_reload(
    client: TestClient,
    stopped_session: tuple[LocalVoiceChangerInterface, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = [_make_device(0, "cpu", "cpu")]
    reloaded = [_make_device(0, "cpu", "cpu"), _make_device(1, "cuda", "cuda:0")]
    monkeypatch.setattr(vcserver_rest_api_devices, "get_device_catalog", lambda: initial)
    monkeypatch.setattr(vcserver_rest_api_devices, "reload_device_catalog", lambda: reloaded)

    get_res = client.get("/api/devices/compute")
    assert get_res.status_code == 200
    assert [d["canonical_id"] for d in get_res.json()] == ["cpu"]

    post_res = client.post("/api/devices/compute/reload")
    assert post_res.status_code == 200
    assert [d["canonical_id"] for d in post_res.json()] == ["cpu", "cuda:0"]


def test_compute_auto_select_recommends_without_mutating_config(
    client: TestClient,
    stopped_session: tuple[LocalVoiceChangerInterface, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vcclient import initializer

    _, conf = stopped_session
    monkeypatch.setattr(conf, "gpu_device_id_int", 0)
    monkeypatch.setattr(conf, "current_slot_index", 0)
    manager = ConfigurationManager.get_instance()
    save_spy = MagicMock()
    monkeypatch.setattr(manager, "save_voice_changer_configuration", save_spy)

    slot = RVCSlotInfo(slot_index=0, model_file=Path("model.onnx"))
    slot_mgr = MagicMock()
    slot_mgr.get_slot_info.return_value = slot
    monkeypatch.setattr(initializer.SlotManager, "get_instance", lambda: slot_mgr)

    catalog = [_make_device(0, "cpu", "cpu"), _make_device(1, "cuda", "cuda:0")]
    monkeypatch.setattr(initializer, "get_device_catalog", lambda: catalog)

    probed_ids: list[int] = []

    def fake_pipeline(_slot: RVCSlotInfo) -> MagicMock:
        probed_ids.append(conf.gpu_device_id_int)  # type: ignore[attr-defined]
        return MagicMock()

    monkeypatch.setattr(rvc_pipeline, "RVCPipeline", fake_pipeline)
    monkeypatch.setattr(initializer, "_verify_device_sessions", lambda _p, _d: None)

    res = client.post("/api/devices/compute/auto-select")
    assert res.status_code == 200
    body = res.json()
    assert body["compute_device_id"] == 1
    assert body["device"]["canonical_id"] == "cuda:0"
    assert probed_ids == [1]
    assert conf.gpu_device_id_int == 0  # type: ignore[attr-defined]
    save_spy.assert_not_called()


def test_compute_auto_select_error_envelopes(
    client: TestClient,
    stopped_session: tuple[LocalVoiceChangerInterface, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vcclient import initializer
    from vcclient.voice_changer import voice_changer_const

    _, conf = stopped_session
    monkeypatch.setattr(conf, "gpu_device_id_int", 2)
    empty_model_dir = tmp_path / "empty_models"
    empty_model_dir.mkdir()
    monkeypatch.setattr(voice_changer_const, "ModelDir", empty_model_dir)

    empty_slot_mgr = MagicMock()
    empty_slot_mgr.get_slot_info.return_value = RVCSlotInfo(slot_index=0, model_file=None)
    empty_slot_mgr.get_slot_infos.return_value = []
    monkeypatch.setattr(initializer.SlotManager, "get_instance", lambda: empty_slot_mgr)

    missing_res = client.post("/api/devices/compute/auto-select")
    assert missing_res.status_code == 409
    assert missing_res.json()["code"] == "model_not_found"
    assert conf.gpu_device_id_int == 2  # type: ignore[attr-defined]

    valid_slot = RVCSlotInfo(slot_index=0, model_file=Path("model.onnx"))
    valid_slot_mgr = MagicMock()
    valid_slot_mgr.get_slot_info.return_value = valid_slot
    monkeypatch.setattr(initializer.SlotManager, "get_instance", lambda: valid_slot_mgr)
    monkeypatch.setattr(initializer, "get_device_catalog", lambda: [_make_device(0, "cpu", "cpu")])
    monkeypatch.setattr(rvc_pipeline, "RVCPipeline", MagicMock(side_effect=RuntimeError("boom")))

    fail_res = client.post("/api/devices/compute/auto-select")
    assert fail_res.status_code == 500
    assert fail_res.json()["code"] == "compute_auto_select_failed"
    assert conf.gpu_device_id_int == 2  # type: ignore[attr-defined]


def test_recordings_latest_and_logs_endpoints(
    client: TestClient,
    stopped_session: tuple[LocalVoiceChangerInterface, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, conf = stopped_session
    rec_path = tmp_path / "output.wav"
    log_path = tmp_path / "vcclient.log"
    monkeypatch.setattr(vcserver_rest_api, "SERVER_IO_RECORDING_FILE_OUT", str(rec_path))
    monkeypatch.setattr(vcserver_rest_api, "LOG_FILE", log_path)

    missing_rec = client.get("/api/recordings/latest")
    assert missing_rec.status_code == 404
    assert missing_rec.json()["code"] == "recording_not_found"

    missing_log = client.get("/api/logs")
    assert missing_log.status_code == 404
    assert missing_log.json()["code"] == "log_not_found"

    rec_path.write_bytes(b"RIFF....WAVE")
    log_path.write_bytes(b"line1\nline2\n")

    monkeypatch.setattr(conf, "recording_started", True)
    active_rec = client.get("/api/recordings/latest")
    assert active_rec.status_code == 409
    assert active_rec.json()["code"] == "recording_in_progress"

    monkeypatch.setattr(conf, "recording_started", False)
    monkeypatch.setattr(
        VoiceChanger,
        "peek_instance",
        classmethod(lambda cls: SimpleNamespace(vc_info=SimpleNamespace(recording_start_flag=True))),
    )
    active_flag_rec = client.get("/api/recordings/latest")
    assert active_flag_rec.status_code == 409
    assert active_flag_rec.json()["code"] == "recording_in_progress"

    monkeypatch.setattr(VoiceChanger, "peek_instance", classmethod(lambda cls: None))
    ok_rec = client.get("/api/recordings/latest")
    assert ok_rec.status_code == 200
    assert ok_rec.headers.get("content-type") == "audio/wav"
    assert ok_rec.content == b"RIFF....WAVE"

    ok_log = client.get("/api/logs")
    assert ok_log.status_code == 200
    assert ok_log.headers.get("content-type", "").startswith("text/plain")
    assert ok_log.content == b"line1\nline2\n"
