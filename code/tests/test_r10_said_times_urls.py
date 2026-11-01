"""hunt10 (low): said_times runs on the whole answer before the voice strips web addresses, so
a time inside a URL is rewritten ("?from=18:00" -> "?from=6 pm"): the screen shows a broken link
and the voice says a stray "pm" (before 48480db the voice dropped the URL first)."""

from speech import said_times
from voice.agent import spoken


def test_a_time_inside_a_web_address_stays():
    text = "Details at https://basel.ch/events?from=18:00 tonight."
    assert said_times(text) == text
    assert spoken(said_times(text)) == spoken(text)
