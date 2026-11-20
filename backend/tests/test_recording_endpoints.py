import pytest
from starlette.testclient import TestClient

from vcclient.server import vcserver_rest_api
from vcclient.server.vcserver_rest_api import get_rest_api


@pytest.fixture(scope="module")
def client():
    app = get_rest_api()
    return TestClient(app)


def test_output_wav_returns_404_when_file_missing(client, tmp_path, monkeypatch):
    monkeypatch.setattr(vcserver_rest_api, "SERVER_IO_RECORDING_FILE_OUT", str(tmp_path / "output.wav"))
    res_out = client.get("/output.wav")
    assert res_out.status_code == 404


def test_output_wav_serves_file_with_no_store_cache_header(client, tmp_path, monkeypatch):
    dummy_wav = b"RIFF....WAVEfmt ...."
    output_path = tmp_path / "output.wav"
    output_path.write_bytes(dummy_wav)
    monkeypatch.setattr(vcserver_rest_api, "SERVER_IO_RECORDING_FILE_OUT", str(output_path))

    res_out = client.get("/output.wav")
    assert res_out.status_code == 200
    assert res_out.headers.get("content-type") == "audio/wav"
    assert res_out.headers.get("cache-control") == "no-store"
    assert res_out.content == dummy_wav
