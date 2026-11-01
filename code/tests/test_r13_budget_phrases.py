"""rev13: review of without_budget() and the `asked` gate in Assistant._turn (no LLM)."""
import asyncio
import os

import httpx
import pytest

from assistant.agent import without_budget

A = {160}


# ---- CONFIRMED -------------------------------------------------------------------------------

def test_sentence_initial_your_keeps_its_capital():
    # r"your \1" hard-codes lower case: "Your CHF 160 budget ..." -> "your budget ..."
    assert without_budget("Your CHF 160 budget covers two of them.", A) == "Your budget covers two of them."


def test_decimal_price_is_not_cut_in_half():
    # "within your CHF 160.50" -> "within your budget.50": the (?! \w) lookahead lets ".50" through
    out = without_budget("That is within your CHF 160.50 cap.", A)
    assert "budget.50" not in out


def test_a_hotel_fact_that_equals_the_budget_is_not_rewritten():
    # "budget|limit|maximum of CHF n" is not tied to "your": a hotel's own limit loses its amount
    text = "Rheinblick has a deposit limit of CHF 160 at check-in."
    assert without_budget(text, A) == text


def test_set_a_maximum_does_not_dangle():
    # user asked "what's my max?" (not caught by `asked`): answer becomes "You set a maximum."
    assert without_budget("You set a maximum of CHF 160 per night.", A) != "You set a maximum per night."


def _ask(user_text, answer, amounts=frozenset({160})):
    os.environ.setdefault("OPENAI_API_KEY", "test")
    from assistant.agent import Assistant
    from assistant.approvals import ApprovalBook
    from assistant.events import EventBus
    from assistant.tools import Toolbox

    class OneAnswer:
        async def complete(self, messages, tools, tool_choice=None):
            return {"role": "assistant", "content": answer + "\nMood: neutral", "provider_items": []}

    bus = EventBus()
    toolbox = Toolbox(httpx.AsyncClient(), "http://registry", bus, ApprovalBook())
    toolbox.private_amounts = lambda: set(amounts)
    return asyncio.run(Assistant(OneAnswer(), toolbox, bus).chat(user_text))


@pytest.mark.parametrize("q", ["what's my max?", "How much did I say I'd spend?", "wie viel darf ich ausgeben?"])
def test_asked_gate_catches_budget_questions(q):
    # the amount is the answer to these questions; stripping it leaves "your limit" with no number
    assert "160" in _ask(q, "You set a maximum of CHF 160.")


def test_hotel_name_budget_rooms_opens_the_gate():
    # "Budget Rooms" is a hotel name: any message naming it lets the amount be read aloud
    assert "160" not in _ask("Tell me about Budget Rooms", "Budget Rooms is within your CHF 160.")


# ---- passing checks (behaviour is fine) ------------------------------------------------------

def test_fine_cases():
    assert without_budget("A room at CHF 160, within your CHF 160.", A) == "A room at CHF 160, within your budget."
    assert without_budget("Within your CHF 160 budget.", A) == "Within your budget."
    assert without_budget("within your budget of CHF 160.", A) == "within your budget."
    assert without_budget("under your CHF 1600 cap", A) == "under your CHF 1600 cap"
    assert without_budget("CHF 160, within your CHF 16.", {16, 160, 0}) == "CHF 160, within your budget."
    assert without_budget("", {0}) == ""
    assert _ask("bye", "") == "Sorry, I didn't catch that."  # fallback untouched
    assert _ask("Is there a German Budget?", "within your CHF 160.") == "within your CHF 160."
    assert _ask("no limit please", "within your CHF 160.") == "within your CHF 160."  # gate open: amount said
