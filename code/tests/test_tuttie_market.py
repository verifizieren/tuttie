"""Tuttie on the marketplace: post a request, collect signed offers, build its own shortlist.

Runs the real registry, market and company agents in process; only the LLM is a stub.
"""

import asyncio
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

import node.agent
from aps.keys import load_public_key
from assistant.events import EventBus
from assistant.marketplace import MarketDesk, shortlist
from assistant.tools import load_authorities
from marketplace.app import create_app as create_market_app
from marketplace.market import Market
from node.server import create_app
from registry.app import app as registry_app

DATA = Path(__file__).resolve().parent.parent / "data"


class StubLLM:
    """Every woken agent is interested and offers a double room with no add-ons."""

    async def complete_json(self, system: str, user: str) -> dict:
        if "decided to make an offer" in system:
            return {"room_type": "double", "add_ons": []}
        return {"interested": True, "reason": "We have a room.", "next_tool": "make_offer"}


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    monkeypatch.setattr(node.agent, "LLM", StubLLM)


def run_find(**kwargs) -> tuple[dict, EventBus, Market]:
    async def scenario():
        transports = {}

        class Router(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                return await transports[request.url.port].handle_async_request(request)

        async with httpx.AsyncClient(transport=Router()) as http:
            apps = {4000: registry_app}
            for path in (DATA / "nodes").glob("*.json"):
                config = json.loads(path.read_text())
                apps[config["port"]] = create_app(config, http=http)
            market_app = create_market_app(http)
            market = Market(http, "http://localhost:4000", load_authorities(), load_public_key("user"),
                            "http://localhost:4010")
            market_app.state.market = market
            apps[4010] = market_app
            transports.update({port: httpx.ASGITransport(app=app) for port, app in apps.items()})
            bus = EventBus()
            desk = MarketDesk(http, "http://localhost:4000", bus, load_authorities(),
                              market_url="http://localhost:4010", offer_wait_s=3)
            return await desk.find(**kwargs), bus, market

    return asyncio.run(scenario())


def test_tuttie_posts_collects_offers_and_shortlists_within_its_private_budget():
    result, bus, market = run_find(date="2026-11-14", tags=["basel-sbb"], requirements=["quiet", "dog"],
                                   budget_chf=200)
    # The budget never left Tuttie: the posting the hotels saw has none.
    posted = market.view(result["request_id"])["request"]
    assert posted["constraints"]["budget_chf"] is None and result["posted"]["constraints"]["budget_chf"] is None
    # Alpina (CHF 240) offered but is over the private budget; Rheinblick (CHF 180) fits.
    assert result["offers_received"] == 2
    assert [o["name"] for o in result["shortlist"]] == ["Hotel Rheinblick"]
    assert result["shortlist"][0]["price_chf"] == 180 and result["shortlist"][0]["size"] == "medium"
    assert "ch.basel.cheap-hotels" in result["skipped"] and "ch.basel.budget-rooms" in result["skipped"]
    phases = [e["detail"].get("phase") for e in bus.history if e["kind"] == "marketplace"]
    assert phases[0] == "posted" and phases.count("offer") == 2 and phases[-1] == "shortlist"


def test_without_a_budget_every_verified_offer_is_shortlisted_cheapest_first():
    result, _, _ = run_find(date="2026-11-14", tags=["basel-sbb"])
    assert [o["price_chf"] for o in result["shortlist"]] == [180, 240]


def test_shortlist_drops_untrusted_expired_and_over_budget_offers():
    now = datetime(2026, 11, 13, 20, tzinfo=timezone.utc)

    def item(name, tier, price, valid="2026-11-13T22:00:00Z"):
        return {"name": name, "trust_tier": tier, "offer": {"price_chf": price, "valid_until": valid}}

    offers = [item("blue", "blue", 150), item("gold", "gold", 150), item("grey", "grey", 90),
              item("old", "gold", 100, valid="2026-11-13T19:00:00Z"), item("dear", "gold", 260)]
    assert [o["name"] for o in shortlist(offers, 200, now)] == ["gold", "blue"]  # gold before blue at the same price


def test_tuttie_rejects_an_offer_whose_signature_does_not_match():
    result, _, market = run_find(date="2026-11-14", tags=["basel-sbb"])
    item = copy.deepcopy(market.view(result["request_id"])["offers"][0])
    item["offer"]["price_chf"] = 1  # what the market shows no longer matches what the hotel signed

    async def scenario():
        bus = EventBus()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=registry_app)) as http:
            desk = MarketDesk(http, "http://localhost:4000", bus, load_authorities())
            return await desk.check(item, {}), bus

    checked, bus = asyncio.run(scenario())
    assert checked is None and bus.history[-1]["status"] == "broken"
