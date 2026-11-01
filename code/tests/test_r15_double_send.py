"""Round 15: the same message sent twice at once (two tabs, a double tap) is one turn: a second
"yes" must not answer a question the user has not seen yet (atk11: a second approval)."""

import asyncio
import os

import httpx

os.environ.setdefault("OPENAI_API_KEY", "test")

from assistant.conversations import Conversation  # noqa: E402


class SlowLLM:
    """Answers each turn after a short pause, counting the turns it was asked."""

    def __init__(self):
        self.calls = 0

    async def complete(self, messages, tools, tool_choice=None):
        self.calls += 1
        await asyncio.sleep(0.2)
        return {"role": "assistant", "content": "Done.\nMood: happy", "provider_items": []}


def test_the_same_message_sent_twice_at_once_is_one_turn():
    async def run():
        llm = SlowLLM()
        conv = Conversation(httpx.AsyncClient(), "http://registry", llm)
        first = conv.start("Yes, book that one.")
        second = conv.start("Yes, book that one.")
        await asyncio.sleep(0.6)
        return first, second, llm.calls

    first, second, calls = asyncio.run(run())
    assert first == second and calls == 1


def test_a_different_or_later_message_is_its_own_turn():
    async def run():
        llm = SlowLLM()
        conv = Conversation(httpx.AsyncClient(), "http://registry", llm)
        a = conv.start("Yes, book that one.")
        b = conv.start("And the weather?")
        await asyncio.sleep(0.8)
        c = conv.start("Yes, book that one.")  # the first one has finished: a new turn
        await asyncio.sleep(0.4)
        return {a, b, c}, llm.calls

    turns, calls = asyncio.run(run())
    assert len(turns) == 3 and calls == 3
