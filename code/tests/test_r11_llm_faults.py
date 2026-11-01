"""r11: Tuttie's own LLM (Anthropic) failing on the 1st, 2nd or 3rd round of a turn.

The real ClaudeLLM runs against a mocked Anthropic HTTP API (no network): RateLimitError (429),
APIStatusError 500 (InternalServerError) and APITimeoutError. Checks: the next request is a valid
Messages API chat (every tool_use answered by a tool_result in the next message), what the user
gets told, and that a failure after the work was done does not tell the user to "try again".
"""

import asyncio
import json

import anthropic
import httpx
import httpx2
import pytest

import llm as llm_module
from assistant.agent import Assistant
from assistant.approvals import ApprovalBook
from assistant.events import EventBus
from assistant.tools import Toolbox


def tool_use(name, args, call_id):
    return {"type": "tool_use", "id": call_id, "name": name, "input": args}


def reply(content, stop="end_turn"):
    return {"id": "msg_x", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
            "content": content, "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1}}


class FakeAnthropic:
    """Plays HTTP answers in order: a dict = 200 JSON reply, an int = that status, "timeout" =
    a read timeout. Records every request body."""

    def __init__(self, script):
        self.script = list(script)
        self.bodies = []

    def handler(self, request):
        self.bodies.append(json.loads(request.content))
        step = self.script.pop(0)
        if step == "timeout":
            raise httpx2.ReadTimeout("slow", request=request)
        if isinstance(step, int):
            return httpx2.Response(step, headers={"retry-after-ms": "1", "x-should-retry": "false"},
                                  json={"type": "error", "error": {"type": "rate_limit_error"
                                        if step == 429 else "api_error", "message": "boom"}})
        return httpx2.Response(200, json=step)


def claude(fake):
    model = llm_module.ClaudeLLM("claude-haiku-5-5")
    model.client = anthropic.AsyncAnthropic(api_key="test", max_retries=0, timeout=1,
                                            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(fake.handler)))
    return model


def make(fake):
    bus = EventBus()
    toolbox = Toolbox(httpx.AsyncClient(), "http://registry", bus, ApprovalBook())

    async def recall():
        return {"calendar": []}
    toolbox.recall_context = recall
    return Assistant(claude(fake), toolbox, bus), bus


def valid_chat(body) -> list[str]:
    """Problems that make the Messages API refuse this request body."""
    problems, messages = [], body["messages"]
    if messages and messages[0]["role"] != "user":
        problems.append("first message is not the user's")
    for n, m in enumerate(messages):
        uses = [b["id"] for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_use"] \
            if isinstance(m["content"], list) else []
        if not uses:
            continue
        nxt = messages[n + 1] if n + 1 < len(messages) else None
        results = [b.get("tool_use_id") for b in (nxt or {}).get("content", [])
                   if isinstance(b, dict) and b.get("type") == "tool_result"] if nxt and isinstance(nxt["content"], list) else []
        missing = [u for u in uses if u not in results]
        if missing:
            problems.append(f"tool_use {missing} without a tool_result right after")
    return problems


ERRORS = [429, 500, "timeout"]
ROUNDS = [  # what the model does before the failing round
    [],
    [reply([tool_use("recall_context", {}, "tu_1")], "tool_use")],
    [reply([tool_use("recall_context", {}, "tu_1")], "tool_use"),
     reply([tool_use("recall_context", {}, "tu_2"), tool_use("current_deals", {}, "tu_3")], "tool_use")],
]


@pytest.mark.parametrize("error", ERRORS)
@pytest.mark.parametrize("before", range(3))
def test_a_failing_round_keeps_the_chat_valid_and_answers_calmly(error, before):
    fake = FakeAnthropic([*ROUNDS[before], error, reply([{"type": "text", "text": "Hi again.\nMood: happy"}])])
    assistant, bus = make(fake)
    first = asyncio.run(assistant.chat("I want to book something"))
    assert "try again" in first and bus.history[-1]["status"] == "broken"
    assert asyncio.run(assistant.chat("hello?")) == "Hi again."
    assert valid_chat(fake.bodies[-1]) == []


# ---------- failures after the work was done ----------

class ScriptedLLM:
    def __init__(self, script):
        self.script = list(script)

    async def complete(self, messages, tools, tool_choice=None):
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


def call(name, args=None, call_id="c1"):
    return {"role": "assistant", "content": None, "provider_items": [],
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args or {})}}]}


def rate_limited():
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    return anthropic.RateLimitError("rate limited", response=response, body=None)


def scripted(script, tool, result):
    bus = EventBus()
    toolbox = Toolbox(httpx.AsyncClient(), "http://registry", bus, ApprovalBook())

    async def done(**_):
        if tool == "post_request":
            bus.emit("marketplace", "verified", "3 hotels to choose from", detail={"phase": "cards", "cards": [{}] * 3})
        else:
            bus.emit("a2t", "verified", "book: confirmed BK-1, CHF 128")
        return result
    setattr(toolbox, tool, done)
    return Assistant(ScriptedLLM(script), toolbox, bus), bus


def test_rate_limit_right_after_the_cards_does_not_tell_the_user_to_search_again():
    """HOLE: the hotel burst (5 hotel LLM calls + negotiation) ends just before Tuttie's summary
    round, which is when a shared-key 429 lands. The cards are on screen, yet the user hears
    "I can't think right now, please try again in a moment" (and voice adds the swipe hand-off),
    so they ask again and the whole 45 s search with new postings runs a second time."""
    cards = {"cards": [{"name": "Gästehaus am Rhein"}, {"name": "Hotel Rheinblick"}, {"name": "Alpina"}]}
    assistant, bus = scripted([call("post_request", {"date": "2026-11-14"}), rate_limited()], "post_request", cards)
    answer = asyncio.run(assistant.chat("Find me a quiet hotel in Basel for tonight"))
    assert "try again" not in answer, answer


def test_rate_limit_right_after_a_confirmed_booking_does_not_say_try_again():
    """HOLE: the user approved with Face ID and the hotel signed the booking, then the summary
    round fails: Tuttie says "I can't think right now, please try again in a moment" instead of
    "booked", inviting a second booking attempt."""
    booked = {"status": "confirmed", "booking_id": "BK-1", "total_chf": 128, "node_id": "ch.basel.gaestehaus-am-rhein"}
    assistant, bus = scripted([call("book", {"node_id": "x", "use_agreement": True}), rate_limited()], "book", booked)
    answer = asyncio.run(assistant.chat("Book Gästehaus am Rhein", first_tool="book"))
    assert "try again" not in answer and "book" in answer.lower(), answer
