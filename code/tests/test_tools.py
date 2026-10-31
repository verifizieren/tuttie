"""Tests for the assistant's trust gate, against the demo registry with mocked HTTP."""

import asyncio
import json
from pathlib import Path

import httpx

from aps import load_signing_key, sign_envelope
from assistant.events import EventBus
from assistant.tools import Toolbox

REGISTRY = json.loads((Path(__file__).resolve().parent.parent / "data" / "registry.json").read_text())
RHEINBLICK = "ch.basel.hotel-rheinblick"
SCAM = "ch.basel.cheap-hotels"


def make_toolbox(tamper: bool = False) -> tuple[Toolbox, EventBus, list[str]]:
    """Toolbox whose registry and nodes are served by a mock transport. Returns contacted URLs too."""
    contacted = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        path = request.url.path
        if path == "/search":
            return httpx.Response(200, json=REGISTRY)
        if path.startswith("/nodes/"):
            record = next((r for r in REGISTRY if r["node_id"] == path.removeprefix("/nodes/")), None)
            return httpx.Response(200, json=record) if record else httpx.Response(404)
        node = next(r for r in REGISTRY if r["endpoint"].endswith(f":{request.url.port}"))
        envelope = sign_envelope(node["node_id"], {"rooms": [{"room_type": "double", "price_chf": 180, "rate": "x"}]},
                                 load_signing_key(node["node_id"]))
        if tamper:
            envelope["payload"]["rooms"][0]["price_chf"] = 1
        return httpx.Response(200, json=envelope)

    bus = EventBus()
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return Toolbox(http, "http://registry", bus), bus, contacted


def test_search_rejects_scam_and_keeps_verified_nodes():
    toolbox, bus, _ = make_toolbox()
    found = asyncio.run(toolbox.search_registry(["hotel"]))
    assert [r["node_id"] for r in found["rejected"]] == [SCAM]
    assert {r["node_id"]: r["trust_tier"] for r in found["verified"]}[RHEINBLICK] == "gold"
    assert {e["node_id"]: e["status"] for e in bus.history}[SCAM] == "broken"


def test_call_tool_returns_verified_payload():
    toolbox, bus, _ = make_toolbox()
    result = asyncio.run(toolbox.call_tool(RHEINBLICK, "get_availability", {"date": "2026-11-14"}))
    assert result["data"]["rooms"][0]["price_chf"] == 180
    assert bus.history[-1]["status"] == "verified"


def test_call_tool_never_contacts_broken_node():
    toolbox, bus, contacted = make_toolbox()
    result = asyncio.run(toolbox.call_tool(SCAM, "get_availability", {}))
    assert result["rejected"] is True
    assert not any(":4003" in url for url in contacted)
    assert bus.history[-1]["status"] == "broken"


def test_call_tool_drops_tampered_response():
    toolbox, bus, _ = make_toolbox(tamper=True)
    result = asyncio.run(toolbox.call_tool(RHEINBLICK, "get_availability", {}))
    assert result["rejected"] is True and "data" not in result
    assert bus.history[-1]["status"] == "broken"


def test_call_tool_refuses_unknown_tools_and_node_ids():
    toolbox, _, contacted = make_toolbox()
    assert "error" in asyncio.run(toolbox.call_tool(RHEINBLICK, "book", {}))
    assert asyncio.run(toolbox.call_tool("../admin", "get_policies", {}))["rejected"] is True
    assert contacted == []
