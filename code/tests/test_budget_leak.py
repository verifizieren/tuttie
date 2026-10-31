"""Red team: does the user's private budget reach a hotel? (alex-muster: CHF 160, private)"""

import asyncio
import json

import pytest

from aps import load_signing_key
from assistant import marketplace as desk_module
from assistant.events import EventBus
from assistant.marketplace import MarketDesk
from negotiation.tuttie import MAX_ROUNDS, TuttieNegotiator
from negotiation_helpers import RHEINBLICK, TUTTIE, signed_offer
from sessions import Context
from test_negotiation_edges import ScriptedPool, ScriptedToolbox, counter
from test_negotiation_flow import bargain, stub_llm  # noqa: F401  (autouse stub for the hotel LLM)

BUDGET = 160


class RecordingToolbox(ScriptedToolbox):
    """The scripted trust gate, also keeping every body Tuttie sends to the hotel."""

    def __init__(self, replies):
        super().__init__(replies)
        self.sent = []

    async def verified_post(self, node_id, path, body, kind, label):
        self.sent.append(json.loads(json.dumps(body)))
        return await super().verified_post(node_id, path, body, kind, label)


def run(replies, limit=BUDGET):
    pool = ScriptedPool([])
    pool.toolbox = RecordingToolbox(list(replies))
    negotiator = TuttieNegotiator(pool, TUTTIE, load_signing_key(TUTTIE))
    context = Context().add("max_price_chf", limit, "private")
    outcome = asyncio.run(negotiator.negotiate(RHEINBLICK, signed_offer(), context))  # double, CHF 195
    prices = [b["counter"]["payload"]["price_chf"] for b in pool.toolbox.sent]
    return outcome, prices


def test_first_counter_is_not_the_private_budget():
    _, prices = run([counter(189, round_=1), counter(187, round_=2), counter(186, final=True, round_=3)])
    assert prices[0] != BUDGET, f"Tuttie's signed opening counter is the private budget: {prices}"


def test_hotel_cannot_read_the_budget_off_the_counters():
    """A hotel that just holds its price sees Tuttie's counters stop at one number: the budget."""
    _, prices = run([counter(189, round_=n) for n in range(1, MAX_ROUNDS + 1)])
    assert BUDGET not in prices, f"signed counters sent to the hotel: {prices}"


def test_real_rheinblick_rules_never_see_the_budget_as_a_counter():
    """Real hotel app and rules (Rheinblick, double + dog CHF 195), user budget 160."""
    moves = bargain(RHEINBLICK, ("dog",), budget=BUDGET)
    assert BUDGET not in [own for own, _, _ in moves], f"(Tuttie, hotel answer, hotel price): {moves}"


def test_the_budget_in_a_requirement_is_not_posted(monkeypatch):
    """Nothing in code stops the LLM from writing the budget into requirements, which go to every
    woken hotel and into the subagents' negotiation context."""
    posted = []

    async def fake_post(http, url, envelope):
        posted.append(envelope["payload"])
        return {"invited": {}, "skipped": []}

    async def no_offers(self, request_id, expected, invited):
        return []

    monkeypatch.setattr(desk_module, "post_request", fake_post)
    monkeypatch.setattr(MarketDesk, "collect", no_offers)
    desk = MarketDesk(None, "http://localhost:4000", EventBus(), {})
    asyncio.run(desk.find("2026-11-14", requirements=["dog", "max CHF 160 per night"], budget_chf=BUDGET))
    assert "160" not in json.dumps(posted), f"posted to the market: {posted[0]['constraints']}"


def test_a_question_naming_the_private_budget_is_not_sent():
    """ask_agent is free text to a business: the budget (CHF 160, private in the user's context)
    must not go out in it, whatever the LLM was talked into."""
    from test_tools import make_toolbox

    toolbox, _, _ = make_toolbox()
    reply = asyncio.run(toolbox.ask_agent(RHEINBLICK, "My client pays at most CHF 160, can you do that?"))
    assert "not sent" in reply["error"]


def test_tuttie_s_counters_never_name_the_limit():
    """Offers of CHF 220 and 270 against a private budget of 160: no counter carries 160 in
    any field (before #18 the opening counter was exactly 160)."""
    for price in (220, 270, 195, 175):
        pool = ScriptedPool([])
        pool.toolbox = RecordingToolbox([counter(price - 2, round_=n) for n in range(1, MAX_ROUNDS + 1)])
        negotiator = TuttieNegotiator(pool, TUTTIE, load_signing_key(TUTTIE))
        context = Context().add("max_price_chf", BUDGET, "private")
        offer = signed_offer()
        offer["payload"]["price_chf"] = price  # the scripted gate does not re-check the hotel's signature
        asyncio.run(negotiator.negotiate(RHEINBLICK, offer, context))
        sent = json.dumps(pool.toolbox.sent)
        assert all(str(BUDGET) not in json.dumps(b["counter"]["payload"]) for b in pool.toolbox.sent), sent
