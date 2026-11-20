from pathlib import Path

from starlette.testclient import TestClient

from vcclient.server import vcserver_rest_api


def test_frontend_and_api_are_served_together(tmp_path: Path, monkeypatch):
    (tmp_path / "index.html").write_text("<title>Forge</title>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/app.js").write_text("console.log('forge')", encoding="utf-8")
    monkeypatch.setattr(vcserver_rest_api, "get_frontend_path", lambda: tmp_path)
    app = vcserver_rest_api._create_rest_api()
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


def test_log_responses_are_not_cached(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "vcclient.log"
    log_path.write_text("test log", encoding="utf-8")
    monkeypatch.setattr(vcserver_rest_api, "LOG_FILE", str(log_path))
    app = vcserver_rest_api._create_rest_api()
    client = TestClient(app)

    response = client.get("/vcclient.log")
    assert response.status_code == 200
    assert response.text == "test log"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["cache-control"] == "no-store"

    log_path.unlink()
    missing = client.get("/vcclient.log")
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == "no-store"
