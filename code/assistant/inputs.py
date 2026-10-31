"""Checks for text a user sends to Tuttie (typed with POST /chat or spoken via POST /voice/say).

A message is stored in the timeline and the conversation, and sent to the LLM on every later
turn, so it must be valid UTF-8 (a lone surrogate made every /history of the chat fail) and
short (one huge message multiplied the tokens of every following turn).
"""

from typing import Annotated

from pydantic import AfterValidator, StringConstraints

MAX_MESSAGE_CHARS = 2000


def encodable(text: str) -> str:
    """Refuse text that cannot be written as UTF-8 (lone surrogates from JSON escapes)."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("text must be valid unicode") from None
    return text


# A user's message: not blank, at most MAX_MESSAGE_CHARS, valid UTF-8.
UserText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS),
                     AfterValidator(encodable)]
