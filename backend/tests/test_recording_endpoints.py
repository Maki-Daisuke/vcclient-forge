import json

import pytest
from starlette.testclient import TestClient

from vcclient.server import vcserver_rest_api
from vcclient.server.vcserver_rest_api import get_rest_api
from vcclient.server.vcserver_socketio import create_socketio_app, create_socketio_server


@pytest.fixture(scope="module")
def client():
    app = get_rest_api()
    return TestClient(app)


def test_output_wav_returns_404_when_file_missing(client, tmp_path, monkeypatch):
    monkeypatch.setattr(vcserver_rest_api, "SERVER_IO_RECORDING_FILE_OUT", str(tmp_path / "output.wav"))
    res_out = client.get("/output.wav")
    assert res_out.status_code == 404


def test_output_wav_serves_file_and_removed_recording_routes_return_404(client, tmp_path, monkeypatch):
    dummy_wav = b"RIFF....WAVEfmt ...."
    output_path = tmp_path / "output.wav"
    output_path.write_bytes(dummy_wav)
    monkeypatch.setattr(vcserver_rest_api, "SERVER_IO_RECORDING_FILE_OUT", str(output_path))

    res_out = client.get("/output.wav")
    assert res_out.status_code == 200
    assert res_out.headers.get("content-type") == "audio/wav"
    assert res_out.content == dummy_wav

    asgi_app = create_socketio_app(create_socketio_server(), get_rest_api())
    asgi_res = TestClient(asgi_app).get("/output.wav")
    assert asgi_res.status_code == 200
    assert asgi_res.headers.get("cache-control") == "no-store"
    assert asgi_res.content == dummy_wav

    for removed_path in [
        "/input.wav",
        "/monitor.wav",
        "/ui/2.1.4/output.wav",
        "/ui/2.0.78/output.wav",
    ]:
        assert client.get(removed_path).status_code == 404


def test_removed_recording_operation_endpoints_return_404(client):
    for endpoint in [
        "/api/voice-changer/operation/start_recording",
        "/api/voice-changer/operation/stop_recording",
    ]:
        res = client.post(endpoint)
        assert res.status_code == 404
        assert json.loads(res.json()["detail"])["code"] == "NOT_SUPPORTED"
