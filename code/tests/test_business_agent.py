"""Tests for the company agents: one agent object for every hotel, persona, tools, wake-ups.

The LLM is replaced by a stub, so these run offline.
"""

import asyncio
import json
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
PERSONA_KEYS = {"name", "role", "business_size", "about", "tone", "priorities", "boundaries"}


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
    assert spec["persona"]["business_size"] == size
    assert set(spec["tools"]) <= set(TOOLS)


def test_hotel_sizes_differ_in_rooms():
    rooms = {size: config(name)["facts"]["rooms_total"] for size, name in HOTELS.items()}
    assert rooms["large"] > rooms["medium"] > rooms["small"]


def test_agents_know_planned_tools_and_their_status():
    agent = BusinessAgent(config(HOTELS["large"]))
    text = agent.persona_text()
    assert "make_offer [planned]" in text and "book [available]" in text
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


def test_wake_up_reports_a_planned_next_tool_as_not_available():
    agent = agent_with(HOTELS["large"], {"interested": True, "reason": "We have rooms.", "next_tool": "make_offer"})
    result = asyncio.run(agent.invoke({"type": "posting.created", "posting": {"category": "hotel"}}))
    assert result["interested"] is True and result["next_tool"] == "make_offer"
    assert TOOLS["make_offer"]["status"] == PLANNED and result["next_tool_available"] is False
    assert "You are Lena" in agent.llm.system


def test_wake_up_drops_a_tool_the_agent_does_not_have():
    agent = agent_with(HOTELS["small"], {"interested": False, "reason": "Too far.", "next_tool": "teleport"})
    result = asyncio.run(agent.invoke({"type": "posting.created"}))
    assert result["next_tool"] is None and result["next_tool_available"] is False
