"""Tuttie's turn survives empty input, failing tools and LLM errors, and stays usable after them."""

import asyncio
import json
import os

import httpx

os.environ.setdefault("OPENAI_API_KEY", "test")

from assistant.agent import Assistant  # noqa: E402
from assistant.approvals import ApprovalBook  # noqa: E402
from assistant.events import EventBus  # noqa: E402
from assistant.tools import Toolbox  # noqa: E402


class ScriptedLLM:
    """Plays back replies; an Exception in the script is raised instead. Records what it was sent."""

    def __init__(self, script):
        self.script = list(script)
        self.sent = []

    async def complete(self, messages, tools, tool_choice=None):
        self.sent.append(messages)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def call(name, args=None, call_id="c1"):
    return {"role": "assistant", "content": None, "provider_items": [],
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args or {})}}]}


def answer(text):
    return {"role": "assistant", "content": f"{text}\nMood: happy", "provider_items": []}


def make(script):
    llm, bus = ScriptedLLM(script), EventBus()
    return Assistant(llm, Toolbox(httpx.AsyncClient(), "http://registry", bus, ApprovalBook()), bus), llm, bus


def tool_ids_without_result(messages):
    """Tool calls that have no tool result anywhere after them (the LLM APIs refuse such a chat)."""
    results = {m["tool_call_id"] for m in messages if m["role"] == "tool"}
    return [c["id"] for m in messages for c in m.get("tool_calls") or [] if c["id"] not in results]


def test_empty_input_is_answered_without_the_llm():
    assistant, llm, bus = make([])
    for text in ("", "   ", "\n"):
        assert asyncio.run(assistant.chat(text))
    assert llm.sent == []
    assert all(m["role"] != "user" for m in assistant.messages)
    assert bus.history[-1]["kind"] == "answer"


def test_llm_error_after_a_tool_call_answers_and_keeps_the_chat_valid():
    error = RuntimeError("provider down")
    assistant, llm, bus = make([call("end_conversation"), error, answer("Hello again")])
    text = asyncio.run(assistant.chat("bye"))
    assert "try again" in text
    assert bus.history[-1]["kind"] == "answer" and bus.history[-1]["status"] == "broken"
    assert tool_ids_without_result(assistant.messages) == []
    assert asyncio.run(assistant.chat("hi")) == "Hello again"
    assert tool_ids_without_result(llm.sent[-1]) == []


def test_a_crashing_tool_becomes_an_error_for_the_llm():
    assistant, llm, bus = make([call("recall_context"), answer("ok")])

    async def broken():
        raise KeyError("calendar")
    assistant.toolbox.recall_context = broken
    assert asyncio.run(assistant.chat("I want to book something")) == "ok"
    result = json.loads(next(m for m in assistant.messages if m["role"] == "tool")["content"])
    assert "recall_context failed" in result["error"]


def test_a_cancelled_turn_leaves_no_open_tool_call():
    assistant, llm, bus = make([call("recall_context"), answer("fine")])

    async def hang():
        await asyncio.sleep(60)

    assistant.toolbox.recall_context = hang

    async def run():
        task = asyncio.create_task(assistant.chat("I want to book something"))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return await assistant.chat("hi")
    assert asyncio.run(run()) == "fine"
    assert tool_ids_without_result(llm.sent[-1]) == []


def test_a_refused_llm_call_ends_the_turn_with_a_friendly_answer():
    import anthropic
    response = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    refused = anthropic.BadRequestError("usage limits reached", response=response, body=None)
    assistant, llm, bus = make([refused, answer("Back again")])
    assert "try again" in asyncio.run(assistant.chat("I want to book something"))
    assert bus.history[-1]["kind"] == "answer" and bus.history[-1]["detail"]["mood"] == "sorry"
    assert asyncio.run(assistant.chat("hello?")) == "Back again"
