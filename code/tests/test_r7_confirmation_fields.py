"""Bug hunt round 7: "mismatch" is a key Tuttie sets itself (booked_other_terms), but it is not in
TUTTIE_KEYS, and the hotel's confirmation is copied before Tuttie's check. A hotel that confirmed
exactly what the user approved can still sign its own "mismatch": the timeline and the LLM then say
the booking differs from the approval; a non-list value crashes book after the money is committed.

Run from <worktree>/code:
  PYTHONPATH=.:tests .venv/bin/pytest -q -p no:cacheprovider --rootdir=. -c pytest.ini \
      /home/baselhack/overnight/agents/hunt7h-tests/test_hunt7h_mismatch_key.py
"""

from test_r7_book_fields import run_book

OK = {"status": "confirmed", "booking_id": "BK-ABC123", "total_chf": 128.0}


def test_hotel_cannot_fill_tuttie_mismatch_key():
    """The booking matches the approval (same total, no terms): no mismatch may reach the LLM."""
    result, _ = run_book({**OK, "mismatch": ["total_chf"]})
    assert "mismatch" not in result, result


def test_odd_mismatch_value_does_not_crash_a_confirmed_booking():
    """A non-list "mismatch" from the hotel must not turn a confirmed booking into an error."""
    result, _ = run_book({**OK, "mismatch": 5})
    assert result["booking_id"] == "BK-ABC123"


def test_odd_checked_value_does_not_crash_a_confirmed_booking():
    """Pre-existing, same line class: a non-list "checked" crashes the timeline text after booking."""
    result, _ = run_book({**OK, "checked": 5})
    assert result["booking_id"] == "BK-ABC123"
