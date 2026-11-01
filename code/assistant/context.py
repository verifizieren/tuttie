"""What Tuttie knows about its user: location, messages, mail, calendar and preferences.

Tuttie holds the user's full context, so "I want to book something" is enough: the calendar
says where and when, the messages who comes along, the preferences what matters and how much
may be spent. In the demo this comes from data/users/<user>.json; a real Tuttie would read
the user's own calendar, mail and messages on the phone.

Every item is classed like any context item (sessions/): public (may go into a posting),
negotiation (may be shared while bargaining) or private (never leaves Tuttie, e.g. the
budget). The LLM sees the classes and must keep private items out of everything it sends.
"""

import asyncio
import json
import os
from pathlib import Path

from assistant.events import EventBus

USERS_DIR = Path(__file__).resolve().parent.parent / "data" / "users"
USER_ID = os.environ.get("TUTTIE_USER", "alex-muster")
# Shown one after the other on the wallet's context line while Tuttie reads them.
SOURCES = [("location", "Checking location"), ("messages", "Checking messages"), ("mail", "Checking mails"),
           ("calendar", "Checking calendar"), ("preferences", "Checking what you like")]
DONE = "Checked your location, messages, mails and calendar"
READ_PACE_S = float(os.environ.get("CONTEXT_PACE_S", "0.15"))  # time per source: each step shows, briefly


class UserContext:
    """The user's calendar, mail, messages and preferences, read on request."""

    def __init__(self, user_id: str = USER_ID, pace_s: float = READ_PACE_S):
        self.data = json.loads((USERS_DIR / f"{user_id}.json").read_text())
        self.pace_s = pace_s

    async def recall(self, bus: EventBus) -> dict:
        """Read every source (each shown on the timeline), then return them for the LLM."""
        for source, label in SOURCES:
            bus.emit("context", "info", label, detail={"phase": "reading", "source": source})
            await asyncio.sleep(self.pace_s)
        bus.emit("context", "verified", DONE, detail={"phase": "found"})
        return {source: self.data.get(source, []) for source, _ in SOURCES} | {
            "rule": "Use these without asking. If the user wants a hotel or something booked, call "
                    "post_request next, in this same turn, with what these give (one guest unless "
                    "they or the calendar say otherwise): do not ask whether to search. Never put private items into "
                    "a posting, a message or a requirement; a private budget only goes into budget_chf."}
