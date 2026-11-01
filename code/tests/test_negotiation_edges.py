"""Edge cases of bargaining that the main tests do not reach: refusals in the middle of a
negotiation, Tuttie's own round cap, unreachable registries, and malformed signed payloads."""

import asyncio
import copy
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

import negotiation.hotel as hotel
from aps import load_signing_key, sign_envelope
from aps.keys import load_public_key
from assistant.tools import Verified
from negotiation.agreement import AgreementInvalid, AgreementRedeemer
from negotiation.tuttie import MAX_ROUNDS, Outcome, TuttieNegotiator, best
from negotiation_helpers import REGISTRY, RHEINBLICK, TUTTIE, node_app, signed_offer
from sessions import Context, SessionStore

RECORD = REGISTRY[RHEINBLICK]


@dataclass
class ScriptedToolbox:
    """Stands in for Tuttie's trust gate: answers each counter with the next scripted reply."""

    replies: list

    async def verified_post(self, node_id, path, body, kind, label):
        reply = self.replies.pop(0)
        if isinstance(reply, dict) and reply.get("rejected"):
            return reply  # what the trust gate returns when a node fails verification
        return Verified(RECORD, {"tier": "gold", "seals": []}, {"payload": reply, "timestamp": "x"})

    def emit_verified(self, kind, summary, result):
        return 0


class ScriptedSubagent:
    def __init__(self, toolbox, memory, open_ok=True):
        self.toolbox, self.memory, self.id = toolbox, memory, memory.id
        self.remote_session = None
        self.open_ok = open_ok

    async def open(self):
        if self.open_ok:
            self.remote_session = "se-remote"
            return {"session_id": "se-remote"}
        return {"rejected": True, "reason": "seal does not verify"}


class ScriptedPool:
    def __init__(self, replies, open_ok=True):
        self.toolbox, self.open_ok = ScriptedToolbox(list(replies)), open_ok
        self.memories = SessionStore("tuttie")
        self.closed = []

    async def close(self, subagent):
        self.closed.append(subagent.id)

    def spawn(self, node_id, task, context):
        return ScriptedSubagent(self.toolbox, self.memories.open(node_id, task, context.share("negotiation")),
                                self.open_ok)


def negotiate(replies, limit=200, open_ok=True) -> Outcome:
    negotiator = TuttieNegotiator(ScriptedPool(replies, open_ok), TUTTIE, load_signing_key(TUTTIE))
    context = Context().add("max_price_chf", limit, "private")
    return asyncio.run(negotiator.negotiate(RHEINBLICK, signed_offer(), context))


def counter(price, final=False, round_=1):
    return {"tool": "counter_offer", "type": "counter", "offer_id": "of-hotel-rheinblick-1", "round": round_,
            "price_chf": price, "includes": [], "conditions": ["best rate, non-refundable"], "final": final}


# --- Tuttie's side ------------------------------------------------------------------------


def test_session_refused_means_no_bargaining():
    outcome = negotiate([], open_ok=False)
    assert outcome.status == "refused" and outcome.rounds == 0 and "seal" in outcome.reason


@pytest.mark.parametrize("reply, status", [
    ({"rejected": True, "reason": "response signature does not verify"}, "refused"),
    ({"tool": "counter_offer", "status": "refused", "reason": "counter is outdated"}, "refused"),
    ({"tool": "counter_offer", "type": "rejection", "offer_id": "of-1", "round": 1, "reason": "fixed prices"},
     "rejected"),
])
def test_refusals_and_rejections_end_the_negotiation(reply, status):
    outcome = negotiate([reply])
    assert outcome.status == status and outcome.rounds == 1 and outcome.price_chf is None


def test_a_stubborn_hotel_hits_tuttie_s_own_round_cap():
    outcome = negotiate([counter(195, round_=n) for n in range(1, MAX_ROUNDS + 1)], limit=190)
    assert outcome.status == "walked_away" and outcome.rounds == MAX_ROUNDS
    assert "Tuttie's rounds" in outcome.reason
    assert all(step["own_chf"] <= 190 for step in outcome.history)  # never above the private limit


def test_final_price_above_the_budget_means_walking_away():
    outcome = negotiate([counter(186, final=True)], limit=180)
    assert outcome.status == "walked_away" and "above the budget" in outcome.reason


def test_without_agreements_there_is_no_best():
    assert best([]) is None
    assert best([Outcome("x", "of-1", "walked_away", 100)]) is None


# --- the hotel's side --------------------------------------------------------------------


def test_hotel_lookup_of_an_unreachable_registry_finds_nothing(monkeypatch):
    monkeypatch.setattr(hotel, "REGISTRY_URL", "http://127.0.0.1:9")  # nothing listens there
    assert asyncio.run(hotel.registry_lookup(TUTTIE)) is None


def test_counter_from_a_user_agent_with_broken_seals_is_refused():
    broken = copy.deepcopy(REGISTRY)
    broken[TUTTIE]["seals"][0]["signature"] = "AAAA"

    async def lookup(node_id):
        return broken.get(node_id)

    client, offer = TestClient(node_app(RHEINBLICK, lookup)), signed_offer()
    body = {"type": "counter", "offer_id": offer["payload"]["offer_id"], "round": 1, "price_chf": 170,
            "includes": [], "conditions": offer["payload"]["conditions"]}
    reply = client.post("/tools/counter_offer", json={
        "counter": sign_envelope(TUTTIE, body, load_signing_key(TUTTIE)), "offer": offer}).json()
    assert reply["payload"]["status"] == "refused" and "seals do not verify" in reply["payload"]["reason"]


