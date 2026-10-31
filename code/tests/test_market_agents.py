"""Integration: the real marketplace wakes the real company agents (only the LLM is a stub).

test_marketplace.py checks the market against fake businesses and test_business_agent.py
checks the agents on their own; this test makes sure the two actually fit together.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

import node.agent
from aps import load_signing_key, sign_envelope
from aps.keys import load_public_key
from marketplace.app import create_app as create_market_app
from marketplace.app import load_authorities
from marketplace.market import Market
from node.server import create_app
from registry.app import app as registry_app

DATA = Path(__file__).resolve().parent.parent / "data"
TUTTIE = "ch.tuttie.alex-muster"
OFFERING = {"ch.basel.alpina-grand", "ch.basel.hotel-rheinblick"}  # at Basel SBB, with make_offer


class StubLLM:
    """Every woken agent is interested, makes an offer next, and offers a double room."""

    async def complete_json(self, system: str, user: str) -> dict:
        if "decided to make an offer" in system:
            return {"room_type": "double", "add_ons": [], "price_chf": 1}  # a price from the LLM is ignored
        return {"interested": True, "reason": "We have a room.", "next_tool": "make_offer"}


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    monkeypatch.setattr(node.agent, "LLM", StubLLM)


class PortRouter(httpx.AsyncBaseTransport):
    """Send each request to the in-process app registered for its port."""

    def __init__(self, apps: dict):
        self.transports = {port: httpx.ASGITransport(app=app) for port, app in apps.items()}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self.transports[request.url.port].handle_async_request(request)


def test_market_wakes_the_matching_company_agents():
    async def scenario():
        apps = {4000: registry_app}
        for path in (DATA / "nodes").glob("*.json"):
            config = json.loads(path.read_text())
            apps[config["port"]] = create_app(config)
        async with httpx.AsyncClient(transport=PortRouter(apps)) as http:
            market = Market(http, "http://localhost:4000", load_authorities(), load_public_key("user"),
                            "http://localhost:4010")
            now = datetime.now(timezone.utc)
            request = {"type": "request", "request_id": "rq-agents1", "category": "hotel", "tags": ["basel-sbb"],
                       "constraints": {"date": "2026-11-14", "budget_chf": 200, "requirements": ["quiet", "dog"]},
                       "expires_at": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")}
            envelope = sign_envelope(TUTTIE, request, load_signing_key(TUTTIE))
            return await market.post_request(envelope)

    invited = asyncio.run(scenario())["invited"]
    # Hotels at Basel SBB are woken through POST /agent/invoke and answer as agents.
    for node_id in ("ch.basel.alpina-grand", "ch.basel.hotel-rheinblick"):
        assert invited[node_id]["status"] == "interested", invited[node_id]
        assert invited[node_id]["next_tool"] == "make_offer"
    assert "ch.basel.cheap-hotels" not in invited        # broken seal: never contacted
    assert "ch.basel.gaestehaus-am-rhein" not in invited  # not at Basel SBB: not matching


def test_woken_agents_send_signed_offers_back_to_the_market():
    async def scenario():
        transports = {}

        class Router(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                return await transports[request.url.port].handle_async_request(request)

        async with httpx.AsyncClient(transport=Router()) as http:
            apps = {4000: registry_app}
            for path in (DATA / "nodes").glob("*.json"):
                config = json.loads(path.read_text())
                apps[config["port"]] = create_app(config, http=http)  # nodes post offers through `http`
            market_app = create_market_app(http)
            market_app.state.market = Market(http, "http://localhost:4000", load_authorities(),
                                             load_public_key("user"), "http://localhost:4010")
            apps[4010] = market_app
            transports.update({port: httpx.ASGITransport(app=app) for port, app in apps.items()})

            now = datetime.now(timezone.utc)
            request = {"type": "request", "request_id": "rq-offers1", "category": "hotel", "tags": ["basel-sbb"],
                       "constraints": {"date": "2026-11-14", "budget_chf": 200, "requirements": ["quiet"]},
                       "expires_at": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")}
            response = await http.post("http://localhost:4010/postings",
                                       json=sign_envelope(TUTTIE, request, load_signing_key(TUTTIE)))
            assert response.status_code == 201, response.text
            for _ in range(50):  # offers arrive in the background
                view = (await http.get("http://localhost:4010/postings/rq-offers1")).json()
                if len(view["offers"]) >= len(OFFERING):
                    break
                await asyncio.sleep(0.05)
            return view

    view = asyncio.run(scenario())
    offers = {o["node_id"]: o["offer"] for o in view["offers"]}
    # Only agents that have the make_offer tool offer; default agents (no "agent" section) do not.
    assert set(offers) == OFFERING
    assert offers["ch.basel.hotel-rheinblick"]["price_chf"] == 180  # from the config, not the LLM
    assert offers["ch.basel.alpina-grand"]["price_chf"] == 240
