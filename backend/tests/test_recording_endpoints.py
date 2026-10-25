from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from vcclient.const import (
    SERVER_IO_RECORDING_FILE_IN,
    SERVER_IO_RECORDING_FILE_MONITOR,
    SERVER_IO_RECORDING_FILE_OUT,
)
from vcclient.server.vcserver_rest_api import RestAPI
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager


@pytest.fixture(scope="module")
def client():
    app = RestAPI.get_instance()
    return TestClient(app)


def test_recording_endpoints_return_404_when_files_missing(client):
    # Ensure test files do not exist
    for filename in [SERVER_IO_RECORDING_FILE_OUT, SERVER_IO_RECORDING_FILE_IN, SERVER_IO_RECORDING_FILE_MONITOR]:
        Path(filename).unlink(missing_ok=True)

    res_out = client.get("/output.wav")
    assert res_out.status_code == 404

    res_in = client.get("/input.wav")
    assert res_in.status_code == 404

    res_mon = client.get("/monitor.wav")
    assert res_mon.status_code == 404


def test_recording_endpoints_serve_wav_files_when_present(client):
    dummy_wav = b"RIFF....WAVEfmt ...."

    try:
        Path(SERVER_IO_RECORDING_FILE_OUT).write_bytes(dummy_wav)
        Path(SERVER_IO_RECORDING_FILE_IN).write_bytes(dummy_wav)
        Path(SERVER_IO_RECORDING_FILE_MONITOR).write_bytes(dummy_wav)

        # Test root paths
        res_out = client.get("/output.wav")
        assert res_out.status_code == 200
        assert res_out.headers.get("content-type") == "audio/wav"
        assert res_out.content == dummy_wav

        res_in = client.get("/input.wav")
        assert res_in.status_code == 200
        assert res_in.headers.get("content-type") == "audio/wav"
        assert res_in.content == dummy_wav

        res_mon = client.get("/monitor.wav")
        assert res_mon.status_code == 200
        assert res_mon.headers.get("content-type") == "audio/wav"
        assert res_mon.content == dummy_wav

        # Test UI relative fallback paths
        res_ui214 = client.get("/ui/2.1.4/output.wav")
        assert res_ui214.status_code == 200
        assert res_ui214.headers.get("content-type") == "audio/wav"
        assert res_ui214.content == dummy_wav

        res_ui2078 = client.get("/ui/2.0.78/output.wav")
        assert res_ui2078.status_code == 200
        assert res_ui2078.headers.get("content-type") == "audio/wav"
        assert res_ui2078.content == dummy_wav

    finally:
        Path(SERVER_IO_RECORDING_FILE_OUT).unlink(missing_ok=True)
        Path(SERVER_IO_RECORDING_FILE_IN).unlink(missing_ok=True)
        Path(SERVER_IO_RECORDING_FILE_MONITOR).unlink(missing_ok=True)


def test_ui_bundles_contain_recording_fallbacks():
    repo_root = Path(__file__).resolve().parent.parent.parent
    ui2078_js = (repo_root / "web_front" / "ui" / "2.0.78" / "index.js").read_text(encoding="utf-8")
    assert "__vc_was_recording" in ui2078_js, "2.0.78 must have server recording fallback"
    assert "/api/voice-changer/operation/start_recording" in ui2078_js

    ui214_js = (repo_root / "web_front" / "ui" / "2.1.4" / "assets" / "index-D8G8J-aW.js").read_text(encoding="utf-8")
    assert 'downloadFile("/output.wav"' in ui214_js, "2.1.4 must use absolute path /output.wav"


def test_operation_start_and_stop_recording_endpoints(client):
    cm = ConfigurationManager.get_instance()

    with patch("vcclient.voice_changer.voice_change_manager.voice_changer.VoiceChanger.get_instance") as mock_vc_get:
        mock_vc = MagicMock()
        mock_vc_get.return_value = mock_vc

        res_start = client.post("/api/voice-changer/operation/start_recording")
        assert res_start.status_code == 200
        mock_vc.start_recording.assert_called_once()
        assert cm.voice_changer_configuration.recording_started is True

        res_stop = client.post("/api/voice-changer/operation/stop_recording")
        assert res_stop.status_code == 200
        mock_vc.stop_recording.assert_called_once()
        assert cm.voice_changer_configuration.recording_started is False
