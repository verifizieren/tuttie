"""Tests for the assistant's trust gate, against the demo registry with mocked HTTP."""

import asyncio
import json
from pathlib import Path

import httpx

from aps import load_signing_key, sign_envelope
from assistant.approvals import ApprovalBook
from assistant.events import EventBus
from assistant.tools import Toolbox

REGISTRY = json.loads((Path(__file__).resolve().parent.parent / "data" / "registry.json").read_text())
RHEINBLICK = "ch.basel.hotel-rheinblick"
SCAM = "ch.basel.cheap-hotels"
NODE_REPLIES = {
    "/tools/get_availability": {"date": "2026-11-14", "rooms": [{"room_type": "double", "price_chf": 180, "rate": "x"}]},
    "/agent": {"answer": "Fine.", "commitment": {"item": "late check-in with dog", "price_chf": 15,
                                                 "conditions": [], "valid_until": "2026-11-15T00:00:00Z"}},
    "/tools/book": {"status": "confirmed", "booking_id": "BK-1", "total_chf": 195},
}


def make_toolbox(tamper: bool = False, timestamp: str | None = None) -> tuple[Toolbox, EventBus, list[str]]:
    """Toolbox whose registry and nodes are served by a mock transport. Returns contacted URLs too.

    `timestamp` makes the nodes sign their replies with that (e.g. an old) timestamp.
    """
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
        payload = NODE_REPLIES.get(path, NODE_REPLIES["/tools/get_availability"])
        envelope = sign_envelope(node["node_id"], json.loads(json.dumps(payload)), load_signing_key(node["node_id"]),
                                 timestamp=timestamp)
        if tamper:
            envelope["payload"]["rooms"][0]["price_chf"] = 1
        return httpx.Response(200, json=envelope)

    bus = EventBus()
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return Toolbox(http, "http://registry", bus, ApprovalBook()), bus, contacted


def test_search_rejects_scam_and_keeps_verified_nodes():
    toolbox, bus, _ = make_toolbox()
    found = asyncio.run(toolbox.search_registry(["hotel"]))
    assert [r["node_id"] for r in found["rejected"]] == [SCAM]
    assert {r["node_id"]: r["trust_tier"] for r in found["verified"]}[RHEINBLICK] == "gold"
    assert {e["node_id"]: e["status"] for e in bus.history}[SCAM] == "broken"


def test_search_shows_uid_only_when_the_register_vouched_for_it():
    toolbox, _, _ = make_toolbox()
    found = asyncio.run(toolbox.search_registry(["hotel"]))
    uids = {r["node_id"]: r["uid"] for r in found["verified"]}
    assert uids[RHEINBLICK] == "CHE-526.018.151"
    assert uids["ch.basel.hotel-spalenhof"] is None  # blue seal only: its UID is just a claim


def test_call_tool_drops_outdated_signed_reply():
    """A genuine but old reply (a replay) is dropped like a forged one."""
    toolbox, bus, _ = make_toolbox(timestamp="2026-01-01T00:00:00Z")
    result = asyncio.run(toolbox.call_tool(RHEINBLICK, "get_availability", {"date": "2026-11-14"}))
    assert result["rejected"] is True and "outdated" in result["reason"]
    assert bus.history[-1]["status"] == "broken"


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


def test_book_waits_for_approval_and_sends_signed_decision_and_commitment():
    toolbox, bus, _ = make_toolbox()
    sent = {}
    original_post = toolbox.http.post

    async def spy_post(url, json=None):
        sent[url.rsplit("/", 1)[-1]] = json
        return await original_post(url, json=json)

    toolbox.http.post = spy_post

    async def flow():
        await toolbox.call_tool(RHEINBLICK, "get_availability", {"date": "2026-11-14"})
        await toolbox.ask_agent(RHEINBLICK, "Late arrival with a dog?")
        booking = asyncio.create_task(
            toolbox.book(RHEINBLICK, "2026-11-14", "double", "Alex Muster", ["late check-in with dog"]))
        await asyncio.sleep(0.05)
        [approval] = toolbox.approvals.pending.values()
        assert approval["amount_chf"] == 195
        toolbox.approvals.decide(approval["id"], "approved")
        return await booking

    result = asyncio.run(flow())
    assert result["status"] == "confirmed"
    assert sent["book"]["approval"]["decision"] == "approved"
    assert sent["book"]["extras"][0]["payload"]["commitment"]["price_chf"] == 15
    assert [e["status"] for e in bus.history if e["kind"] == "approval"] == ["pending", "approved"]


def test_book_declined_never_calls_the_node():
    toolbox, bus, contacted = make_toolbox()

    async def flow():
        await toolbox.call_tool(RHEINBLICK, "get_availability", {"date": "2026-11-14"})
        booking = asyncio.create_task(toolbox.book(RHEINBLICK, "2026-11-14", "double", "Alex Muster"))
        await asyncio.sleep(0.05)
        toolbox.approvals.decide(next(iter(toolbox.approvals.pending)), "declined")
        return await booking

    assert asyncio.run(flow())["declined"] is True
    assert not any(url.endswith("/tools/book") for url in contacted)


def test_book_requires_signed_availability_and_known_extras():
    toolbox, _, _ = make_toolbox()
    assert "get_availability" in asyncio.run(toolbox.book(RHEINBLICK, "2026-11-14", "double", "A"))["error"]
    asyncio.run(toolbox.call_tool(RHEINBLICK, "get_availability", {"date": "2026-11-14"}))
    assert "unknown extras" in asyncio.run(toolbox.book(RHEINBLICK, "2026-11-14", "double", "A", ["free spa"]))["error"]


def test_book_refuses_untrusted_unsigned_node():
    toolbox, _, contacted = make_toolbox()
    asyncio.run(toolbox.call_tool("ch.basel.budget-rooms", "get_availability", {"date": "2026-11-14"}))
    result = asyncio.run(toolbox.book("ch.basel.budget-rooms", "2026-11-14", "double", "A"))
    assert result["rejected"] is True and not toolbox.approvals.pending
    assert not any(url.endswith("/tools/book") for url in contacted)