@pytest.mark.parametrize("payload", [["not", "an", "object"], "text", 42])
def test_signed_payloads_that_are_not_objects_are_refused_not_crashing(payload):
    client, offer = TestClient(node_app(RHEINBLICK)), signed_offer()
    odd_offer = sign_envelope(RHEINBLICK, payload, load_signing_key(RHEINBLICK))
    odd_counter = sign_envelope(TUTTIE, payload, load_signing_key(TUTTIE))
    good_counter = sign_envelope(TUTTIE, {"type": "counter", "offer_id": offer["payload"]["offer_id"], "round": 1,
                                          "price_chf": 170, "includes": [],
                                          "conditions": offer["payload"]["conditions"]}, load_signing_key(TUTTIE))
    for body, reason in (({"counter": good_counter, "offer": odd_offer}, "offer is not a valid Offer"),
                         ({"counter": odd_counter, "offer": offer}, "counter is not a valid Counter")):
        response = client.post("/tools/counter_offer", json=body)
        assert response.status_code == 200 and reason in response.json()["payload"]["reason"]
    with pytest.raises(AgreementInvalid, match="not a valid agreement"):
        AgreementRedeemer(RHEINBLICK, load_public_key(RHEINBLICK)).check(odd_offer)


def test_hotel_lookup_of_an_unknown_node_finds_nothing(monkeypatch):
    """The registry answers 404 for an unknown node: the counter's sender is then unknown."""
    import httpx

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(404, json={"detail": "unknown node"}))
    monkeypatch.setattr(hotel.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))
    assert asyncio.run(hotel.registry_lookup("ch.nobody.agent")) is None


def test_a_final_price_within_the_budget_is_accepted_with_a_matching_counter():
    """The hotel's last word fits the budget: Tuttie's next counter is exactly that price."""
    agreement = {"tool": "counter_offer", "type": "agreement", "request_id": "rq-neg1",
                 "offer_id": "of-hotel-rheinblick-1", "round": 2, "item": "double room 2026-11-14", "room_type": "double",
                 "date": "2026-11-14", "rate": "best rate, non-refundable", "price_chf": 175,
                 "includes": [], "conditions": ["best rate, non-refundable"], "valid_until": "2099-01-01T00:00:00Z"}
    outcome = negotiate([counter(175, final=True), agreement], limit=180)
    assert outcome.status == "agreed" and outcome.price_chf == 175 and outcome.rounds == 2
    assert [step["own_chf"] for step in outcome.history] == [162, 175]  # opened 10 % below 180, then matched


def agreement(price, **changes):
    """A signed-looking agreement about signed_offer()'s terms, as the hotel would copy them."""
    return {"tool": "counter_offer", "type": "agreement", "request_id": "rq-neg1",
            "offer_id": "of-hotel-rheinblick-1", "round": 1, "item": "double room 2026-11-14",
            "room_type": "double", "date": "2026-11-14", "rate": "best rate, non-refundable",
            "price_chf": price, "includes": [], "conditions": ["best rate, non-refundable"],
            "valid_until": "2099-01-01T00:00:00Z", **changes}


def test_an_agreement_at_tuttie_s_counter_is_agreed():
    outcome = negotiate([agreement(162)], limit=180)  # Tuttie opened at 162 (10 % below 180)
    assert outcome.status == "agreed" and outcome.price_chf == 162


@pytest.mark.parametrize("limit, price", [
    (150, 900),   # far above the private budget
    (200, 999),   # above the offer price
    (200, 163),   # one franc above Tuttie's own counter (162)
])
def test_an_agreement_above_tuttie_s_counter_is_refused(limit, price):
    outcome = negotiate([agreement(price)], limit=limit)
    assert outcome.status == "refused" and outcome.price_chf is None and outcome.agreement is None
    assert "above" in outcome.reason


def test_an_agreement_without_a_budget_is_capped_by_the_offer_price():
    negotiator = TuttieNegotiator(ScriptedPool([agreement(999)]), TUTTIE, load_signing_key(TUTTIE))
    outcome = asyncio.run(negotiator.negotiate(RHEINBLICK, signed_offer(), Context()))
    assert outcome.status == "refused"


@pytest.mark.parametrize("changes", [
    {"offer_id": "of-hotel-rheinblick-2"},
    {"request_id": "rq-other"},
    {"date": "2026-11-15"},
    {"room_type": "single"},
    {"rate": "flexible"},
    {"includes": ["breakfast"]},
])
def test_an_agreement_with_other_terms_than_the_offer_is_refused(changes):
    outcome = negotiate([agreement(162, **changes)], limit=180)
    assert outcome.status == "refused" and "does not match the offer" in outcome.reason


@pytest.mark.parametrize("price", [float("nan"), float("inf"), 0, -50, True, "162", None])
def test_an_agreement_at_a_price_that_is_not_a_real_price_is_refused(price):
    """Red team R9: a signed agreement at NaN, 0, -50 or true was accepted as agreed."""
    outcome = negotiate([agreement(price)], limit=180)
    assert outcome.status == "refused" and outcome.agreement is None and outcome.price_chf is None


@pytest.mark.parametrize("changes", [{"round": 0}, {"valid_until": "soon"}, {"item": ""}, {"unknown": 1}])
def test_an_agreement_that_is_not_a_valid_agreement_is_refused(changes):
    outcome = negotiate([agreement(162, **changes)], limit=180)
    assert outcome.status == "refused" and outcome.agreement is None


@pytest.mark.parametrize("price", [float("nan"), -5, True, "150"])
def test_a_counter_without_a_real_price_ends_the_negotiation(price):
    outcome = negotiate([counter(price)], limit=180)
    assert outcome.status == "refused" and outcome.agreement is None
