"""Tests for the assistant's trust gate, against the demo registry with mocked HTTP."""

import asyncio
import json
from pathlib import Path

import httpx

from aps import load_signing_key, sign_envelope
from aps.call import verify_call
from aps.keys import load_public_key
from assistant.approvals import ApprovalBook
from assistant.events import EventBus
from assistant.tools import Toolbox

REGISTRY = json.loads((Path(__file__).resolve().parent.parent / "data" / "registry.json").read_text())
RHEINBLICK = "ch.basel.hotel-rheinblick"
SCAM = "ch.basel.cheap-hotels"
NODE_REPLIES = {  # by MCP tool name or agent path
    "get_availability": {"date": "2026-11-14", "rooms": [{"room_type": "double", "price_chf": 180, "rate": "x"}]},
    "/agent": {"answer": "Fine.", "commitment": {"item": "late check-in with dog", "price_chf": 15,
                                                 "conditions": [], "valid_until": "2026-11-15T00:00:00Z"}},
    "book": {"status": "confirmed", "booking_id": "BK-1", "total_chf": 195, "room_type": "double",
             "date": "2026-11-14", "rate": "x", "offer_id": None, "extras": ["late check-in with dog"]},
    "get_policies": {"tool": "get_policies", "charges": [{"purpose": "city tax", "price_chf": 4}]},
    "pay": {"tool": "pay", "status": "paid", "amount_chf": 4, "checked": ["caller", "signature", "delegation", "mandate"]},
}


def make_toolbox(tamper: bool = False, timestamp: str | None = None) -> tuple[Toolbox, EventBus, list[str]]:
    """Toolbox whose registry and nodes are served by a mock transport. Returns contacted URLs too.

    `timestamp` makes the nodes sign their replies with that (e.g. an old) timestamp.
    """
    contacted = []

    def signed_reply(node: dict, payload: dict) -> dict:
        envelope = sign_envelope(node["node_id"], json.loads(json.dumps(payload)), load_signing_key(node["node_id"]),
                                 timestamp=timestamp)
        if tamper:
            envelope["payload"]["rooms"][0]["price_chf"] = 1
        return envelope

    class FakeMcp:
        """Stands in for McpLink: answers each tool with the node's signed reply."""

        def __init__(self):
            self.sent = {}  # tool -> the arguments Tuttie sent

        async def call(self, endpoint: str, tool: str, args: dict) -> dict:
            contacted.append(f"{endpoint}/mcp/{tool}")
            self.sent[tool] = args
            return signed_reply(next(r for r in REGISTRY if r["endpoint"] == endpoint), NODE_REPLIES[tool])

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        path = request.url.path
        if path == "/search":
            return httpx.Response(200, json=REGISTRY)
        if path.startswith("/nodes/"):
            record = next((r for r in REGISTRY if r["node_id"] == path.removeprefix("/nodes/")), None)
            return httpx.Response(200, json=record) if record else httpx.Response(404)
        node = next(r for r in REGISTRY if r["endpoint"].endswith(f":{request.url.port}"))
        return httpx.Response(200, json=signed_reply(node, NODE_REPLIES.get(path, NODE_REPLIES["get_availability"])))

    bus = EventBus()
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return Toolbox(http, "http://registry", bus, ApprovalBook(), mcp=FakeMcp()), bus, contacted


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
    call = toolbox.mcp.sent["book"]["call"]  # book goes out as a call signed by Tuttie
    assert verify_call(call, load_public_key("ch.tuttie.alex-muster"), tool="book")
    assert call["delegation"]["agent_id"] == "ch.tuttie.alex-muster"
    assert call["args"]["approval"]["decision"] == "approved"
    assert call["args"]["extras"][0]["payload"]["commitment"]["price_chf"] == 15
    assert [e["status"] for e in bus.history if e["kind"] == "approval"] == ["pending", "approved"]
    # The user signed the room, night, rate and extras along with the amount.
    assert call["args"]["approval"]["terms"] == {"room_type": "double", "date": "2026-11-14", "rate": "x",
                                                 "includes": ["late check-in with dog"]}
    assert "mismatch" not in result


def test_a_confirmation_for_other_terms_than_approved_is_flagged():
    from assistant.tools import booked_other_terms
    terms = {"room_type": "double", "date": "2026-11-14", "rate": "best rate, non-refundable", "includes": [],
             "offer_id": "of-1"}
    same = {"total_chf": 172, "room_type": "double", "date": "2026-11-14", "rate": "best rate, non-refundable",
            "offer_id": "of-1"}
    assert booked_other_terms(same, 172, terms) == []
    flexible = {**same, "room_type": "double-flex", "rate": "flexible", "total_chf": 205}
    assert booked_other_terms(flexible, 172, terms) == ["total_chf", "room_type", "rate"]
    from aps.approval import booking_terms
    odd = booking_terms("double", "2026-11-14", {"x": 1}, [])  # a hotel's rate in an odd shape
    assert booked_other_terms({"total_chf": 172, "room_type": "double", "date": "2026-11-14", "rate": {"x": 1}},
                              172, odd) == []


def test_book_declined_never_calls_the_node():
    toolbox, bus, contacted = make_toolbox()

    async def flow():
        await toolbox.call_tool(RHEINBLICK, "get_availability", {"date": "2026-11-14"})
        booking = asyncio.create_task(toolbox.book(RHEINBLICK, "2026-11-14", "double", "Alex Muster"))
        await asyncio.sleep(0.05)
        toolbox.approvals.decide(next(iter(toolbox.approvals.pending)), "declined")
        return await booking

    assert asyncio.run(flow())["declined"] is True
    assert not any(url.endswith("/mcp/book") for url in contacted)


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
    assert not any(url.endswith("/mcp/book") for url in contacted)


