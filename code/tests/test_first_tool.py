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
