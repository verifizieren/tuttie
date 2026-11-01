"""atk10: the wallet's index.html (and sw.js) are served without Cache-Control (nginx only adds
"no-transform", checked with curl -I on the live site), but with Last-Modified. Browsers then
cache them heuristically (10 % of their age), and sw.js's network-first fetch() goes through
that HTTP cache: after a deploy a phone that opened the wallet within that window keeps running
the OLD build (old hashed JS from the HTTP/SW cache) against the new backend.
Expected: index.html and sw.js say Cache-Control: no-cache (or the SW fetches with cache: "no-cache")."""

from pathlib import Path

from fastapi.testclient import TestClient
from starlette.staticfiles import StaticFiles

import assistant.app as assistant_app


def test_wallet_shell_is_revalidated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    (tmp_path / "index.html").write_text("<!doctype html><script src='/wallet/assets/index-abc.js'></script>")
    (tmp_path / "sw.js").write_text("// sw")
    for route in assistant_app.app.routes:
        if getattr(route, "name", "") == "wallet":
            route.app = StaticFiles(directory=tmp_path, html=True)
    with TestClient(assistant_app.app) as client:
        for path in ("/wallet/", "/wallet/sw.js"):
            response = client.get(path)
            assert response.status_code == 200
            assert "last-modified" in response.headers  # heuristic freshness applies...
            assert "no-cache" in response.headers.get("cache-control", ""), path  # ...unless told not to


def test_service_worker_bypasses_http_cache():
    sw = (Path(assistant_app.APPS_DIR) / "wallet" / "public" / "sw.js").read_text()
    assert "no-cache" in sw or "no-store" in sw or "reload" in sw, "fetch(request) uses the HTTP cache"
