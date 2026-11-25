import numpy as np
import pytest
from starlette.testclient import TestClient

from vcclient.server.vcserver_rest_api import get_rest_api


@pytest.fixture(scope="module")
def client():
    app = get_rest_api()
    return TestClient(app)


def test_convert_chunk_passthrough(monkeypatch):
    from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
    from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger

    manager = ConfigurationManager.get_instance()
    conf = manager.get_voice_changer_configuration()
    monkeypatch.setattr(conf, "pass_through", True)
    monkeypatch.setattr(conf, "input_sample_rate", 48000)
    monkeypatch.setattr(conf, "output_sample_rate", 48000)
    monkeypatch.setattr(manager, "save_voice_changer_configuration", lambda: None)
    manager.set_voice_changer_configuration(conf)

    sample_rate = 48000
    duration_sec = 0.5
    num_samples = int(sample_rate * duration_sec)
    t = np.linspace(0, duration_sec, num_samples, endpoint=False, dtype=np.float32)
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)

    res_audio, _ = VoiceChanger.get_instance().convert_chunk(audio)
    assert res_audio is not None
    assert len(res_audio) > 0
    assert not np.isnan(res_audio).any()


def test_frontend_root():
    from vcclient.server.vcserver import VCServer

    server = VCServer(host="127.0.0.1", port=0)
    c = TestClient(server.app)
    response = c.get("/")
    assert response.status_code == 200
    assert "html" in response.headers.get("content-type", "")


def test_unsupported_api_and_removed_legacy_routes_return_404(client):
    # 存在しないAPIエンドポイント・撤去済みレガシーAPIは統一 Domain JSON 404 を返すこと
    for method, path in (
        ("GET", "/api/unknown_route"),
        ("POST", "/api/unknown_route"),
        ("GET", "/api/slot-manager/slots"),
        ("GET", "/api/configuration-manager/configuration"),
        ("GET", "/api/audio-device-manager/input_devices"),
        ("GET", "/api/gpu-device-manager/devices"),
        ("GET", "/api/voice-changer-manager/information"),
        ("GET", "/api/local-voice-changer-interface/information"),
    ):
        response = client.request(method, path)
        assert response.status_code == 404, (method, path, response.text)
        body = response.json()
        assert body["code"] == "not_found"
        assert "message" in body and "details" in body

    # 撤去済みの非APIレガシールートおよび通常の存在しないパスは通常の 404 を返すこと
    for path in ("/non_api_route", "/output.wav", "/vcclient.log"):
        response_non_api = client.get(path)
        assert response_non_api.status_code == 404, path
        assert response_non_api.json()["detail"] == "Not Found"
