"""r11: one slow or failing piece of the market flow must not sink the whole hotel search.

Real registry, market and hotel nodes in process; only the hotel LLM is a stub. Timeouts are
scaled down with the production ratio kept: Tuttie's HTTP client (assistant/app.py lifespan,
timeout=20) and the market's per-hotel wake timeout (marketplace/market.py INVOKE_TIMEOUT_S=20)
are equal in production, so here both are T.
"""

import asyncio

import httpx
import pytest

import marketplace.market
import node.agent
from r11_world import Router, world

T = 0.5  # production: 20 s for both


class StubLLM:
    """Every hotel is interested and offers a double room; `slow` hotels think for a long time."""

    slow: tuple = ()
    junk_add_on: tuple = ()

    async def complete_json(self, system: str, user: str) -> dict:
        if any(name in system for name in self.slow):
            await asyncio.sleep(3)  # e.g. an Anthropic 429 with retry-after, or a hung provider (40 s x 2)
        add_ons = ["minibar"] if any(name in system for name in self.junk_add_on) else []
        if "decided to make an offer" in system:
            return {"room_type": "double", "add_ons": add_ons}
        return {"interested": True, "reason": "We have a room.", "next_tool": "make_offer",
                "room_type": "double", "add_ons": add_ons}


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    StubLLM.slow, StubLLM.junk_add_on = (), ()
    monkeypatch.setattr(node.agent, "LLM", StubLLM)
    monkeypatch.setattr(marketplace.market, "INVOKE_TIMEOUT_S", T)


def search(fault=None, offer_wait_s: float = 3):
    async def scenario():
        router = Router()
        if fault:
            router.fault = fault
        async with httpx.AsyncClient(transport=router, timeout=T) as http:
            toolbox, bus, market, _ = await world(http, router, offer_wait_s)
            loop = asyncio.get_running_loop()
            started = loop.time()
            result = await toolbox.post_request(date="2026-11-14", tags=["basel"], requirements=["quiet"])
            return result, bus, loop.time() - started
    return asyncio.run(scenario())


def test_baseline_without_faults_shows_cards():
    result, _, _ = search()
    assert "error" not in result and len(result["cards"]) >= 3


def test_one_slow_hotel_agent_does_not_sink_the_whole_search():
    """HOLE: Tuttie's POST /postings times out exactly when the market's wait for ONE slow hotel
    does (both 20 s), so one hotel whose LLM is throttled turns the search into
    "the market is still waking the hotels" for the user, although the other hotels answered."""
    StubLLM.slow = ("Alpina",)
    result, _, _ = search()
    assert "error" not in result, result
    assert {c["name"] for c in result["cards"]} >= {"Gästehaus am Rhein", "Hotel Rheinblick"}


def test_one_transient_market_poll_error_keeps_the_offers_collected_so_far():
    """HOLE: MarketDesk.poll lets any error of one GET /postings/{id} escape: every offer already
    collected is lost and post_request fails ("node unreachable"), after the hotels were woken."""
    failed = []

    def fault(request):
        if request.method == "GET" and "/postings/" in request.url.path and len(failed) < 1:
            failed.append(1)
            return httpx.ReadTimeout("market hiccup", request=request)
        return None
    result, _, _ = search(fault)
    assert "error" not in result, result
    assert len(result["cards"]) >= 3


def test_a_hotel_that_said_interested_but_sends_no_offer_does_not_hold_the_search_for_the_full_wait():
    """HOLE (latency): a hotel LLM that names an add-on id the hotel does not have makes
    make_offer return None (node/agent.py), but the hotel already told the market it will offer,
    so Tuttie waits the full OFFER_WAIT_S (45 s live) before showing anyone's cards."""
    StubLLM.junk_add_on = ("Alpina",)
    result, _, took = search(offer_wait_s=3)
    assert "error" not in result and len(result["cards"]) >= 2
    assert took < 2.5, f"search waited {took:.1f}s for an offer that never comes"


def test_a_registry_blip_during_one_hotels_negotiation_keeps_the_other_hotels_cards():
    """HOLE: Toolbox.verified() calls lookup() (GET registry /nodes/{id}) outside its try, and
    negotiate_all is a bare asyncio.gather: one failed lookup for ONE hotel mid-bargaining raises
    out of negotiate and post_request, so no cards at all although every offer was collected."""
    state = {"bus": None, "failed": False}

    def fault(request):
        bus = state["bus"]
        shortlisted = bus is not None and any(e["detail"].get("phase") == "shortlist" for e in bus.history)
        if (shortlisted and not state["failed"] and request.url.port == 4000
                and request.url.path == "/nodes/ch.basel.hotel-rheinblick"):
            state["failed"] = True
            return httpx.ConnectError("registry restarting", request=request)
        return None

    async def scenario():
        router = Router()
        router.fault = fault
        async with httpx.AsyncClient(transport=router, timeout=T) as http:
            toolbox, bus, _, _ = await world(http, router)
            state["bus"] = bus
            return await toolbox.post_request(date="2026-11-14", tags=["basel"], requirements=["quiet"])
    result = asyncio.run(scenario())
    assert state["failed"]
    assert "Gästehaus am Rhein" in {c["name"] for c in result["cards"]}


def test_negotiate_all_turns_one_hotels_error_into_a_refused_outcome():
    """negotiate_all isolates each hotel: an unexpected error is that hotel's refusal only."""
    from negotiation.tuttie import Outcome, TuttieNegotiator

    class Negotiator(TuttieNegotiator):
        async def negotiate(self, node_id, envelope, context):
            if node_id == "bad":
                raise httpx.ConnectError("registry restarting")
            return Outcome(node_id, "of-good", "agreed", 135, price_chf=128)

    offers = [{"node_id": "bad", "envelope": {"payload": {"offer_id": "of-bad", "price_chf": 150}}},
              {"node_id": "good", "envelope": {"payload": {"offer_id": "of-good", "price_chf": 135}}}]
    bad, good = asyncio.run(Negotiator(None, "tuttie", None).negotiate_all(offers, None))
    assert (bad.status, bad.offer_id, bad.offer_price_chf) == ("refused", "of-bad", 150)
    assert good.status == "agreed"
