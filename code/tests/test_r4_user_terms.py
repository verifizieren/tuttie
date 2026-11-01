"""Real-user test, round 4: the user's own date, party size and nights win over the calendar,
the model's notes to itself never reach the answer, and post_request's bargaining is not
repeated by a second negotiate call in the same turn (fake LLMs, no network)."""

import asyncio
import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

import assistant.tools as tools
import negotiation.tuttie
from assistant.agent import SYSTEM_PROMPT, Assistant
from assistant.approvals import ApprovalBook
from assistant.events import EventBus
from assistant.tools import Toolbox, stay_error
from llm import LLM, ClaudeLLM, final_text
from negotiation.tuttie import Outcome

TODAY = date(2026, 11, 1)


@pytest.fixture(autouse=True)
def swiss_today(monkeypatch):
    monkeypatch.setattr(tools, "swiss_today", lambda: TODAY)


def toolbox() -> Toolbox:
    return Toolbox(httpx.AsyncClient(), "http://registry", EventBus(), ApprovalBook())


# 1. The user's terms win; the code refuses what it cannot do instead of changing it.

def test_the_prompt_lets_the_users_own_date_nights_and_party_size_beat_the_calendar():
    assert "The calendar only fills in what the user did not say" in SYSTEM_PROMPT
    assert "The date is the check-in date the calendar names, even" not in SYSTEM_PROMPT


@pytest.mark.parametrize("day, guests, nights, error", [
    ("2026-10-31", 1, 1, "in the past"),            # "for yesterday"
    ("2026-11-02", 0, 1, "guests must be"),
    ("2026-11-02", True, 1, "guests must be"),
    ("2026-11-02", 1, 3, "one night per booking"),  # honest instead of silently booking 1 night
    ("14 Nov", 1, 1, "YYYY-MM-DD"),
    ("2026-02-30", 1, 1, "YYYY-MM-DD"),
])
def test_stays_that_cannot_be_posted_as_asked_are_refused(day, guests, nights, error):
    assert error in stay_error(day, guests, nights)


@pytest.mark.parametrize("day", ["2026-11-01", "2026-11-02", "2026-11-14"])
def test_today_tomorrow_and_the_demo_night_are_postable(day):
    assert stay_error(day, 5, 1) is None


def test_post_request_refuses_a_past_night_before_posting_anything():
    box = toolbox()
    posted = []

    async def find(**request):
        posted.append(request)
        return {"shortlist": []}

    box.market.find = find
    result = asyncio.run(box.post_request(date="2026-10-31", nights=3, requirements=["dog"]))
    assert "in the past" in result["error"] and posted == []


def test_post_request_posts_the_users_party_size():
    box = toolbox()
    posted = []

    async def find(**request):
        posted.append(request)
        return {"shortlist": []}

    box.market.find = find
    asyncio.run(box.post_request(date="2026-11-02", guests=5, requirements=["2 dogs"], tags=["basel"]))
    assert posted == [{"date": "2026-11-02", "guests": 5, "requirements": ["2 dogs"], "tags": ["basel"]}]


def test_post_request_schema_offers_nights_and_guests():
    schema = next(s for s in tools.SCHEMAS if s["function"]["name"] == "post_request")["function"]
    assert {"nights", "guests", "date"} <= schema["parameters"]["properties"].keys()


# 2. Only the answer reaches the user.

def test_final_text_drops_a_note_written_before_the_answer():
    assert final_text(["The marketplace has no Zurich hotels, so I'll report that.",
                       "\n\nSorry, no verified hotels in Zurich yet.\nMood: sorry"]) == \
        "Sorry, no verified hotels in Zurich yet.\nMood: sorry"
    assert final_text(["Booked for CHF 128.", "Mood: happy"]) == "Booked for CHF 128.\nMood: happy"
    assert final_text(["", "  "]) == ""


def claude_with(blocks: list[dict], monkeypatch) -> ClaudeLLM:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    claude = LLM("claude-haiku-5-5")

    async def create(**_):
        return SimpleNamespace(content=[SimpleNamespace(model_dump=lambda exclude_none, b=b: b) for b in blocks])

    claude.client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return claude


