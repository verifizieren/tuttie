"""Tests for the company agents: one agent object for every hotel, persona, tools, wake-ups.

The LLM is replaced by a stub, so these run offline.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aps import verify_envelope
from node.agent import BusinessAgent
from node.catalog import PLANNED, TOOLS, tools_for
from node.server import create_app

NODES = Path(__file__).resolve().parent.parent / "data" / "nodes"
REGISTRY = {r["node_id"]: r for r in json.loads((NODES.parent / "registry.json").read_text())}
# The three hotel agents of the first marketplace example, one per business size.
HOTELS = {"large": "hotel-alpina-grand.json", "medium": "hotel-rheinblick.json", "small": "guesthouse-am-rhein.json"}
PERSONA_KEYS = {"name", "role", "tone", "priorities", "boundaries"}


def config(name: str) -> dict:
    return json.loads((NODES / name).read_text())


class StubLLM:
    """Stands in for the LLM: returns a fixed JSON reply and records the prompt."""

    def __init__(self, reply: dict):
        self.reply, self.system = reply, None

    async def complete_json(self, system: str, user: str) -> dict:
        self.system = system
        return self.reply


def agent_with(name: str, reply: dict) -> BusinessAgent:
    agent = BusinessAgent(config(name))
    agent.llm = StubLLM(reply)
    return agent


@pytest.mark.parametrize("size, name", HOTELS.items())
def test_every_hotel_has_the_same_agent_object(size, name):
    spec = config(name)["agent"]
    assert set(spec) == {"persona", "tools", "wakes_on"}
    assert set(spec["persona"]) == PERSONA_KEYS
    assert config(name)["facts"]["profile"]["size"] == size
    assert set(spec["tools"]) <= set(TOOLS)


def test_hotel_sizes_differ_in_rooms():
    rooms = {size: config(name)["facts"]["profile"]["rooms_total"] for size, name in HOTELS.items()}
    assert rooms["large"] > rooms["medium"] > rooms["small"]


def test_agents_know_their_tools_and_their_status(monkeypatch):
    agent = BusinessAgent(config(HOTELS["large"]))
    assert "pay [available]" in agent.persona_text() and "counter_offer [available]" in agent.persona_text()
    monkeypatch.setitem(TOOLS, "pay", {**TOOLS["pay"], "status": PLANNED})  # a tool not built yet
    assert "pay [planned]" in BusinessAgent(config(HOTELS["large"])).persona_text()
    with pytest.raises(ValueError):
        tools_for(["teleport"])


def test_negotiation_limits_never_reach_a_prompt_or_the_card():
    agent = BusinessAgent(config(HOTELS["medium"]))
    assert "floor_chf" not in agent.facts_json
    card = agent.card()
    assert "boundaries" not in card["persona"] and "floor_chf" not in json.dumps(card)


def test_agent_card_is_signed_by_the_hotel():
    cfg = config(HOTELS["small"])
    envelope = TestClient(create_app(cfg)).get("/agent/card").json()
    assert verify_envelope(envelope, REGISTRY[cfg["node_id"]]["public_key"], expected_node_id=cfg["node_id"])
    assert envelope["payload"]["persona"]["name"] == "Anna"


def test_unsubscribed_event_is_ignored_without_the_llm():
    agent = BusinessAgent(config(HOTELS["large"]))  # no LLM set: it must not be needed
    result = asyncio.run(agent.invoke({"type": "something.else"}))
    assert result["ignored"] is True


def test_wake_up_reports_whether_the_next_tool_is_available(monkeypatch):
    agent = agent_with(HOTELS["large"], {"interested": True, "reason": "We have rooms.", "next_tool": "make_offer"})
    result = asyncio.run(agent.invoke({"type": "posting.created", "posting": {"category": "hotel"}}))
    assert result["interested"] is True and result["next_tool"] == "make_offer"
    assert result["next_tool_available"] is True
    assert "You are Lena" in agent.llm.system
    monkeypatch.setitem(TOOLS, "pay", {**TOOLS["pay"], "status": PLANNED})  # a tool not built yet
    planned = agent_with(HOTELS["large"], {"interested": True, "reason": "Pay!", "next_tool": "pay"})
    result = asyncio.run(planned.invoke({"type": "posting.updated"}))
    assert result["next_tool_available"] is False


def test_wake_up_drops_a_tool_the_agent_does_not_have():
    agent = agent_with(HOTELS["small"], {"interested": False, "reason": "Too far.", "next_tool": "teleport"})
    result = asyncio.run(agent.invoke({"type": "posting.created"}))
    assert result["next_tool"] is None and result["next_tool_available"] is False


SOON = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
# The posting's own expires_at is not signed: the offer's validity comes from the signed request.
POSTING = {"request_id": "rq-test1", "expires_at": "2099-12-31T23:59:59Z", "offer_url": "http://market/x",
           "request": {"payload": {"constraints": {"date": "2099-11-14", "requirements": ["dog", "late arrival"]},
                                   "expires_at": SOON}}}


def test_offer_price_comes_from_the_config_whatever_the_llm_picks():
    agent = agent_with(HOTELS["medium"], {"room_type": "double", "add_ons": ["late-checkin-dog"], "price_chf": 1})
    offer = asyncio.run(agent.make_offer(POSTING))
    assert offer["price_chf"] == 180 + 15 and offer["request_id"] == "rq-test1"
    assert offer["includes"] == ["late check-in after 22:00 with dog"]
    assert offer["item"] == "double room 2099-11-14" and offer["valid_until"] == SOON
    # The bookable terms travel as fields, so an agreement and the booking can be bound to them.
    assert (offer["room_type"], offer["date"], offer["rate"]) == ("double", "2099-11-14", "best rate, non-refundable")


def test_no_offer_for_an_invalid_choice():
    assert asyncio.run(agent_with(HOTELS["medium"], {"add_ons": []}).make_offer(POSTING)) is None


def test_an_unknown_add_on_is_dropped_and_the_hotel_still_offers():
    """The hotel told the market it will offer: an add-on id it lacks must not cost the offer."""
    offer = asyncio.run(agent_with(HOTELS["medium"], {"room_type": "double", "add_ons": ["free-spa"]})
                        .make_offer(POSTING))
    assert offer["price_chf"] == 180 + 15 and offer["includes"] == ["late check-in after 22:00 with dog"]


def test_an_unknown_room_gets_the_cheapest_real_room_instead_of_no_offer():
    offer = asyncio.run(agent_with(HOTELS["medium"], {"room_type": "penthouse"}).make_offer(POSTING))
    assert offer["item"].startswith("double ")  # Rheinblick's cheapest room, priced from the config


def test_a_new_posting_decides_and_chooses_the_offer_in_one_llm_call():
    agent = agent_with(HOTELS["medium"], {"interested": True, "reason": "Happy to.", "room_type": "double",
                                          "add_ons": ["late-checkin-dog"]})
    decision = asyncio.run(agent.invoke({"type": "posting.created", "posting": POSTING}))
    choice = decision["offer_choice"]
    assert choice.room_type == "double" and "room_type" in agent.llm.system
    agent.llm = None  # the offer needs no second call
    offer = asyncio.run(agent.make_offer(POSTING, choice))
    assert offer["price_chf"] == 180 + 15


def test_offer_validity_comes_from_the_signed_request_and_is_capped():
    """Red team R3: valid_until was the UNSIGNED posting's expires_at (e.g. 2099)."""
    from node.agent import offer_valid_until
    now = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    request = {"constraints": {"date": "2026-11-13"}, "expires_at": "2026-11-01T12:00:00Z"}
    assert offer_valid_until(request, now) == "2026-11-01T12:00:00Z"
    far = {**request, "expires_at": "2099-12-31T23:59:59Z"}
    assert offer_valid_until(far, now) == "2026-11-02T10:00:00Z"  # at most 24 h
    tonight = {"constraints": {"date": "2026-11-01"}, "expires_at": "2099-12-31T23:59:59Z"}
    assert offer_valid_until(tonight, now) == "2026-11-02T10:00:00Z"
    assert offer_valid_until({"constraints": {"date": "2026-10-31"}, "expires_at": "2099-01-01T00:00:00Z"},
                             now) == "2026-11-01T12:00:00Z"  # noon after the stay night
    assert offer_valid_until({**request, "expires_at": "2026-11-01T09:00:00Z"}, now) is None  # expired
    assert offer_valid_until({"constraints": {"date": "2026-11-13"}}, now) is None  # no signed expiry
