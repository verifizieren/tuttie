"""Round 6: a line said while the phone asks for an approval is answered at once, not queued
behind the waiting turn (in voice mode Tuttie stayed silent for up to 5 minutes)."""

import asyncio
import json
import os

import httpx

os.environ.setdefault("OPENAI_API_KEY", "test")

from assistant.agent import WAIT_FOR_PHONE  # noqa: E402
from assistant.conversations import Conversation  # noqa: E402


class ScriptedLLM:
    """Plays back replies in order (shared by all turns of a conversation)."""

    def __init__(self, script):
        self.script = list(script)

    async def complete(self, messages, tools, tool_choice=None):
        return self.script.pop(0)


def call(name, call_id="c1"):
    return {"role": "assistant", "content": None, "provider_items": [],
            "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}]}


def answer(text):
    return {"role": "assistant", "content": f"{text}\nMood: happy", "provider_items": []}


def waiting_conversation(script):
    """A conversation whose first turn waits on the phone like Toolbox's book does."""
    conv = Conversation(httpx.AsyncClient(), "http://registry", ScriptedLLM([call("book"), *script]))

    async def dispatch(name, args):
        record = {"node_id": "ch.basel.hotel-rheinblick", "name": "Hotel Rheinblick"}
        approval = conv.approvals.create("book", record, 128, "Book Hotel Rheinblick = CHF 128", [])
        decision = await conv.approvals.wait(approval["id"])
        return {"declined": decision["decision"] != "approved"}

    conv.assistant.toolbox.dispatch = dispatch
    return conv


async def pending(conv):
    for _ in range(100):
        await asyncio.sleep(0.01)
        if conv.approvals.pending:
            return
    raise AssertionError("setup: the booking should be waiting for the phone")


def test_a_line_said_while_the_phone_asks_gets_an_answer_at_once_and_decides_nothing():
    async def run():
        conv = waiting_conversation([answer("Declined, no problem.")])
        conv.start("I want to book something", source="voice")
        await pending(conv)
        conv.start("ok thanks, bye", source="voice")
        await asyncio.sleep(0.2)
        answers = [e for e in conv.bus.history if e["kind"] == "answer" and e["turn"] == "t2"]
        assert [a["summary"] for a in answers] == [WAIT_FOR_PHONE]
        assert conv.approvals.pending, "the approval is still the phone's to decide"
        assert all("thanks, bye" not in json.dumps(m) for m in conv.assistant.messages), "nothing queued for later"
        approval_id = next(iter(conv.approvals.pending))
        conv.approvals.decide(approval_id, "declined")
        await asyncio.sleep(0.2)
        assert [e["summary"] for e in conv.bus.history if e["kind"] == "answer" and e["turn"] == "t1"] == \
            ["Declined, no problem."]
    asyncio.run(run())


def test_a_line_said_while_an_ordinary_turn_runs_still_waits_its_turn():
    """Only a pending approval answers at once; otherwise turns stay in order, as before."""
    async def run():
        conv = Conversation(httpx.AsyncClient(), "http://registry", ScriptedLLM([answer("One."), answer("Two.")]))
        conv.start("first")
        conv.start("second")
        await asyncio.sleep(0.2)
        assert [e["summary"] for e in conv.bus.history if e["kind"] == "answer"] == ["One.", "Two."]
    asyncio.run(run())
