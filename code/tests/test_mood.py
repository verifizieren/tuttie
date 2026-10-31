"""Tests for the mood line that ends every answer (shown on Tuttie's face in the wallet)."""

from assistant.agent import split_mood


def test_mood_line_is_split_off():
    assert split_mood("Booked at CHF 128 [9].\nMood: excited") == ("Booked at CHF 128 [9].", "excited")


def test_missing_or_unknown_mood_is_neutral():
    assert split_mood("Hello!") == ("Hello!", "neutral")
    assert split_mood("Hello!\nMood: grumpy") == ("Hello!", "neutral")


def test_mood_case_and_trailing_dot():
    assert split_mood("Sorry, nothing free.\n\nmood: Sorry.") == ("Sorry, nothing free.", "sorry")