def test_claude_answer_is_only_the_text_after_the_notes(monkeypatch):
    claude = claude_with([{"type": "text", "text": "No Zurich hotels, so I'll report that."},
                          {"type": "text", "text": "Sorry, none in Zurich yet.\nMood: sorry"}], monkeypatch)
    message = asyncio.run(claude.complete([{"role": "user", "content": "Zurich?"}], []))
    assert message["content"] == "Sorry, none in Zurich yet.\nMood: sorry"
    assert len(message["provider_items"]) == 2  # the provider keeps the full turn


def test_claude_text_before_a_tool_call_is_not_the_answer(monkeypatch):
    claude = claude_with([{"type": "text", "text": "Let me post that."},
                          {"type": "tool_use", "id": "t1", "name": "recall_context", "input": {}}], monkeypatch)
    message = asyncio.run(claude.complete([{"role": "user", "content": "hotel"}], []))
    assert message["content"] is None and message["tool_calls"][0]["function"]["name"] == "recall_context"


def test_openai_answer_is_only_the_last_message(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    model = LLM("gpt-5.1")
    items = [{"type": "message", "content": [{"type": "output_text", "text": "I'll report that."}]},
             {"type": "message", "content": [{"type": "output_text", "text": "Sorry, none.\nMood: sorry"}]}]

    async def create(**_):
        return SimpleNamespace(output=[SimpleNamespace(model_dump=lambda exclude_none, i=i: i) for i in items],
                               output_text="I'll report that.Sorry, none.\nMood: sorry")

    model.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    message = asyncio.run(model.complete([{"role": "user", "content": "Zurich?"}], []))
    assert message["content"] == "Sorry, none.\nMood: sorry"


# 5. One bargaining per turn.

class CountingNegotiator:
    """Stands in for TuttieNegotiator: every hotel agrees 7 below its offer."""
    runs: list[list[str]] = []

    def __init__(self, *_):
        pass

    async def negotiate_all(self, offers, context):
        CountingNegotiator.runs.append([o["node_id"] for o in offers])
        return [Outcome(o["node_id"], o["offer"]["offer_id"], "agreed", o["offer"]["price_chf"],
                        o["offer"]["price_chf"] - 7, 3, {"payload": {"price_chf": o["offer"]["price_chf"] - 7}})
                for o in offers]


@pytest.fixture
def market_box(monkeypatch):
    monkeypatch.setattr(negotiation.tuttie, "TuttieNegotiator", CountingNegotiator)
    CountingNegotiator.runs = []
    box = toolbox()
    offers = [{"node_id": n, "name": n.title(), "offer": {"offer_id": f"of-{i}", "price_chf": p}}
              for i, (n, p) in enumerate([("gaestehaus", 135), ("rheinblick", 220)])]
    box.market.last_offers = box.market.last_shortlist = offers
    box.market.last_request = {"request_id": "rq-1", "constraints": {"date": "2026-11-14", "requirements": []}}
    box.market.last_budget = 160
    return box


def test_negotiate_right_after_post_request_reuses_its_agreements(market_box):
    first = asyncio.run(market_box.negotiate(160, ["gaestehaus", "rheinblick"]))  # what post_request does
    again = asyncio.run(market_box.negotiate(160))
    favourite = asyncio.run(market_box.negotiate(None, ["gaestehaus"]))
    assert CountingNegotiator.runs == [["gaestehaus", "rheinblick"]]  # bargained once
    assert again["best"] == first["best"] == {"hotel": "Gaestehaus", "price_chf": 128, "offer_id": "of-0"}
    assert "Already negotiated" in again["note"] and [o["hotel"] for o in favourite["outcomes"]] == ["Gaestehaus"]


def test_a_new_message_or_another_budget_bargains_again(market_box):
    asyncio.run(market_box.negotiate(160))
    asyncio.run(market_box.negotiate(200))      # a different limit is a new negotiation
    market_box.new_turn()                       # the user asked again ("try for less")
    asyncio.run(market_box.negotiate(200))
    assert len(CountingNegotiator.runs) == 3


def test_every_user_message_starts_a_new_turn_for_the_toolbox():
    class OneAnswer:
        async def complete(self, messages, schemas, first_tool=None):
            return {"role": "assistant", "content": "Hi!\nMood: happy"}

    bus = EventBus()
    box = toolbox()
    tuttie = Assistant(OneAnswer(), box, bus)
    box.bargained = {"request_id": "rq-1", "budget": None, "outcomes": {}}
    asyncio.run(tuttie.chat("try for a better price"))
    assert box.bargained is None
    assert json.dumps(bus.history)  # the turn answered normally
