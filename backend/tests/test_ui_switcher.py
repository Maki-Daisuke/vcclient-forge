from pathlib import Path

import socketio
from starlette.testclient import TestClient

from vcclient.server import vcserver_rest_api, vcserver_socketio
from vcclient.server.vcserver_socketio import create_socketio_app


def test_frontend_and_api_are_served_together(tmp_path: Path, monkeypatch):
    (tmp_path / "index.html").write_text("<title>Forge</title>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/app.js").write_text("console.log('forge')", encoding="utf-8")
    monkeypatch.setattr(vcserver_rest_api, "get_frontend_path", lambda: tmp_path)
    app = create_socketio_app(socketio.AsyncServer(async_mode="asgi"), vcserver_rest_api._create_rest_api())
    client = TestClient(app, follow_redirects=False)

    for url in ("/", "/?view=log", "/index.html"):
        response = client.get(url)
        assert response.status_code == 200
        assert "<title>Forge</title>" in response.text
        assert response.headers["cache-control"] == "no-store"
        assert client.head(url).headers["cache-control"] == "no-store"
    response = client.get("/assets/app.js")
    assert response.text == "console.log('forge')"
    assert response.headers["cache-control"] == "no-store"
    assert client.head("/assets/app.js").headers["cache-control"] == "no-store"
    for method in (client.get, client.post):
        response = method("/api/does-not-exist")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
        assert response.headers["cache-control"] == "no-store"


def test_socketio_and_log_responses_are_not_cached(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "vcclient.log"
    log_path.write_text("test log", encoding="utf-8")
    monkeypatch.setattr(vcserver_socketio, "LOG_FILE", str(log_path))
    app = create_socketio_app(socketio.AsyncServer(async_mode="asgi"))
    client = TestClient(app)

    for url in ("/vcclient.log", "/socket.io/?EIO=4&transport=polling"):
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
