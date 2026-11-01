"""Integration: offers from the real marketplace, then Tuttie's subagents bargain in parallel.

Real registry, real marketplace, real hotel apps (with the counter_offer tool mounted as the
server hook will do), Tuttie's real Toolbox and SubagentPool. Only the hotels' LLM is a stub.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import node.agent
from aps import load_signing_key, sign_envelope, verify_envelope
from aps.keys import load_public_key
from assistant.approvals import ApprovalBook
from assistant.events import EventBus
from assistant.subagents import SubagentPool
from assistant.tools import Toolbox
from marketplace.app import create_app as create_market_app
from marketplace.app import load_authorities
from marketplace.market import Market
from negotiation.tuttie import TuttieNegotiator, best
from negotiation_helpers import CONFIGS, RHEINBLICK, TUTTIE, node_app, signed_offer, stamp
from registry.app import app as registry_app
from sessions import Context

ALPINA = "ch.basel.alpina-grand"
HOTEL_DELAY = 0.1  # seconds each hotel "thinks" per session turn, to show the parallelism


class StubLLM:
    """Woken agents are interested and offer a double room; session questions get a short answer."""

    async def complete_json(self, system: str, user: str) -> dict:
        await asyncio.sleep(HOTEL_DELAY)
        if "decided to make an offer" in system:
            return {"room_type": "double", "add_ons": []}
        if "marketplace woke you" in system:
            return {"interested": True, "reason": "We have a room.", "next_tool": "make_offer"}
        return {"answer": "ok", "add_on": None, "arrival_date": None}


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    monkeypatch.setattr(node.agent, "LLM", StubLLM)


class Recorder(httpx.AsyncBaseTransport):
    """Routes requests to the in-process apps by port and records what was sent to hotels."""

    def __init__(self):
        self.transports: dict[int, httpx.AsyncBaseTransport] = {}
        self.sent_to_hotels: list[str] = []
        self.answers: list[tuple[str, int]] = []  # (path, HTTP status) of every hotel call

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.port not in (4000, 4010):
            self.sent_to_hotels.append((await request.aread()).decode())
        response = await self.transports[request.url.port].handle_async_request(request)
        if request.url.port not in (4000, 4010):
            self.answers.append((request.url.path, response.status_code))
        return response


def user_context(limit: float = 200) -> Context:
    return (Context().add("date", "2026-11-14", "public").add("requirements", ["quiet"], "negotiation")
            .add("max_price_chf", limit, "private").add("guest_name", "Alex Muster", "private"))


async def world(recorder: Recorder, http: httpx.AsyncClient) -> tuple[Toolbox, Market]:
    """Registry, every hotel (sending offers through `http`) and the marketplace, in process."""
    apps = {4000: registry_app}
    for node_id, config in CONFIGS.items():
        apps[config["port"]] = node_app(node_id, http=http)
    market_app = create_market_app(http)
    market = Market(http, "http://localhost:4000", load_authorities(), load_public_key("user"), "http://localhost:4010")
    market_app.state.market = market
    apps[4010] = market_app
    recorder.transports.update({port: httpx.ASGITransport(app=app) for port, app in apps.items()})
    return Toolbox(http, "http://localhost:4000", EventBus(), ApprovalBook()), market


async def collect_offers(http: httpx.AsyncClient, expected: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    request = {"type": "request", "request_id": "rq-bargain1", "category": "hotel", "tags": ["basel-sbb"],
               "constraints": {"date": "2026-11-14", "budget_chf": 200, "requirements": ["quiet"]},
               "expires_at": stamp(now + timedelta(hours=2))}
    response = await http.post("http://localhost:4010/postings", json=sign_envelope(TUTTIE, request, load_signing_key(TUTTIE)))
    assert response.status_code == 201, response.text
    for _ in range(100):  # offers arrive in the background
        view = (await http.get("http://localhost:4010/postings/rq-bargain1")).json()
        if len(view["offers"]) >= expected:
            return view["offers"]
        await asyncio.sleep(0.05)
    raise AssertionError(f"only {len(view['offers'])} offers arrived")


def test_tuttie_bargains_with_every_offering_hotel_in_parallel():
    recorder = Recorder()

    async def scenario():
        async with httpx.AsyncClient(transport=recorder) as http:
            toolbox, _ = await world(recorder, http)
            offers = await collect_offers(http, expected=2)
            negotiator = TuttieNegotiator(SubagentPool(toolbox), TUTTIE, load_signing_key(TUTTIE))
            start = asyncio.get_running_loop().time()
            outcomes = await negotiator.negotiate_all(offers, user_context(limit=200))
            return offers, outcomes, asyncio.get_running_loop().time() - start, toolbox

    offers, outcomes, elapsed, toolbox = asyncio.run(scenario())
    by_hotel = {o.node_id: o for o in outcomes}
    assert set(by_hotel) == {ALPINA, RHEINBLICK}

    # Rheinblick (offer 180) comes down to a price within the budget and signs an agreement.
    rheinblick = by_hotel[RHEINBLICK]
    assert rheinblick.status == "agreed" and 170 <= rheinblick.price_chf < 180
    assert verify_envelope(rheinblick.agreement, load_public_key(RHEINBLICK), RHEINBLICK)
    assert rheinblick.agreement["payload"]["type"] == "agreement"
    # Alpina (offer 240) stays above the private budget of 200 at its floor: Tuttie walks away.
    assert by_hotel[ALPINA].status == "walked_away" and by_hotel[ALPINA].price_chf is None
    assert best(outcomes) is rheinblick

    # Parallel: both negotiations together take about as long as one session turn per hotel.
    assert elapsed < 2 * HOTEL_DELAY + 1.0
    # The private budget limit and the guest's name never reached a hotel.
    sent = "\n".join(recorder.sent_to_hotels)
    assert "max_price_chf" not in sent and "Alex Muster" not in sent
    # Every round is on Tuttie's timeline, without any limit.
    rounds = [e["summary"] for e in toolbox.bus.history if "round" in e["summary"]]
    assert rounds and not any("floor" in line or "limit" in line for line in rounds)


def test_subagent_memory_records_every_round():
    recorder = Recorder()

    async def scenario():
        async with httpx.AsyncClient(transport=recorder) as http:
            toolbox, _ = await world(recorder, http)
            pool = SubagentPool(toolbox)
            negotiator = TuttieNegotiator(pool, TUTTIE, load_signing_key(TUTTIE))
            outcome = await negotiator.negotiate(RHEINBLICK, signed_offer(RHEINBLICK), user_context(limit=175))
            return outcome, pool.subagents[outcome.subagent_id]

    outcome, subagent = asyncio.run(scenario())
    kinds = [turn.kind for turn in subagent.memory.turns]
    own_counters = [t for t in subagent.memory.turns if t.author == "self" and t.kind == "counter"]
    assert kinds[0] == "opened" and len(own_counters) == outcome.rounds
    assert kinds[-1] == "agreement"
    assert "max_price_chf" not in json.dumps(subagent.memory.context)  # the subagent only got shareable context
    assert outcome.status == "agreed" and outcome.price_chf <= 175
    # The negotiation closed its session with the hotel (frees the hotel's slot) and its memory.
    assert subagent.memory.status == "closed" and subagent.remote_session is None
    closes = [status for path, status in recorder.answers if path.endswith("/close")]
    assert closes == [200]


def test_a_forged_hotel_is_refused_before_any_bargaining():
    recorder = Recorder()

    async def scenario():
        async with httpx.AsyncClient(transport=recorder) as http:
            toolbox, _ = await world(recorder, http)
            negotiator = TuttieNegotiator(SubagentPool(toolbox), TUTTIE, load_signing_key(TUTTIE))
            return await negotiator.negotiate("ch.basel.cheap-hotels", signed_offer("ch.basel.cheap-hotels"),
                                              user_context())

    outcome = asyncio.run(scenario())
    assert outcome.status == "refused" and outcome.rounds == 0


def bargain(node_id: str, add_ons: tuple, budget: float) -> list[tuple]:
    """One negotiation against the real hotel app; the moves as (Tuttie, hotel answer, price)."""
    recorder = Recorder()

    async def scenario():
        async with httpx.AsyncClient(transport=recorder) as http:
            toolbox, _ = await world(recorder, http)
            negotiator = TuttieNegotiator(SubagentPool(toolbox), TUTTIE, load_signing_key(TUTTIE))
            return await negotiator.negotiate(node_id, signed_offer(node_id, add_ons=add_ons), user_context(budget))

    outcome = asyncio.run(scenario())
    return [(step["own_chf"], step["hotel"]["type"], step["hotel"]["price_chf"]) for step in outcome.history]


def test_the_pitch_story_anna_s_guesthouse():
    """documentation/context/pitch/storyline.md: "...with my dog, under 160" → Gästehaus am Rhein
    (CHF 135) wins and Tuttie bargains: three visible rounds, agreed at CHF 128, above Anna's
    private floor but never at it. If this test has to change, tell the pitch team: the numbers
    are on stage (preview: scripts/bargain_preview.py)."""
    moves = bargain("ch.basel.gaestehaus-am-rhein", ("late-arrival-dog",), budget=160)
    assert moves == [(121, "counter", 131), (126, "counter", 130), (128, "agreement", 128)]


def test_the_rheinblick_story():
    """The earlier live run (double + dog at CHF 195, budget 200), now over three rounds."""
    moves = bargain(RHEINBLICK, ("dog",), budget=200)
    assert moves == [(175, "counter", 189), (182, "counter", 187), (185, "agreement", 185)]
