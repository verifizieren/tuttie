"""Red team round 7: POST /reset ("start over") clears the toolbox's signed facts and the timeline,
but not the MarketDesk: the old posting's offers stay in last_offers / last_request, so the next
turn's notes still carry "Current verified deal data" of the old search (instead of "No offers or
agreements yet") and negotiate (first_tool) bargains on the old request.

Run from <worktree>/code:
  PYTHONPATH=.:tests .venv/bin/pytest -q -p no:cacheprovider --rootdir=. -c pytest.ini \
      /home/baselhack/overnight/agents/atk7-race-tests/test_atk7_reset_market.py
"""

import asyncio

import httpx

from assistant.conversations import Conversation


class NoLLM:
    """Never called: the test runs no turn."""

    async def complete(self, *args, **kwargs):
        raise AssertionError("no LLM in this test")


def test_reset_forgets_the_old_postings_offers():
    async def scenario():
        conv = Conversation(httpx.AsyncClient(), "http://registry.invalid", NoLLM())
        market = conv.assistant.toolbox.market
        market.last_request = {"request_id": "rq-old", "constraints": {"date": "2026-11-14", "requirements": []}}
        market.last_offers = [{"node_id": "ch.basel.hotel-rheinblick", "name": "Hotel Rheinblick",
                               "offer": {"offer_id": "of-rheinblick-abc123", "price_chf": 128}}]
        market.last_shortlist = list(market.last_offers)
        conv.reset()
        return market

    market = asyncio.run(scenario())
    assert not market.last_offers and market.last_request is None, (market.last_request, market.last_offers)
