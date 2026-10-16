import numpy as np
import pytest
from starlette.testclient import TestClient

from vcclient.server.vcserver_rest_api import RestAPI


@pytest.fixture(scope="module")
def client():
    app = RestAPI.get_instance()
    return TestClient(app)


def test_hello_endpoint(client):
    response = client.get("/api/hello")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_convert_chunk_endpoint(client):
    from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager

    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
    conf.pass_through = True
    conf.input_sample_rate = 48000
    conf.output_sample_rate = 48000
    ConfigurationManager.get_instance().set_voice_changer_configuration(conf)

    sample_rate = 48000
    duration_sec = 0.5
    num_samples = int(sample_rate * duration_sec)
    t = np.linspace(0, duration_sec, num_samples, endpoint=False, dtype=np.float32)
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)
    raw_bytes = audio.tobytes()

    files = {"waveform": ("chunk.bin", raw_bytes, "application/octet-stream")}
    headers = {"x-timestamp": "12345"}

    response = client.post("/api/voice-changer/convert_chunk", files=files, headers=headers)
    assert response.status_code == 200
    res_audio = np.frombuffer(response.content, dtype=np.float32)
    assert len(res_audio) > 0
    assert not np.isnan(res_audio).any()


def test_frontend_root():
    from vcclient.server.vcserver_socketio import serverio_app

    c = TestClient(serverio_app)
    response = c.get("/")
    assert response.status_code == 200
    assert "html" in response.headers.get("content-type", "")


def test_merge_models_not_supported(client):
    import json

    response = client.post(
        "/api/slot-manager/slots/operation/merge_models",
        json={"files": [{"slot_index": 0, "strength": 0.5}]},
    )
    assert response.status_code == 400
    data = response.json()
    detail = json.loads(data["detail"])
    assert detail["code"] == "NOT_SUPPORTED"


def test_convert_chunk_passes_direct_from_server_when_perf_monitor_disabled(monkeypatch):
    from unittest.mock import MagicMock

    from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
    from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger

    vc = VoiceChanger.get_instance()
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
    monkeypatch.setattr(conf, "enable_performance_monitor", False)

    mock_internal = MagicMock(return_value=(np.zeros(100), None))
    monkeypatch.setattr(vc, "_convert_chunk", mock_internal)

    dummy_wave = np.zeros(100, dtype=np.float32)
    vc.convert_chunk(dummy_wave, direct_from_server=True)

    mock_internal.assert_called_once_with(dummy_wave, direct_from_server=True)
