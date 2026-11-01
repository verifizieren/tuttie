"""Round 5 fixes: ask_agent shares the posted night (never the budget) so a commitment holds for
it, an empty goodbye still says goodbye, and the model always knows whether deals exist."""

import asyncio

import httpx

from assistant.agent import GUEST_NAME, Assistant, drop_notes
from assistant.approvals import ApprovalBook
from assistant.events import EventBus
from assistant.tools import Toolbox

RHEINBLICK = "ch.basel.hotel-rheinblick"


def toolbox() -> Toolbox:
    return Toolbox(httpx.AsyncClient(), "http://registry", EventBus(), ApprovalBook())


def test_ask_agent_shares_only_the_posted_night():
    box = toolbox()
    box.market.last_request = {"request_id": "r1", "constraints": {"date": "2026-11-14", "guests": 1}}
    box.market.last_budget = 160
    sent = []

    async def verified_post(node_id, path, body, kind, label):
        sent.append(body)
        return {"rejected": True, "reason": "test"}

    box.verified_post = verified_post
    asyncio.run(box.ask_agent(RHEINBLICK, "Late arrival around 1 am with a dog?"))
    assert sent == [{"question": "Late arrival around 1 am with a dog?", "context": {"date": "2026-11-14"}}]


def test_ask_agent_without_a_posting_sends_no_context():
    box = toolbox()
    sent = []

    async def verified_post(node_id, path, body, kind, label):
        sent.append(body)
        return {"rejected": True, "reason": "test"}

    box.verified_post = verified_post
    asyncio.run(box.ask_agent(RHEINBLICK, "Dogs?"))
    assert sent[0]["context"] == {}


class Goodbye:
    """Real Haiku on "Bye!": end_conversation without text, then only the mood line."""

    def __init__(self):
        self.seen = []

    async def complete(self, messages, schemas, first_tool=None):
        self.seen.append(messages)
        if len(self.seen) == 1:
            return {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "end_conversation", "arguments": "{}"}}]}
        return {"role": "assistant", "content": "Mood: happy"}


def test_an_empty_goodbye_still_says_goodbye():
    bus = EventBus()
    answer = asyncio.run(Assistant(Goodbye(), toolbox(), bus).chat("Thanks, that's all for now. Bye!"))
    assert answer == f"Bye, {GUEST_NAME.split()[0]}! Enjoy Basel."
    assert [e["summary"] for e in bus.history if e["kind"] == "answer"] == [answer]


def test_an_empty_answer_without_goodbye_is_not_silent():
    class Empty:
        async def complete(self, messages, schemas, first_tool=None):
            return {"role": "assistant", "content": "Mood: neutral"}

    assert asyncio.run(Assistant(Empty(), toolbox(), EventBus()).chat("Hmm")) == "Sorry, I didn't catch that."


def test_the_model_is_told_when_there_are_no_deals_yet():
    llm = Goodbye()
    asyncio.run(Assistant(llm, toolbox(), EventBus()).chat("Book the Rheinblick agreement"))
    notes = [m["content"] for m in llm.seen[0] if m["role"] == "system"]
    assert "No offers or agreements yet in this conversation." in notes


def test_drop_notes_keeps_real_answers_and_drops_narration():
    assert drop_notes("I should check: Gästehaus agreed.\n\nSwipe right.").startswith("I should")
    assert drop_notes("The user asked about CHF 128.\n\nShall I book?").startswith("The user asked")
    assert drop_notes("The user asked if dogs are ok?\n\nYes.").startswith("The user")
    assert drop_notes("The user wants Basel, so I'll report the hotels.\n\nThree hotels.") == "Three hotels."
    assert drop_notes("The user said hi.") == "The user said hi."  # never empty
