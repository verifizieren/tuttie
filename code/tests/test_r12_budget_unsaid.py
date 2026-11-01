"""Round 12: the private budget amount is not said aloud unless the user asks about it (others
hear Tuttie; the model still wrote "above your CHF 160 budget")."""

from assistant.agent import without_budget


def test_the_budget_amount_goes_from_budget_phrases():
    amounts = {160}
    assert without_budget("It is above your CHF 160 budget.", amounts) == "It is above your budget."
    assert without_budget("Only one fits your CHF 160 limit.", amounts) == "Only one fits your limit."
    assert without_budget("Well under your budget of CHF 160.", amounts) == "Well under your budget."
    assert without_budget("It agreed to CHF 128, within your CHF 160.", amounts) == "It agreed to CHF 128, within your budget."


def test_other_prices_and_a_user_who_asks_keep_their_numbers():
    amounts = {160}
    assert without_budget("The room is CHF 128 and the tax CHF 4.", amounts) == "The room is CHF 128 and the tax CHF 4."
    assert without_budget("A suite at CHF 160 is free.", amounts) == "A suite at CHF 160 is free."  # not a budget phrase
    assert without_budget("It is above your CHF 160 budget.", set()) == "It is above your CHF 160 budget."


def test_tuttie_s_answer_drops_the_amount_unless_the_user_asked():
    import asyncio
    import os
    import httpx
    os.environ.setdefault("OPENAI_API_KEY", "test")
    from assistant.agent import Assistant
    from assistant.approvals import ApprovalBook
    from assistant.events import EventBus
    from assistant.tools import Toolbox

    class OneAnswer:
        async def complete(self, messages, tools, tool_choice=None):
            return {"role": "assistant", "content": "Rheinblick is above your CHF 160 budget.\nMood: sorry",
                    "provider_items": []}

    def ask(text):
        bus = EventBus()
        toolbox = Toolbox(httpx.AsyncClient(), "http://registry", bus, ApprovalBook())
        toolbox.private_amounts = lambda: {160}
        return asyncio.run(Assistant(OneAnswer(), toolbox, bus).chat(text))

    assert ask("Is Rheinblick an option?") == "Rheinblick is above your budget."
    assert ask("What is my budget again?") == "Rheinblick is above your CHF 160 budget."
