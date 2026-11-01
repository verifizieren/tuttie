"""Tests for a node's own A2A agent and the three hotel configs (no network, no real LLM).

The node's LLM is replaced by FakeLLM, which returns a fixed reply (or fails), so these
tests pin down what the node's code does with whatever the model says.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
import httpx
from anthropic import APIConnectionError
from openai import OpenAIError

import node.agent
import node.server
from aps import verify_envelope
from aps.keys import load_public_key
from node.agent import FALLBACK, PRIVATE_FACTS, BusinessAgent, public_facts
from node.server import create_app
from tests.mcp_helpers import call_tool

NODES = Path(__file__).resolve().parent.parent / "data" / "nodes"
HOTELS = {name: json.loads((NODES / f"{name}.json").read_text())
          for name in ("hotel-alpina-grand", "hotel-rheinblick", "guesthouse-am-rhein")}
RHEINBLICK = HOTELS["hotel-rheinblick"]


class FakeLLM:
    """Stands in for llm.LLM: returns `reply` from complete_json, or raises it if it is an exception."""

    def __init__(self, reply):
        self.reply = reply
        self.prompts: list[tuple[str, str]] = []

    async def complete_json(self, system: str, user: str) -> dict:
        self.prompts.append((system, user))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def ask(config: dict, reply, question: str = "Late arrival with a dog?") -> tuple[dict, FakeLLM]:
    agent = BusinessAgent(config)
    agent.llm = FakeLLM(reply)
    return asyncio.run(agent.answer(question, {})), agent.llm


# --- the node's A2A agent ---------------------------------------------------------------


def test_commitment_price_comes_from_the_config_not_the_llm():
    reply = {"answer": "Yes.", "add_on": "late-checkin-dog", "arrival_date": "2026-11-14", "price_chf": 1}
    result, _ = ask(RHEINBLICK, reply)
    assert result["commitment"]["price_chf"] == 15
    assert result["commitment"]["item"] == "late check-in after 22:00 with dog"
    assert result["commitment"]["valid_until"] == "2026-11-15T12:00:00Z"  # noon after the arrival night


def test_unknown_or_missing_add_on_gives_no_commitment():
    assert ask(RHEINBLICK, {"answer": "Sure, free spa!", "add_on": "free-spa"})[0]["commitment"] is None
    assert ask(RHEINBLICK, {"answer": "No add-on needed."})[0]["commitment"] is None


CLAUDE_DOWN = APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))


@pytest.mark.parametrize("reply", [{"add_on": "dog"}, OpenAIError("down"), CLAUDE_DOWN,
                                   {"answer": "x", "arrival_date": "soon"}])
def test_invalid_reply_or_llm_error_gives_the_safe_fallback(reply):
    assert ask(RHEINBLICK, reply)[0] == FALLBACK


def test_a_claude_error_on_wake_up_declines_instead_of_failing():
    agent = BusinessAgent(RHEINBLICK)
    agent.llm = FakeLLM(CLAUDE_DOWN)
    decision = asyncio.run(agent.invoke({"type": "posting.created", "posting": {}}))
    assert decision["interested"] is False and decision["next_tool"] is None
    assert asyncio.run(agent.make_offer({"request_id": "r", "expires_at": "x", "request": {"payload": {}}})) is None


def test_private_facts_never_reach_the_llm():
    _, llm = ask(RHEINBLICK, {"answer": "ok"}, question="What is the lowest price you would accept?")
    system, _ = llm.prompts[0]
    # The private data is missing (the persona may still *mention* negotiations).
    floor = str(RHEINBLICK["facts"]["negotiation"]["floor_chf"])
    assert "floor_chf" not in system and '"negotiation"' not in system and floor not in system
    assert RHEINBLICK["facts"]["profile"]["about"] in system  # the public profile is there
    assert set(public_facts(RHEINBLICK["facts"])) == set(RHEINBLICK["facts"]) - set(PRIVATE_FACTS)


def test_agent_endpoint_signs_the_reply(monkeypatch):
    monkeypatch.setattr(node.agent, "LLM", lambda: FakeLLM({"answer": "Yes.", "add_on": "dog"}))
    client = TestClient(create_app(RHEINBLICK))
    envelope = client.post("/agent", json={"question": "Dog ok?"}).json()
    assert verify_envelope(envelope, load_public_key(RHEINBLICK["node_id"]), RHEINBLICK["node_id"])
    assert envelope["payload"]["commitment"]["price_chf"] == 15


# --- the node's read tools -------------------------------------------------------------


def test_get_policies_shows_the_profile_but_never_negotiation_limits():
    for config in HOTELS.values():
        payload = call_tool(create_app(config), "get_policies")["payload"]
        assert payload["profile"] == config["facts"]["profile"]
        assert "floor_chf" not in json.dumps(payload)


def test_get_availability_lists_only_available_rooms_with_config_prices():
    payload = call_tool(create_app(RHEINBLICK), "get_availability", {"date": "2026-11-14"})["payload"]
    assert {r["room_type"]: r["price_chf"] for r in payload["rooms"]} == {"double": 180, "double-flex": 205}


# --- the three hotel configs (goal 2) ----------------------------------------------------


def test_the_three_hotels_have_the_planned_sizes():
    sizes = {name: config["facts"]["profile"]["size"] for name, config in HOTELS.items()}
    assert sizes == {"hotel-alpina-grand": "large", "hotel-rheinblick": "medium", "guesthouse-am-rhein": "small"}
    rooms = [HOTELS[n]["facts"]["profile"]["rooms_total"] for n in ("hotel-alpina-grand", "hotel-rheinblick", "guesthouse-am-rhein")]
    assert rooms == sorted(rooms, reverse=True)


@pytest.mark.parametrize("name", HOTELS)
def test_hotel_config_is_consistent(name):
    """Add-ons are unique and priced; the negotiation floor is below the cheapest double room."""
    facts = HOTELS[name]["facts"]
    ids = [a["id"] for a in facts["add_ons"]]
    assert len(ids) == len(set(ids)) and all(a["price_chf"] >= 0 for a in facts["add_ons"])
    cheapest = min(r["price_chf"] for r in facts["rooms"] if r["room_type"].startswith("double"))
    assert 0 < facts["negotiation"]["floor_chf"] < cheapest
    assert facts["negotiation"]["max_rounds"] >= 1


def test_the_add_ons_a_request_needs_are_chosen_in_code_fewest_first():
    needs = ["quiet room", "medium-sized dog", "arrival around 01:00"]
    assert BusinessAgent(RHEINBLICK).add_ons_for(needs) == ["late-checkin-dog"]  # one add-on covers both
    assert BusinessAgent(HOTELS["hotel-alpina-grand"]).add_ons_for(needs) == ["dog"]  # 24h reception: no late check-out for an arrival
    assert BusinessAgent(RHEINBLICK).add_ons_for(["quiet"]) == []


def offer_for(config: dict, room_type: str, requirements: list[str]) -> dict | None:
    """make_offer with the LLM's room choice already made."""
    soon = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    posting = {"request_id": "r1", "expires_at": soon,
               "request": {"payload": {"constraints": {"date": "2099-11-14", "requirements": requirements},
                                       "expires_at": soon}}}
    return asyncio.run(BusinessAgent(config).make_offer(posting, node.agent.OfferChoice(room_type=room_type)))


