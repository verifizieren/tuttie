"""Red team round 5 (r5c): regressions in the round-2 hardening (1e2b1fd)."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from node.agent import BusinessAgent
from node.server import commitment_expired

NODES = Path(__file__).resolve().parent.parent / "data" / "nodes"


class StubLLM:
    def __init__(self, reply):
        self.reply = reply

    async def complete_json(self, system, user):
        return self.reply


def gaestehaus(reply):
    agent = BusinessAgent(json.loads((NODES / "guesthouse-am-rhein.json").read_text()))
    agent._llm = lambda: StubLLM(reply)
    return agent


def ask(agent, question):
    return asyncio.run(agent.answer(question, {}))  # Tuttie's ask_agent always sends context {}


def test_r5c_commitment_without_arrival_date_unusable_for_a_night_40_days_out():
    """The hotel LLM did not know the arrival date (null): the commitment gets COMMITMENT_DAYS=30,
    so a booking for a night more than 30 days ahead is refused as 'expired' and asking again
    gives the same promise. Before 1e2b1fd this booked."""
    reply = ask(gaestehaus({"answer": "Sure, door code.", "add_on": "breakfast", "arrival_date": None}),
                "Do you serve breakfast?")
    night = (datetime.now(timezone.utc).date() + timedelta(days=40)).isoformat()
    assert not commitment_expired(reply["commitment"], night), "a fresh commitment is refused for a legal night"


def test_r5c_commitment_with_llm_arrival_today_unusable_for_tomorrow_night():
    """'Guest arrives late, around 1 am' (no date in the question, context {}): the LLM guesses
    today. valid_until = tomorrow 12:00 UTC, and the night of tomorrow is then 'expired'."""
    today = datetime.now(timezone.utc).date()
    reply = ask(gaestehaus({"answer": "Door code it is.", "add_on": "late-arrival-dog",
                            "arrival_date": today.isoformat()}),
                "The guest arrives around 1 am with a dog, is that fine?")
    night = (today + timedelta(days=1)).isoformat()
    assert not commitment_expired(reply["commitment"], night)


def test_r5c_drop_notes_drops_a_real_first_paragraph():
    """drop_notes treats any leading paragraph with 'I should' as a note to self."""
    from assistant.agent import drop_notes
    answer = ("I should mention that Rheinblick is over your budget at CHF 220.\n\n"
              "Gästehaus am Rhein agreed to CHF 128. Swipe right if you like it.")
    assert "Rheinblick" in drop_notes(answer)


def test_r5c_final_text_keeps_only_last_of_two_answer_blocks():
    """Unconfirmed in live use (Claude rarely splits text without a tool call): two text blocks
    that together are the answer lose the first one."""
    from llm import final_text
    out = final_text(["Gästehaus am Rhein agreed to CHF 128.", "Shall I book it?\nMood: happy"])
    assert "128" in out