def test_identity_shows_tuttie_sealed_and_acting_for_the_user():
    toolbox, bus, _ = make_toolbox()
    me = asyncio.run(toolbox.identity("ch.tuttie.alex-muster"))
    assert me["trust_tier"] == "blue" and me["acts_for_user"] is True
    assert set(me["scopes"]) == {"ask_agents", "book", "negotiate", "post_requests"}
    assert bus.history == []  # identity checks are for the wallet, not the timeline


def test_identity_without_delegation_does_not_act_for_the_user():
    toolbox, _, _ = make_toolbox()
    me = asyncio.run(toolbox.identity(RHEINBLICK))  # a sealed node, but nobody delegated to it
    assert me["acts_for_user"] is False and me["scopes"] == []
    assert asyncio.run(toolbox.identity("ch.nobody.here"))["rejected"] is True


def book_and_decide(allow_mandate: bool) -> tuple[dict, Toolbox, EventBus]:
    """Book Rheinblick; the user approves on the phone, allowing the offered mandate or not."""
    toolbox, bus, _ = make_toolbox()

    async def flow():
        await toolbox.call_tool(RHEINBLICK, "get_availability", {"date": "2026-11-14"})
        booking = asyncio.create_task(toolbox.book(RHEINBLICK, "2026-11-14", "double", "Alex Muster"))
        while not toolbox.approvals.pending:
            await asyncio.sleep(0.01)
        [approval] = toolbox.approvals.pending.values()
        assert approval["offer_mandate"]["purpose"] == "city tax" and approval["offer_mandate"]["max_chf"] == 4
        toolbox.approvals.decide(approval["id"], "approved", allow_mandate=allow_mandate)
        return await booking

    return asyncio.run(flow()), toolbox, bus


def test_an_allowed_mandate_pays_the_city_tax_right_after_booking_without_asking():
    result, toolbox, bus = book_and_decide(allow_mandate=True)
    assert result["charges_paid"][0]["status"] == "paid" and "open_charges" not in result
    call = toolbox.mcp.sent["pay"]["call"]
    assert call["args"]["mandate"]["purpose"] == "city tax" and "approval" not in call["args"]
    assert [e["status"] for e in bus.history if e["kind"] == "approval"] == ["pending", "approved"]  # only the booking
    assert bus.history[-1]["kind"] == "payment" and "with your mandate" in bus.history[-1]["summary"]


def test_without_a_mandate_the_city_tax_stays_open_for_the_phone():
    result, toolbox, _ = book_and_decide(allow_mandate=False)
    assert result["open_charges"] == [{"purpose": "city tax", "price_chf": 4}] and "pay" not in toolbox.mcp.sent
    assert toolbox.approvals.mandates == {}


def test_saying_goodbye_asks_the_wallet_to_close_the_card():
    toolbox, bus, _ = make_toolbox()
    result = asyncio.run(toolbox.dispatch("end_conversation", {}))
    assert result["closing"] is True
    assert bus.history[-1]["kind"] == "close"


def test_current_deals_preserves_signed_total():
    toolbox, _, _ = make_toolbox()
    toolbox.market.last_offers = [{"node_id": RHEINBLICK, "name": "Hotel Rheinblick", "offer": {"price_chf": 220}}]
    toolbox.agreements[RHEINBLICK] = {"payload": {"type": "agreement", "price_chf": 209, "includes": ["dog"]}}
    deal = asyncio.run(toolbox.current_deals())["deals"][0]
    assert deal["offered_chf"] == 220 and deal["agreement"]["price_chf"] == 209
    assert deal["agreement"]["includes"] == ["dog"]


def test_current_deals_carry_the_signed_policies_for_follow_ups():
    toolbox, _, _ = make_toolbox()
    toolbox.market.last_offers = [{"node_id": RHEINBLICK, "name": "Hotel Rheinblick", "offer": {"price_chf": 220}}]
    assert asyncio.run(toolbox.current_deals())["deals"][0]["policies"] is None  # not fetched: no guessing
    asyncio.run(toolbox.load_policies(RHEINBLICK))
    toolbox.policies[RHEINBLICK] |= {"policies": {"check_in": "from 15:00"}, "photos": ["a.jpg"]}
    policies = asyncio.run(toolbox.current_deals())["deals"][0]["policies"]
    assert policies["policies"] == {"check_in": "from 15:00"} and "photos" not in policies


def test_voice_swipe_targets_current_deck():
    toolbox, bus, _ = make_toolbox()
    assert "error" in asyncio.run(toolbox.swipe_card("like"))
    cards = bus.emit("marketplace", "verified", "2 hotels", detail={"phase": "cards", "cards": []})
    assert asyncio.run(toolbox.swipe_card("pass"))["sent"] == "pass"
    assert bus.history[-1]["detail"] == {"action": "swipe", "verdict": "pass", "cards_step": cards["step"]}
    assert "error" in asyncio.run(toolbox.swipe_card("invalid"))
    bus.emit("marketplace", "verified", "New request", detail={"phase": "posted"})
    assert "error" in asyncio.run(toolbox.swipe_card("like"))
