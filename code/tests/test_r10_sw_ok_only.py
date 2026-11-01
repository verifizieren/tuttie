"""Round 10: the wallet's service worker caches only successful answers (a 502 while the service
restarts must never replace the offline copy)."""

from pathlib import Path

SW = Path(__file__).resolve().parent.parent / "apps" / "wallet" / "public" / "sw.js"


def test_the_service_worker_caches_only_ok_responses():
    assert "response.ok" in SW.read_text()
