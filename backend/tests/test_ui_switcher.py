from pathlib import Path


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

    # Check dist sync
    dist_switcher = repo_root / "frontend" / "dist" / "ui" / "ui_switcher.js"
    assert dist_switcher.exists(), "frontend/dist/ui/ui_switcher.js must be synchronized"

    # Verify redundant Classic UI button is removed from v2.1.4 bundle
    v214_bundle = (repo_root / "web_front" / "ui" / "2.1.4" / "assets" / "index-D8G8J-aW.js").read_text(
        encoding="utf-8"
    )
    assert "Classic UI (v2.0.78)" not in v214_bundle, "Redundant Classic UI button must be removed"
