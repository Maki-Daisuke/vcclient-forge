from pathlib import Path

from starlette.testclient import TestClient

from vcclient.server.vcserver_rest_api import RestAPI


def test_ui_switcher_assets_and_integration():
    """Verify that ui_switcher.js is integrated into both UI versions."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    ui_switcher_path = repo_root / "web_front" / "ui" / "ui_switcher.js"
    assert ui_switcher_path.exists(), "web_front/ui/ui_switcher.js must exist"

    content = ui_switcher_path.read_text(encoding="utf-8")
    assert "vcclient-ui-switcher" in content
    assert "/ui/2.1.4/" in content
    assert "/ui/2.0.78/" in content
    assert "Modern (v2.1.4)" in content
    assert "Classic (v2.0.78)" in content

    # Check 2.0.78 integration
    html_2078 = (repo_root / "web_front" / "ui" / "2.0.78" / "index.html").read_text(encoding="utf-8")
    assert "ui_switcher.js" in html_2078, "2.0.78 index.html must include ui_switcher.js"

    # Check 2.1.4 integration
    html_214 = (repo_root / "web_front" / "ui" / "2.1.4" / "index.html").read_text(encoding="utf-8")
    assert "ui_switcher.js" in html_214, "2.1.4 index.html must include ui_switcher.js"


def test_root_redirect_preserves_query_parameters():
    """Verify that root redirect preserves query parameters such as app_mode."""
    client = TestClient(RestAPI.get_instance(), follow_redirects=False)

    res_root = client.get("/")
    assert res_root.status_code == 307
    assert res_root.headers.get("location") == "/ui/2.1.4/"

    res_query = client.get("/?app_mode=LogViewer")
    assert res_query.status_code == 307
    assert res_query.headers.get("location") == "/ui/2.1.4/?app_mode=LogViewer"
