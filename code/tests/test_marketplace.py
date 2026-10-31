"""Tests for the marketplace agent layer: signed postings in, signed offers out.

Runs against the real demo registry and keys; HTTP is mocked. Businesses answer the
wake-up (POST /agent/invoke) the way the planned business agent will:
{"interested": true, "next_tool": "make_offer"}.
"""

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from nacl.signing import SigningKey
from pydantic import ValidationError

from aps import load_signing_key, sign_envelope, verify_envelope
from aps.delegation import verify_delegation
from aps.keys import load_public_key
from marketplace.app import create_app, load_authorities
from marketplace.client import new_request_id, sign_request
from marketplace.market import Market, MarketError
from marketplace.messages import Request

REGISTRY = json.loads((Path(__file__).resolve().parent.parent / "data" / "registry.json").read_text())
TUTTIE = "ch.tuttie.alex-muster"
ALPINA = "ch.basel.alpina-grand"
RHEINBLICK, GUNDELI, SPALENHOF = "ch.basel.hotel-rheinblick", "ch.basel.hotel-gundeli", "ch.basel.hotel-spalenhof"
BUDGET_ROOMS, SCAM, LAWYER = "ch.basel.budget-rooms", "ch.basel.cheap-hotels", "ch.legal.consumer-law"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class World:
    """A mocked registry plus business agents; records who was contacted and what they got."""

    def __init__(self, registry=REGISTRY, invoke_reply=None, down=(), unsubscribed=()):
        self.registry = registry
        self.invoke_reply = invoke_reply or {"interested": True, "next_tool": "make_offer"}
        self.down = set(down)  # node ids whose /agent/invoke fails
        self.unsubscribed = set(unsubscribed)  # node ids whose agent does not wake on new postings
        self.events: dict[str, dict] = {}  # node_id -> PostingCreated it received
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/search":
            wanted = {t for t in request.url.params.get("tags", "").split(",") if t}
            return httpx.Response(200, json=[r for r in self.registry if wanted <= set(r["tags"])])
        if path.startswith("/nodes/"):
            record = next((r for r in self.registry if r["node_id"] == path.removeprefix("/nodes/")), None)
            return httpx.Response(200, json=record) if record else httpx.Response(404)
        if path == "/agent/card":  # signed by the business, like the real node
            node = next(r for r in self.registry if r["endpoint"].endswith(f":{request.url.port}"))
            wakes_on = [] if node["node_id"] in self.unsubscribed else ["posting.created"]
            card = {"node_id": node["node_id"], "persona": {"name": "Agent"}, "profile": {"size": "medium"},
                    "wakes_on": wakes_on}
            return httpx.Response(200, json=sign_envelope(node["node_id"], card, load_signing_key(node["node_id"])))
        if path == "/agent/invoke":
            node = next(r for r in self.registry if r["endpoint"].endswith(f":{request.url.port}"))
            if node["node_id"] in self.down:
                return httpx.Response(404)
            self.events[node["node_id"]] = json.loads(request.content)
            return httpx.Response(200, json=self.invoke_reply)
        return httpx.Response(404)

    def market(self) -> Market:
        return Market(self.http, "http://registry", load_authorities(), load_public_key("user"), "http://market")


def request(request_id="rq-test1", budget=200, expires=NOW + timedelta(hours=2), **changes) -> Request:
    body = {"request_id": request_id, "category": "hotel", "tags": ["basel-sbb"],
            "constraints": {"date": "2026-11-14", "budget_chf": budget, "requirements": ["quiet", "dog"]},
            "expires_at": stamp(expires), **changes}
    return Request.model_validate(body)


def tuttie_envelope(req: Request | None = None, key: SigningKey | None = None, timestamp: str | None = None) -> dict:
    body = (req or request()).model_dump(mode="json")
    return sign_envelope(TUTTIE, body, key or load_signing_key(TUTTIE), timestamp or stamp(NOW))


