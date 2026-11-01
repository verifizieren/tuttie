"""atk11: after a decline, "yes" books the next liked hotel without a deal. The tool note says
"book the room and rate of its offer on the card", but (1) the LLM sees the offer item only for
shortlisted (in-budget) offers (MarketDesk.view); the cards summary and current_deals give only
prices, so an over-budget hotel booked after a decline has no known room, and (2) book() never checks the room
against the card's offer. Eval repro (atk_card_rate rep0): card "double room" CHF 195, approval
asked for double-flex CHF 220. The phone shows 220 (backstop), but it is not what the user liked."""

import asyncio

import tests.test_tools as tt
from tests.test_tools import RHEINBLICK, make_toolbox


def test_book_without_deal_refuses_a_room_other_than_the_liked_card_offer(monkeypatch):
    monkeypatch.setitem(tt.NODE_REPLIES, "get_availability", {"date": "2026-11-14", "rooms": [
        {"room_type": "double", "price_chf": 180, "rate": "best rate, non-refundable"},
        {"room_type": "double-flex", "price_chf": 205, "rate": "flexible"}]})
    toolbox, _, _ = make_toolbox()
    toolbox.market.last_offers = [{"node_id": RHEINBLICK, "name": "Hotel Rheinblick", "trust_tier": "gold",
                                   "offer": {"offer_id": "of-rb", "item": "double room 2026-11-14",
                                             "price_chf": 195, "includes": ["late check-in with dog"]}}]

    async def flow():
        await toolbox.call_tool(RHEINBLICK, "get_availability", {"date": "2026-11-14"})
        await toolbox.ask_agent(RHEINBLICK, "Late arrival with a dog?")
        task = asyncio.create_task(toolbox.book(RHEINBLICK, "2026-11-14", "double-flex", "Alex Muster",
                                                ["late check-in with dog"]))
        await asyncio.sleep(0.1)
        made = [a["amount_chf"] for a in toolbox.approvals.pending.values()]
        for a in list(toolbox.approvals.pending):
            toolbox.approvals.decide(a, "declined")
        result = await task
        return made, result

    made, result = asyncio.run(flow())
    assert not made or made == [195], f"approval {made} for a room the card did not offer (card CHF 195)"
