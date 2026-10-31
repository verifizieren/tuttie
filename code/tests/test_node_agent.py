"""Tests for a node's own A2A agent and the three hotel configs (no network, no real LLM).

The node's LLM is replaced by FakeLLM, which returns a fixed reply (or fails), so these
tests pin down what the node's code does with whatever the model says.
"""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
import httpx
from anthropic import APIConnectionError
from openai import OpenAIError

import node.agent
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
    posting = {"request_id": "r1", "expires_at": "2026-11-14T12:00:00Z",
               "request": {"payload": {"constraints": {"date": "2026-11-14", "requirements": requirements}}}}
    return asyncio.run(BusinessAgent(config).make_offer(posting, node.agent.OfferChoice(room_type=room_type)))


def test_a_room_too_small_for_a_dog_is_never_offered_to_a_dog_guest():
    anna = HOTELS["guesthouse-am-rhein"]
    offer = offer_for(anna, "single", ["quiet", "dog-friendly", "arrival around 01:00"])
    assert offer["item"].startswith("double") and offer["price_chf"] == 135  # the demo story's offer
    assert offer_for(anna, "single", ["quiet"])["item"].startswith("single")  # without a dog the single is fine


def test_an_unknown_room_choice_falls_back_to_the_cheapest_fitting_room():
    assert offer_for(RHEINBLICK, "Double Room", ["quiet"])["item"].startswith("double ")
