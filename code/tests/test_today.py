"""Tuttie's prompt carries the current Swiss date instead of a fixed one."""

from datetime import datetime, timezone

from assistant.agent import SYSTEM_PROMPT, today_note


def test_no_hardcoded_date_in_prompt():
    assert "2026-11-13" not in SYSTEM_PROMPT


def test_today_note_uses_swiss_date():
    # 23:30 UTC on 31 Oct is already 1 Nov in Zurich (UTC+1 in winter).
    note = today_note(datetime(2026, 10, 31, 23, 30, tzinfo=timezone.utc))
    assert "2026-11-01" in note and "Sunday" in note and "00:30" in note
