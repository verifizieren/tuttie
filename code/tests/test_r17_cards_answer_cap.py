"""Round 17: the answer of the turn that showed the hotel cards keeps its first two sentences
(it is read aloud while the user looks at the cards; it ran to 3-4 sentences, 60+ words)."""

from assistant.agent import first_sentences


def test_first_two_sentences_are_kept():
    text = ("I found two hotels, and I'd pick Gästehaus am Rhein. It's quiet and takes Luna, at CHF 128. "
            "The other, Hotel Rheinblick, is above your budget. Swipe to choose.")
    assert first_sentences(text, 2) == "I found two hotels, and I'd pick Gästehaus am Rhein. It's quiet and takes Luna, at CHF 128."


def test_decimals_and_short_answers_stay_whole():
    assert first_sentences("It costs CHF 12.50 a night. Fine.", 2) == "It costs CHF 12.50 a night. Fine."
    assert first_sentences("One sentence only.", 2) == "One sentence only."
