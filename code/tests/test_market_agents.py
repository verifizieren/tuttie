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
from marketplace.app import load_authorities
from marketplace.market import Market
from node.server import create_app
from registry.app import app as registry_app

DATA = Path(__file__).resolve().parent.parent / "data"
TUTTIE = "ch.tuttie.alex-muster"


class StubLLM:
    """Every woken agent is interested and would make an offer next."""

    async def complete_json(self, system: str, user: str) -> dict:
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
