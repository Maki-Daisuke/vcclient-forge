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


def test_unsupported_api_returns_safe_json_404(client):
    import json

    # 存在しないAPIエンドポイントへのアクセスでも安全な JSON が返ること（UIクラッシュ防止）
    for method in ("GET", "POST"):
        response = client.request(method, "/api/unknown_route")
        assert response.status_code == 404
        detail = json.loads(response.json()["detail"])
        assert detail["code"] == "NOT_SUPPORTED"

    # /api/ 以外のパス（通常のWebリクエスト）では通常の 404 が返ること
    response_non_api = client.get("/non_api_route")
    assert response_non_api.status_code == 404
    assert response_non_api.json()["detail"] == "Not Found"


def test_slot_index_out_of_range_api_validation(client):
    """API経由で範囲外スロット番号（40億番や負の数）を指定された場合に 400 Bad Request を返すこと。"""
    # 4000000000 番スロットの取得
    res_huge = client.get("/api/slot-manager/slots/4000000000")
    assert res_huge.status_code == 400
    assert "out of range" in res_huge.text

    # 負の数スロットの取得
    res_neg = client.get("/api/slot-manager/slots/-1")
    assert res_neg.status_code == 400

    # 範囲外スロットのメタデータ更新（PATCH）とアップロード（POST）
    res_patch = client.patch(
        "/api/slot-manager/slots/4000000000",
        data={"name": "InvalidSlot"},
    )
    assert res_patch.status_code == 400

    res_post = client.post(
        "/api/slot-manager/slots",
        data={"name": "InvalidSlot", "slot_index": "4000000000"},
        files={"model_file": ("model.onnx", b"dummy", "application/octet-stream")},
    )
    assert res_post.status_code == 400

    # 範囲外スロットの削除（DELETE）
    res_delete_huge = client.delete("/api/slot-manager/slots/4000000000")
    assert res_delete_huge.status_code == 400
    res_delete_neg = client.delete("/api/slot-manager/slots/-1")
    assert res_delete_neg.status_code == 400

    # 範囲外スロット（上限境界超過）の取得
    res_overflow = client.get("/api/slot-manager/slots/999999")
    assert res_overflow.status_code == 400
