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


def test_unsupported_api_returns_safe_json_404(client):
    import json

    # 削除された merge_models へのアクセス
    response = client.post(
        "/api/slot-manager/slots/operation/merge_models",
        json={"files": [{"slot_index": 0, "strength": 0.5}]},
    )
    assert response.status_code == 404
    data = response.json()
    detail = json.loads(data["detail"])
    assert detail["code"] == "NOT_SUPPORTED"

    # 存在しないエンドポイントへのアクセスでも安全な JSON が返ること（UIクラッシュ防止）
    response_unknown = client.get("/api/unknown_route")
    assert response_unknown.status_code == 404
    data_unknown = response_unknown.json()
    detail_unknown = json.loads(data_unknown["detail"])
    assert detail_unknown["code"] == "NOT_SUPPORTED"

    # /api/ 以外のパス（通常のWebリクエスト）では通常の 404 が返ること
    response_non_api = client.get("/non_api_route")
    assert response_non_api.status_code == 404
    assert response_non_api.json()["detail"] == "Not Found"


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


def test_slot_index_out_of_range_api_validation(client):
    """API経由で範囲外スロット番号（40億番や負の数）を指定された場合に 400 Bad Request を返すこと。"""
    # 4000000000 番スロットの取得
    res_huge = client.get("/api/slot-manager/slots/4000000000")
    assert res_huge.status_code == 400
    assert "out of range" in res_huge.text

    # 負の数スロットの取得
    res_neg = client.get("/api/slot-manager/slots/-1")
    assert res_neg.status_code == 400

    # 範囲外スロットの削除
    res_del = client.delete("/api/slot-manager/slots/999999")
    assert res_del.status_code == 400

    # 範囲外スロットへの移動
    res_move = client.post("/api/slot-manager/slots/operation/move_model", json={"src": 0, "dst": 4000000000})
    assert res_move.status_code == 400