def offer_envelope(node_id=RHEINBLICK, price=195, offer_id="of-1", request_id="rq-test1",
                   valid_until=NOW + timedelta(hours=1), key=None, timestamp=None) -> dict:
    payload = {"type": "offer", "request_id": request_id, "offer_id": offer_id, "item": "double room 14 Nov",
               "price_chf": price, "includes": ["late check-in with dog"], "conditions": ["non-refundable"],
               "valid_until": stamp(valid_until)}
    return sign_envelope(node_id, payload, key or load_signing_key(node_id), timestamp or stamp(NOW))


def posted(world: World | None = None) -> tuple[Market, World, dict]:
    world = world or World()
    market = world.market()
    return market, world, asyncio.run(market.post_request(tuttie_envelope(), now=NOW))


def refused(coroutine) -> MarketError:
    with pytest.raises(MarketError) as caught:
        asyncio.run(coroutine)
    return caught.value


# --- postings ------------------------------------------------------------------------------


def test_posting_wakes_only_verified_businesses():
    _, world, view = posted()
    assert set(view["invited"]) == {ALPINA, RHEINBLICK, SPALENHOF, GUNDELI}
    assert set(world.events) == set(view["invited"])  # untrusted and broken ones never contacted
    assert view["skipped"][BUDGET_ROOMS] == {"name": "Basel Budget Rooms", "trust_tier": "grey", "reason": "untrusted"}
    assert view["skipped"][SCAM]["reason"] == "broken seal"
    assert view["invited"][RHEINBLICK] == {"name": "Hotel Rheinblick", "trust_tier": "gold", "agent": "Agent",
                                           "profile": {"size": "medium"}, "status": "interested",
                                           "next_tool": "make_offer"}


def test_only_agents_subscribed_to_new_postings_are_woken():
    _, world, view = posted(World(unsubscribed={SPALENHOF}))
    assert SPALENHOF not in view["invited"] and SPALENHOF not in world.events
    assert view["skipped"][SPALENHOF]["reason"] == "not subscribed to new postings"


def test_woken_business_can_verify_tuttie_itself():
    """The event carries Tuttie's signed request unchanged, plus where to send the offer."""
    _, world, _ = posted()
    event = world.events[GUNDELI]
    assert event["type"] == "posting.created"
    posting = event["posting"]
    tuttie = next(r for r in REGISTRY if r["node_id"] == TUTTIE)
    assert verify_envelope(posting["request"], tuttie["public_key"], TUTTIE)
    assert verify_delegation(tuttie["delegation"], load_public_key("user"), TUTTIE, tuttie["public_key"],
                             scope="post_requests")
    assert posting["offer_url"] == "http://market/postings/rq-test1/offers"


def test_unreachable_or_declining_business_is_recorded():
    _, _, view = posted(World(down={SPALENHOF}, invoke_reply={"interested": False}))
    assert view["invited"][SPALENHOF]["status"] == "unreachable"
    assert view["invited"][GUNDELI]["status"] == "declined"


def test_refuses_requests_that_do_not_verify():
    market = World().market()
    tampered = tuttie_envelope()
    tampered["payload"]["constraints"]["budget_chf"] = 1000
    assert "signature" in refused(market.post_request(tampered, now=NOW)).reason
    forged = tuttie_envelope(key=SigningKey.generate())
    assert refused(market.post_request(forged, now=NOW)).status == 403
    old = tuttie_envelope(timestamp=stamp(NOW - timedelta(hours=1)))
    assert "outdated" in refused(market.post_request(old, now=NOW)).reason


def test_only_delegated_user_agents_may_post():
    as_hotel = sign_envelope(RHEINBLICK, request().model_dump(mode="json"), load_signing_key(RHEINBLICK), stamp(NOW))
    assert "user agents" in refused(World().market().post_request(as_hotel, now=NOW)).reason
    registry = copy.deepcopy(REGISTRY)
    next(r for r in registry if r["node_id"] == TUTTIE)["delegation"]["scopes"] = ["ask_agents"]
    error = refused(World(registry=registry).market().post_request(tuttie_envelope(), now=NOW))
    assert "delegation" in error.reason
    assert refused(World().market().post_request({"node_id": "../admin"}, now=NOW)).reason == "invalid sender id"


