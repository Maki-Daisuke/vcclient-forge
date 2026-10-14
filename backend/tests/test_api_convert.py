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
