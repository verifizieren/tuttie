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
