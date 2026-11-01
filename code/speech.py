"""Times as people say them, shared by Tuttie's answers (assistant/agent.py, shown and stored)
and its voice (voice/agent.py spoken): "18:00" is "6 pm", "00:52" is "12:52 am"."""

import re

# 24-hour times (two-digit hour) not already said in 12 hours or meant as a duration; a
# trailing "hrs"/"Uhr" is part of the time: "18:00", "00:52", "14:00 hrs" yes; "8:30 pm",
# "1:30 hours", "18:00:30" no.
CLOCK = re.compile(r"(?<![:\d])\b([01]\d|2[0-3]):([0-5]\d)(?:[ \t]*(?:hrs?|uhr)\b)?\b"
                   r"(?!:\d|\s*(?:[ap]\.?m\b|noon|midnight|h\b|hours?\b|min))", re.IGNORECASE)
# Before a time these words make it a length of time ("takes 01:15"); "for" and "in" only when
# "hrs" follows ("for 01:15 hrs"), since "hold the room for 00:52" is a clock time.
DURATION_WORDS = re.compile(r"(?:^|\s)(?:takes|take|took|lasts)(?:\s+(?:about|around|approx\.?))?\s+$",
                            re.IGNORECASE)
MAYBE_DURATION_WORDS = re.compile(r"(?:^|\s)(?:for|in)(?:\s+(?:about|around|approx\.?))?\s+$", re.IGNORECASE)


def clock(match: re.Match) -> str:
    """A 24-hour time as it is said: "18:00" is "6 pm", "00:52" is "12:52 am", "00:00" is "midnight".
    After "takes", "lasts" ... (and after "for", "in" with "hrs") it is a length of time and stays."""
    before = match.string[max(0, match.start() - 12):match.start()]
    if DURATION_WORDS.search(before) or (MAYBE_DURATION_WORDS.search(before)
                                         and re.search(r"hrs?$", match.group(0), re.IGNORECASE)):
        return match.group(0)
    hour, minute = int(match.group(1)), int(match.group(2))
    if minute == 0 and hour in (0, 12):
        return "midnight" if hour == 0 else "noon"
    said = str(hour % 12 or 12) + (f":{minute:02d}" if minute else "")
    return f"{said} {'am' if hour < 12 else 'pm'}"


def said_times(text: str) -> str:
    """Every 24-hour clock time in `text` as it is said ("00:52" -> "12:52 am"); durations stay."""
    return CLOCK.sub(clock, text)
