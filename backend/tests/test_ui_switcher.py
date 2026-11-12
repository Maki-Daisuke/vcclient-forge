from pathlib import Path

import socketio
from starlette.testclient import TestClient

from vcclient.server import vcserver_rest_api
from vcclient.server.vcserver_socketio import create_socketio_app


def test_frontend_and_api_are_served_together(tmp_path: Path, monkeypatch):
    (tmp_path / "index.html").write_text("<title>Forge</title>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/app.js").write_text("console.log('forge')", encoding="utf-8")
    monkeypatch.setattr(vcserver_rest_api, "get_frontend_path", lambda: tmp_path)
    app = create_socketio_app(socketio.AsyncServer(async_mode="asgi"), vcserver_rest_api._create_rest_api())
    client = TestClient(app, follow_redirects=False)

    for url in ("/", "/?view=log"):
        response = client.get(url)
        assert response.status_code == 200
        assert "<title>Forge</title>" in response.text
    assert client.get("/assets/app.js").text == "console.log('forge')"
    for method in (client.get, client.post):
        response = method("/api/does-not-exist")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