def test_refuses_invalid_expired_or_duplicate_requests():
    market = World().market()
    bad = tuttie_envelope()
    bad["payload"]["secret_budget"] = 250  # unknown field: contract drift
    bad = sign_envelope(TUTTIE, bad["payload"], load_signing_key(TUTTIE), stamp(NOW))
    assert "not a valid request" in refused(market.post_request(bad, now=NOW)).reason
    expired = tuttie_envelope(request(expires=NOW - timedelta(minutes=1)))
    assert "expired" in refused(market.post_request(expired, now=NOW)).reason
    asyncio.run(market.post_request(tuttie_envelope(), now=NOW))
    assert refused(market.post_request(tuttie_envelope(), now=NOW)).status == 409


# --- offers --------------------------------------------------------------------------------


def test_signed_offer_from_invited_business_is_accepted():
    market, _, _ = posted()
    accepted = asyncio.run(market.receive_offer("rq-test1", offer_envelope(), now=NOW))
    assert accepted["trust_tier"] == "gold" and accepted["uid"] == "CHE-526.018.151"
    assert accepted["offer"]["price_chf"] == 195
    assert verify_envelope(accepted["envelope"], load_public_key(RHEINBLICK), RHEINBLICK)
    assert market.view("rq-test1")["offers"] == [accepted]


def test_untrusted_business_may_not_offer():
    market, _, _ = posted()
    assert refused(market.receive_offer("rq-test1", offer_envelope(BUDGET_ROOMS), now=NOW)).status == 403


def test_refuses_offers_from_businesses_that_were_not_invited():
    market, _, _ = posted()
    for node_id in (SCAM, LAWYER):  # broken seals; or not matching the posting
        error = refused(market.receive_offer("rq-test1", offer_envelope(node_id), now=NOW))
        assert error.status == 403 and "invited" in error.reason


def test_refuses_offers_that_do_not_verify_or_do_not_fit():
    market, _, _ = posted()
    tampered = offer_envelope()
    tampered["payload"]["price_chf"] = 1
    assert "signature" in refused(market.receive_offer("rq-test1", tampered, now=NOW)).reason
    stale = offer_envelope(timestamp=stamp(NOW - timedelta(hours=1)))
    assert "outdated" in refused(market.receive_offer("rq-test1", stale, now=NOW)).reason
    other = offer_envelope(request_id="rq-other")
    assert "another request" in refused(market.receive_offer("rq-test1", other, now=NOW)).reason
    expired = offer_envelope(valid_until=NOW - timedelta(minutes=1))
    assert "expired" in refused(market.receive_offer("rq-test1", expired, now=NOW)).reason
    asyncio.run(market.receive_offer("rq-test1", offer_envelope(), now=NOW))
    assert refused(market.receive_offer("rq-test1", offer_envelope(), now=NOW)).status == 409


def test_refuses_offers_for_unknown_or_expired_postings():
    market, _, _ = posted()
    assert refused(market.receive_offer("rq-nope", offer_envelope(), now=NOW)).status == 404
    later = NOW + timedelta(hours=3)
    assert refused(market.receive_offer("rq-test1", offer_envelope(), now=later)).status == 410


# --- formats and the HTTP service ----------------------------------------------------------


def test_request_format_is_strict():
    for change in ({"expires_at": "tomorrow"}, {"tags": ["Basel SBB"]}, {"request_id": "x"},
                   {"constraints": {"date": "2026-11-14", "budget_chf": -5}}):
        with pytest.raises(ValidationError):
            request(**change)
    assert new_request_id().startswith("rq-") and Request.model_validate(
        request(request_id=new_request_id()).model_dump()).type == "request"


def test_http_flow_post_and_offer():
    world = World()
    with TestClient(create_app(world.http)) as client:
        envelope = sign_request(request(), TUTTIE, load_signing_key(TUTTIE))
        assert client.post("/postings", json=envelope).status_code == 201
        assert client.post("/postings/rq-test1/offers", json=offer_envelope(timestamp=None)).status_code == 201
        assert [o["node_id"] for o in client.get("/postings/rq-test1").json()["offers"]] == [RHEINBLICK]
        refusal = client.post("/postings/rq-test1/offers", json=offer_envelope(SCAM))
        assert refusal.status_code == 403 and refusal.json()["refused"] is True
        assert client.get("/postings/rq-nope").status_code == 404