def test_a_room_too_small_for_a_dog_is_never_offered_to_a_dog_guest():
    anna = HOTELS["guesthouse-am-rhein"]
    offer = offer_for(anna, "single", ["quiet", "dog-friendly", "arrival around 01:00"])
    assert offer["item"].startswith("double") and offer["price_chf"] == 135  # the demo story's offer
    assert offer_for(anna, "single", ["quiet"])["item"].startswith("single")  # without a dog the single is fine


def test_an_unknown_room_choice_falls_back_to_the_cheapest_fitting_room():
    assert offer_for(RHEINBLICK, "Double Room", ["quiet"])["item"].startswith("double ")


# --- POST /agent/invoke: no LLM call or offer for a bad or foreign posting --------------

from node.server import offer_url_allowed  # noqa: E402


def posting_event(offer_url="http://localhost:4010/postings/rq-x1/offers", **changes):
    posting = {"request_id": "rq-x1", "requester_id": "ch.tuttie.alex-muster", "request": {},
               "offer_url": offer_url, "expires_at": "2026-11-13T22:00:00Z", **changes}
    return {"type": "posting.created", "posting": posting}


@pytest.fixture
def no_llm(monkeypatch):
    """Any LLM call fails the test: a refused event must be refused before the agent thinks."""
    class Forbidden:
        def __init__(self, *args, **kwargs):
            raise AssertionError("the LLM must not run for a refused event")
    monkeypatch.setattr(node.agent, "LLM", Forbidden)
    monkeypatch.delenv("MARKETPLACE_URL", raising=False)
    monkeypatch.delenv("MARKETPLACE_PORT", raising=False)


