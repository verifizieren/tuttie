"""Explicit card choices shared by speech filtering and the assistant.

Bare yes/no/accept are deliberately excluded: they can answer a payment approval.
Longer or ambiguous phrases stay with the assistant's normal language handling.
"""
import re

CHOICES = {
    "like": "like", "i like it": "like", "i like this one": "like", "keep this one": "like",
    "gefällt mir": "like", "das gefällt mir": "like", "behalten": "like",
    "pass": "pass", "reject": "pass", "skip": "pass", "next": "pass", "dislike": "pass",
    "pass on this one": "pass", "skip this one": "pass", "reject this one": "pass",
    "not this one": "pass", "i don't like this one": "pass", "no thanks": "pass",
    "weiter": "pass", "überspringen": "pass", "ablehnen": "pass", "das nicht": "pass",
}


def card_choice(text: str) -> str | None:
    normalized = " ".join(re.sub(r"[.!?,]+$", "", text.lower().strip()).replace("’", "'").split())
    return CHOICES.get(normalized)
