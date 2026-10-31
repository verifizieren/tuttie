"""Tests for the user's context (assistant/context.py): read source by source, privacy classes kept."""

import asyncio

from assistant.context import DONE, SOURCES, UserContext
from assistant.events import EventBus


def test_recall_reads_every_source_then_says_what_it_found():
    bus = EventBus()
    context = asyncio.run(UserContext(pace_s=0).recall(bus))
    assert [e["detail"]["source"] for e in bus.history[:-1]] == [source for source, _ in SOURCES]
    assert [e["summary"] for e in bus.history[:2]] == ["Checking location", "Checking messages"]
    assert bus.history[-1]["detail"]["phase"] == "found" and bus.history[-1]["summary"] == DONE
    assert any("00:52" in item["what"] for item in context["calendar"])


def test_the_budget_is_private_and_never_in_what_the_wallet_shows():
    bus = EventBus()
    context = asyncio.run(UserContext(pace_s=0).recall(bus))
    budget = [p for p in context["preferences"] if "CHF 160" in p["what"]]
    assert budget and budget[0]["visibility"] == "private"
    assert all("160" not in e["summary"] for e in bus.history)
