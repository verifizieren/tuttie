"""Round 17: a booking without a deal for another room than the liked card's gets one nudge back
to the card's room; asked again for that room, it books (the user may want it)."""

import asyncio

import tests.test_tools as tt
from tests.test_tools import RHEINBLICK, make_toolbox


def setup(monkeypatch):
    monkeypatch.setitem(tt.NODE_REPLIES, "get_availability", {"date": "2026-11-14", "rooms": [
        {"room_type": "double", "price_chf": 180, "rate": "best rate, non-refundable"},
        {"room_type": "double-flex", "price_chf": 205, "rate": "flexible"}]})
    toolbox, _, _ = make_toolbox()
    toolbox.market.last_offers = [{"node_id": RHEINBLICK, "name": "Hotel Rheinblick", "trust_tier": "gold",
                                   "offer": {"offer_id": "of-rb", "item": "double room 2026-11-14", "room_type": "double",
                                             "price_chf": 180, "includes": []}}]
    return toolbox


def book(toolbox, room):
    async def flow():
        await toolbox.call_tool(RHEINBLICK, "get_availability", {"date": "2026-11-14"})
        task = asyncio.create_task(toolbox.book(RHEINBLICK, "2026-11-14", room, "Alex Muster", []))
        await asyncio.sleep(0.1)
        made = [a["amount_chf"] for a in toolbox.approvals.pending.values()]
        for a in list(toolbox.approvals.pending):
            toolbox.approvals.decide(a, "declined")
        return made, await task
    return asyncio.run(flow())


def test_another_room_than_the_card_gets_one_nudge_then_books(monkeypatch):
    toolbox = setup(monkeypatch)
    made, result = book(toolbox, "double-flex")
    assert made == [] and "card" in result.get("error", "")
    made, result = book(toolbox, "double-flex")  # asked again: the user wants it
    assert made == [205]


def test_the_card_s_room_books_at_once(monkeypatch):
    made, _ = book(setup(monkeypatch), "double")
    assert made == [180]