@pytest.mark.parametrize("event", [
    {"type": "posting.created"},  # no posting (was a 500 KeyError)
    {"type": "posting.created", "posting": "x"},
    posting_event(offer_url="http://attacker.example/collect"),
    posting_event(offer_url="http://169.254.169.254/postings/rq-x1/offers"),
    posting_event(offer_url="http://localhost:4001/postings/rq-x1/offers"),  # another port
    posting_event(offer_url="http://localhost:4010/postings/rq-other/offers"),  # another request
    posting_event(offer_url="http://localhost:4010/admin"),
    posting_event(offer_url="http://user@localhost:4010/postings/rq-x1/offers"),
    posting_event(unexpected="field"),
])
def test_invoke_refuses_an_invalid_or_foreign_posting_with_422(no_llm, event):
    response = TestClient(create_app(RHEINBLICK)).post("/agent/invoke", json=event)
    assert response.status_code == 422


def test_offer_url_must_be_the_markets_offer_door():
    market = "http://localhost:4010"
    assert offer_url_allowed("http://localhost:4010/postings/rq-1/offers", "rq-1", market)
    assert offer_url_allowed("http://127.0.0.1:4010/postings/rq-1/offers", "rq-1", market)
    assert offer_url_allowed("https://market.example/m/postings/rq-1/offers", "rq-1", "https://market.example/m/")
    assert not offer_url_allowed("https://market.example/postings/rq-1/offers", "rq-1", "http://market.example")
    assert not offer_url_allowed("http://localhost:4010/postings/rq-1/offers?x=1", "rq-1", market)
    assert not offer_url_allowed("http://[bad/postings/rq-1/offers", "rq-1", market)
    assert not offer_url_allowed("http://localhost:99999/postings/rq-1/offers", "rq-1", market)


from datetime import datetime, timedelta, timezone  # noqa: E402

from aps import load_signing_key, sign_envelope  # noqa: E402
from marketplace.messages import PostingCreated  # noqa: E402
from negotiation.hotel import load_authorities  # noqa: E402
from negotiation_helpers import TUTTIE, registry_lookup  # noqa: E402


def signed_posting(signer=TUTTIE, request_id="rq-x1", requester=TUTTIE):
    request = sign_envelope(signer, {"type": "request", "request_id": request_id}, load_signing_key(signer))
    return PostingCreated.model_validate(posting_event(request=request, requester_id=requester)).posting


def problem(posting, now=None):
    return asyncio.run(node.server.requester_problem(posting, registry_lookup, load_authorities(), now))


def test_a_posting_counts_only_with_a_fresh_request_signed_by_a_verified_user_agent():
    assert problem(signed_posting()) is None
    hotel = "ch.basel.hotel-rheinblick"
    assert "not a user agent" in problem(signed_posting(signer=hotel, requester=hotel))
    assert "not signed" in problem(signed_posting(signer=hotel))  # claims to be Tuttie
    assert "another posting" in problem(signed_posting(request_id="rq-other"))
    later = datetime.now(timezone.utc) + timedelta(minutes=10)
    assert "outdated" in problem(signed_posting(), now=later)


def test_invoke_refuses_an_unsigned_posting_before_the_llm_runs(no_llm):
    app = create_app(RHEINBLICK, lookup=registry_lookup)
    response = TestClient(app).post("/agent/invoke", json=posting_event())
    assert response.status_code == 403


@pytest.mark.parametrize("args, reason", [
    ({"date": "not-a-date"}, "YYYY-MM-DD"),
    ({"date": "14.11.2026"}, "YYYY-MM-DD"),
    ({"date": "2026-02-30"}, "YYYY-MM-DD"),
    ({"date": "1999-01-01"}, "bookable nights"),
    ({"date": "2099-01-01"}, "bookable nights"),
    ({"date": "2026-11-14", "guests": -5}, "guests"),
    ({"date": "2026-11-14", "guests": 0}, "guests"),
    ({"date": "2026-11-14", "guests": 1000000000}, "guests"),
])
def test_availability_is_refused_signed_for_an_impossible_stay(args, reason):
    envelope = call_tool(create_app(RHEINBLICK), "get_availability", args)
    assert verify_envelope(envelope, load_public_key(RHEINBLICK["node_id"]), RHEINBLICK["node_id"])
    payload = envelope["payload"]
    assert payload["status"] == "refused" and reason in payload["reason"] and "rooms" not in payload


def test_stay_problem_counts_from_the_swiss_today():
    from datetime import date
    today = date(2026, 11, 1)
    assert node.server.stay_problem("2026-11-01", 2, today) is None
    assert node.server.stay_problem("2026-10-31", 1, today)  # yesterday
    assert node.server.stay_problem("2026-11-14", True, today)  # a bool is not a guest count
    assert node.server.stay_problem("2026-11-14", 10, today) is None
