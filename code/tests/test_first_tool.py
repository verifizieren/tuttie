"""Tests that the wallet can fix Tuttie's first step for a message (after swiping: negotiate)."""

import asyncio
import os

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test")  # the app builds an LLM client; these tests never call it

from assistant.agent import Assistant  # noqa: E402
from assistant.app import app  # noqa: E402
from assistant.approvals import ApprovalBook  # noqa: E402
from assistant.events import EventBus  # noqa: E402
from assistant.tools import Toolbox  # noqa: E402


class RecordingLLM:
    """Answers at once and remembers which tool each turn was forced to."""

    def __init__(self):
        self.choices = []

    async def complete(self, messages, tools, tool_choice=None):
        self.choices.append(tool_choice)
        return {"role": "assistant", "content": "Done.\nMood: happy", "provider_items": []}


def test_the_first_tool_is_forced_for_that_message_only():
    llm, bus = RecordingLLM(), EventBus()
    assistant = Assistant(llm, Toolbox(httpx.AsyncClient(), "http://registry", bus, ApprovalBook()), bus)
    asyncio.run(assistant.chat("I liked these", first_tool="negotiate"))
    asyncio.run(assistant.chat("Thanks!"))
    assert llm.choices == ["negotiate", None]


def test_chat_accepts_only_known_first_steps():
    with TestClient(app) as client:
        assert client.post("/chat", json={"message": "hi", "first_tool": "pay"}).status_code == 422


def test_card_synonyms_dispatch_without_an_llm_guess():
    from assistant.card_commands import card_choice
    llm, bus = RecordingLLM(), EventBus()
    toolbox = Toolbox(httpx.AsyncClient(), "http://registry", bus, ApprovalBook())
    assistant = Assistant(llm, toolbox, bus)
    bus.emit("marketplace", "verified", "Cards", detail={"phase": "cards", "cards": [{}]})
    for phrase, verdict in [("Reject!", "pass"), ("skip this one", "pass"), ("Gefällt mir.", "like"), ("I like this one", "like")]:
        asyncio.run(assistant.chat(phrase))
        assert [e for e in bus.history if e["kind"] == "wallet"][-1]["detail"]["verdict"] == verdict
    assert llm.choices == []
    for phrase in ("yes", "no", "accept", "don't skip this one", "reject the payment"):
        assert card_choice(phrase) is None


def test_every_followup_receives_current_signed_deal_facts():
    class FactsLLM(RecordingLLM):
        async def complete(self, messages, tools, tool_choice=None):
            import json
            facts = json.loads(messages[2]["content"].split("\n", 1)[1])
            assert facts["deals"][0]["agreement"]["price_chf"] == 209
            assert facts["deals"][0]["offered_chf"] == 220
            return await super().complete(messages, tools, tool_choice)
    bus = EventBus()
    toolbox = Toolbox(httpx.AsyncClient(), "http://registry", bus, ApprovalBook())
    assistant = Assistant(FactsLLM(), toolbox, bus)
    toolbox.market.last_offers = [{"node_id": "hotel", "name": "Hotel", "offer": {"price_chf": 220}}]
    toolbox.agreements["hotel"] = {"payload": {"type": "agreement", "price_chf": 209}}
    asyncio.run(assistant.chat("Didn't you agree on 209?"))
    assert len([m for m in assistant.messages if m["role"] == "system"]) == 1
