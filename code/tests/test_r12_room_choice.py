"""hunt12: the card-room binding in Toolbox.book (assistant/tools.py ~811) is a hard refusal with
no way out. A user who explicitly asks for another room of the carded hotel ("book the flexible
one instead", "a single room please") can never get it without a negotiated agreement, and a
hotel whose card room is no longer available becomes unbookable."""

import asyncio

import tests.test_tools as tt
from tests.test_tools import RHEINBLICK, make_toolbox

ROOMS = {"date": "2026-11-14", "rooms": [
    {"room_type": "double", "price_chf": 180, "rate": "best rate, non-refundable"},
    {"room_type": "double-flex", "price_chf": 205, "rate": "flexible"}]}
CARD = [{"node_id": RHEINBLICK, "name": "Hotel Rheinblick", "trust_tier": "gold",
         "offer": {"offer_id": "of-rb", "item": "double room 2026-11-14", "room_type": "double",
                   "price_chf": 195, "includes": []}}]


def book_and_decide(toolbox, room_type):
    """Book `room_type`, approve whatever approval appears, return (approval amounts, result)."""
    async def flow():
        await toolbox.call_tool(RHEINBLICK, "get_availability", {"date": "2026-11-14"})
        task = asyncio.create_task(toolbox.book(RHEINBLICK, "2026-11-14", room_type, "Alex Muster"))
        await asyncio.sleep(0.1)
        made = [a["amount_chf"] for a in toolbox.approvals.pending.values()]
        for a in list(toolbox.approvals.pending):
            toolbox.approvals.decide(a, "declined")
        return made, await task
    return asyncio.run(flow())


def test_user_who_explicitly_asks_for_the_flexible_room_can_book_it(monkeypatch):
    """User: "book the flexible one instead" (free cancellation). The phone would show CHF 205
    and the user approves there, but book() refuses before any approval, on every retry."""
    monkeypatch.setitem(tt.NODE_REPLIES, "get_availability", ROOMS)
    toolbox, _, _ = make_toolbox()
    toolbox.market.last_offers = CARD
    made, result = book_and_decide(toolbox, "double-flex")
    if not made:  # one nudge back to the card's room (round 17); asked again, it books
        assert "unless the user asked" in result.get("error", "")
        made, result = book_and_decide(toolbox, "double-flex")
    assert made == [205], f"no approval for the room the user asked for: {result}"


def test_hotel_whose_card_room_sold_out_is_still_bookable(monkeypatch):
    """The card's double is gone (owner closed it / booked), only double-flex is left: the
    double is refused by availability and double-flex by the card binding: a dead end."""
    monkeypatch.setitem(tt.NODE_REPLIES, "get_availability",
                        {"date": "2026-11-14", "rooms": [ROOMS["rooms"][1]]})
    toolbox, _, _ = make_toolbox()
    toolbox.market.last_offers = CARD
    made_double, r1 = book_and_decide(toolbox, "double")
    made_flex, r2 = book_and_decide(toolbox, "double-flex")
    assert made_double or made_flex, f"no room bookable at all: {r1['error']!r} / {r2['error']!r}"
