"""Round 9: Tuttie's answers say times as people do on screen too, the same as its voice
(the model copied "00:52" and "02:00" from calendar and policy data)."""

import asyncio
import os

import httpx

os.environ.setdefault("OPENAI_API_KEY", "test")

from assistant.agent import Assistant  # noqa: E402
from assistant.approvals import ApprovalBook  # noqa: E402
from assistant.events import EventBus  # noqa: E402
from assistant.tools import Toolbox  # noqa: E402
from speech import said_times  # noqa: E402


class OneAnswer:
    """An LLM that answers once."""

    def __init__(self, text):
        self.text = text

    async def complete(self, messages, tools, tool_choice=None):
        return {"role": "assistant", "content": f"{self.text}\nMood: happy", "provider_items": []}


def test_an_answer_with_24_hour_times_is_shown_and_stored_as_said():
    bus = EventBus()
    assistant = Assistant(OneAnswer("Your train arrives at 00:52 and check-in runs until 02:00."),
                          Toolbox(httpx.AsyncClient(), "http://registry", bus, ApprovalBook()), bus)
    answer = asyncio.run(assistant.chat("When do I arrive?"))
    assert answer == "Your train arrives at 12:52 am and check-in runs until 2 am."
    assert bus.history[-1]["summary"] == answer


def test_durations_and_12_hour_times_stay():
    assert said_times("The ride takes 01:15.") == "The ride takes 01:15."
    assert said_times("Dinner at 8:30 pm.") == "Dinner at 8:30 pm."
