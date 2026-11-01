"""rev14: "within your CHF 160" followed by any word keeps the private amount ((?! \\w) lookahead)."""
from assistant.agent import without_budget


def test_within_your_amount_per_night_drops_the_amount():
    out = without_budget("Gundeli agreed to CHF 128, within your CHF 160 per night.", {160})
    assert "160" not in out, out


def test_within_your_amount_for_the_night_drops_the_amount():
    out = without_budget("That is well under your CHF 160 for Saturday.", {160})
    assert "160" not in out, out


def test_everyday_words_do_not_count_as_asking_about_the_budget():
    import re
    from assistant.agent import ASKED_BUDGET
    for text in ("Find me a budget hotel", "It's a limited offer", "Where do I spend the night?"):
        assert not ASKED_BUDGET.search(text), text
    for text in ("What's my budget?", "what's my max?", "Is there a limit?", "How much can I spend?"):
        assert ASKED_BUDGET.search(text), text
