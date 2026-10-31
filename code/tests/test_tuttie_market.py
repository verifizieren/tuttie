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
from assistant.approvals import ApprovalBook
from assistant.tools import Toolbox
from negotiation_helpers import registry_lookup
from node.server import create_app
from registry.app import app as registry_app
from tests.mcp_helpers import in_process_link

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


def run_find(negotiate_budget: float | None = None, book_agreement: bool = False,
             favourites: list[str] | None = None, resume_before_booking: bool = False,
             **kwargs) -> tuple[dict, EventBus, Market]:
    async def scenario():
        transports = {}

        class Router(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                return await transports[request.url.port].handle_async_request(request)

        async with httpx.AsyncClient(transport=Router()) as http:
            apps = {4000: registry_app}
            for path in (DATA / "nodes").glob("*.json"):
                config = json.loads(path.read_text())
                apps[config["port"]] = create_app(config, http=http, lookup=registry_lookup)
            market_app = create_market_app(http)
            market = Market(http, "http://localhost:4000", load_authorities(), load_public_key("user"),
                            "http://localhost:4010")
            market_app.state.market = market
            apps[4010] = market_app
            transports.update({port: httpx.ASGITransport(app=app) for port, app in apps.items()})
            bus = EventBus()
            desk = MarketDesk(http, "http://localhost:4000", bus, load_authorities(),
                              market_url="http://localhost:4010", offer_wait_s=3)
            link = in_process_link({f"http://localhost:{port}": app for port, app in apps.items()})
            toolbox = Toolbox(http, "http://localhost:4000", bus, ApprovalBook(), market=desk, mcp=link)
            result = await toolbox.post_request(**kwargs)  # the LLM tool: find, then the cards
            if negotiate_budget is not None:
                result["negotiation"] = await toolbox.negotiate(budget_chf=negotiate_budget, node_ids=favourites)
                if book_agreement:  # the user approves on the phone while book waits
                    if resume_before_booking:
                        from assistant.conversations import Conversations
                        chats = Conversations(http, "http://localhost:4000", llm=object())
                        original = chats.get("browser")
                        original.assistant.toolbox = toolbox
                        chats.switch("browser")
                        assert chats.get("browser").assistant.toolbox.agreements == {}
                        toolbox = chats.switch("browser", original.id).assistant.toolbox
                    async def phone():
                        while not toolbox.approvals.pending:
                            await asyncio.sleep(0.01)
                        approval = next(iter(toolbox.approvals.pending.values()))
                        result["approved_chf"] = approval["amount_chf"]
                        toolbox.approvals.decide(approval["id"], "approved")
                    tap = asyncio.create_task(phone())
                    result["booking"] = await toolbox.book("ch.basel.hotel-rheinblick", "2026-11-15", "double",
                                                           "Alex Muster", use_agreement=True)
                    await tap
            return result, bus, market

    return asyncio.run(scenario())


def test_tuttie_posts_collects_offers_and_shortlists_within_its_private_budget():
    result, bus, market = run_find(date="2026-11-14", tags=["basel-sbb"], requirements=["quiet", "dog"],
                                   budget_chf=200)
    # The budget never left Tuttie: the posting the hotels saw has none.
    posted = market.view(result["request_id"])["request"]
    assert posted["constraints"]["budget_chf"] is None and result["posted"]["constraints"]["budget_chf"] is None
    # Alpina (CHF 270 with the dog) offered but is over the private budget; Rheinblick (CHF 195) fits.
    assert result["offers_received"] == 2
    assert [o["name"] for o in result["shortlist"]] == ["Hotel Rheinblick"]
    # The dog needs Rheinblick's add-on (CHF 15): every fee that applies is in the offer.
    assert result["shortlist"][0]["price_chf"] == 195 and result["shortlist"][0]["size"] == "medium"
    assert "ch.basel.cheap-hotels" in result["skipped"] and "ch.basel.budget-rooms" in result["skipped"]
    phases = [e["detail"].get("phase") for e in bus.history if e["kind"] == "marketplace"]
    assert phases[0] == "posted" and phases.count("offer") == 2 and phases[-3:] == ["shortlist", "agreement", "cards"]


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


def test_tuttie_negotiates_its_shortlist_and_gets_a_signed_agreement():
    result, bus, _ = run_find(negotiate_budget=200, date="2026-11-14", tags=["basel-sbb"], budget_chf=200)
    negotiation = result["negotiation"]
    assert negotiation["best"]["hotel"] == "Hotel Rheinblick"
    assert negotiation["best"]["price_chf"] <= 180  # bargained from the offer, within the private budget
    agreement = [e for e in bus.history if e["detail"].get("phase") == "agreement"][-1]
    assert agreement["detail"]["agreement"]["payload"]["type"] == "agreement"
    # The private budget was never sent: no event or message on the way mentions it as a limit.
    assert all("max_price" not in json.dumps(e) for e in bus.history)


def test_tuttie_books_the_negotiated_price_after_the_phone_approval():
    result, _, _ = run_find(negotiate_budget=200, book_agreement=True, date="2026-11-14", tags=["basel-sbb"],
                            budget_chf=200)
    agreed = result["negotiation"]["best"]["price_chf"]
    assert result["approved_chf"] == agreed  # the user approved exactly the negotiated price
    assert result["booking"]["status"] == "confirmed" and result["booking"]["total_chf"] == agreed
    assert result["booking"]["date"] == "2026-11-14"  # the posted night, even if the LLM passes another date


def test_resumed_chat_can_book_its_signed_agreement_after_starting_a_new_chat():
    result, _, _ = run_find(negotiate_budget=200, book_agreement=True, resume_before_booking=True,
                            date="2026-11-14", tags=["basel-sbb"], budget_chf=200)
    agreed = result["negotiation"]["best"]["price_chf"]
    assert result["approved_chf"] == agreed
    assert result["booking"]["status"] == "confirmed"
    assert result["booking"]["total_chf"] == agreed


def test_the_cards_show_every_offer_with_signed_features_shortlist_first():
    result, bus, _ = run_find(date="2026-11-14", tags=["basel-sbb"], requirements=["quiet", "dog"], budget_chf=200)
    cards = [e for e in bus.history if e["detail"].get("phase") == "cards"][-1]["detail"]["cards"]
    assert [(c["name"], c["shortlisted"]) for c in cards] == [("Hotel Rheinblick", True), ("Alpina Grand Basel", False)]
    rheinblick, alpina = cards
    labels = {c["name"]: {f["label"]: f["ok"] for f in c["features"]} for c in cards}
    assert labels["Hotel Rheinblick"]["Dogs CHF 15"] and labels["Hotel Rheinblick"]["Quiet"]
    assert alpina["over_budget_chf"] == 70 and labels["Alpina Grand Basel"]["Not quiet"] is False  # 240 + dog 30
    assert rheinblick["rating"]["score"] == 4.5
    assert [c["name"] for c in result["cards"]] == ["Hotel Rheinblick", "Alpina Grand Basel"]


def test_tuttie_bargains_before_the_cards_and_they_show_the_agreed_price():
    result, bus, _ = run_find(date="2026-11-14", tags=["basel-sbb"], requirements=["quiet", "dog"], budget_chf=200)
    phases = [e["detail"].get("phase") for e in bus.history if e["kind"] == "marketplace"]
    assert phases.index("agreement") < phases.index("cards")
    cards = {c["name"]: c for c in result["cards"]}
    assert cards["Hotel Rheinblick"]["agreed_chf"] < cards["Hotel Rheinblick"]["price_chf"]
    assert cards["Alpina Grand Basel"]["agreed_chf"] is None  # over the private budget: no deal


def test_negotiate_can_be_limited_to_some_hotels():
    result, _, _ = run_find(negotiate_budget=300, favourites=["ch.basel.alpina-grand"], date="2026-11-14",
                            tags=["basel-sbb"], budget_chf=300)
    assert [o["hotel"] for o in result["negotiation"]["outcomes"]] == ["Alpina Grand Basel"]
