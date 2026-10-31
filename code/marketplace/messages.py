"""Marketplace and negotiation message formats in one place (draft of documentation/formats.md).

Every message here is the `payload` of an APS signed envelope; the envelope says who
sent it, these models say what it may contain. They are strict (unknown fields are
refused), so a sender and receiver that drift apart notice at once instead of silently
dropping data. Change a format here and in formats.md together.

Built against the DRAFT the team has not fully agreed on yet; see formats.md.
"""

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from aps.envelope import parse_timestamp

ID = r"^[a-z0-9][a-z0-9-]{0,63}$"
TAG = re.compile(r"^[a-z0-9-]{1,40}$")


def aps_timestamp(value: str) -> str:
    """Accept only APS timestamps (YYYY-MM-DDTHH:MM:SSZ, UTC)."""
    if parse_timestamp(value) is None:
        raise ValueError("must be an APS timestamp YYYY-MM-DDTHH:MM:SSZ")
    return value


def tag_list(values: list[str]) -> list[str]:
    """Registry tags: lowercase words with dashes, as in the node configs."""
    for value in values:
        if not TAG.match(value):
            raise ValueError(f"invalid tag {value!r}")
    return values


Timestamp = Annotated[str, AfterValidator(aps_timestamp)]
Tags = Annotated[list[str], AfterValidator(tag_list)]


class Message(BaseModel):
    """Base for all marketplace messages: strict, no unknown fields."""
    model_config = ConfigDict(extra="forbid")


class Constraints(Message):
    """What the user needs. Only public information goes here: the posting is seen by every
    matching business, so private details (e.g. the real budget limit) stay with Tuttie."""
    date: date
    guests: int = Field(1, ge=1, le=20)
    budget_chf: float | None = Field(None, gt=0)
    requirements: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=10)


class Request(Message):
    """A posting: the user's agent asks the market (signed by the user agent's key)."""
    type: Literal["request"] = "request"
    request_id: Annotated[str, Field(pattern=r"^rq-[a-z0-9-]{1,40}$")]
    category: Annotated[str, Field(pattern=r"^[a-z0-9-]{1,40}$")]
    tags: Tags = Field(default_factory=list, max_length=10)
    constraints: Constraints
    expires_at: Timestamp


class Offer(Message):
    """A business agent's answer to a request (signed by the business's node key).
    Its price comes from the node config, never from an LLM (the node's make_offer tool)."""
    type: Literal["offer"] = "offer"
    request_id: Annotated[str, Field(pattern=r"^rq-[a-z0-9-]{1,40}$")]
    offer_id: Annotated[str, Field(pattern=ID)]
    item: Annotated[str, Field(min_length=1, max_length=120)]
    price_chf: float = Field(gt=0)
    includes: list[str] = Field(default_factory=list, max_length=10)
    conditions: list[str] = Field(default_factory=list, max_length=10)
    valid_until: Timestamp


class Counter(Message):
    """One negotiation step about a signed offer (either side, step 4; code/negotiation/).

    Only the price is negotiable: includes and conditions must equal the offer's. Round 1 is
    the guest's first counter; the business answers each round with a Counter of the same
    round, an Agreement or a Rejection. `final` marks the business's last price: after it,
    only accepting that price (or walking away) is left.
    """
    type: Literal["counter"] = "counter"
    offer_id: Annotated[str, Field(pattern=ID)]
    round: int = Field(ge=1)
    price_chf: float = Field(gt=0)
    includes: list[str] = Field(default_factory=list, max_length=10)
    conditions: list[str] = Field(default_factory=list, max_length=10)
    final: bool = False


class Agreement(Message):
    """The price both sides accept, signed by the business. It is what the user approves on the
    phone and what booking redeems, like a commitment."""
    type: Literal["agreement"] = "agreement"
    request_id: Annotated[str, Field(pattern=r"^rq-[a-z0-9-]{1,40}$")]
    offer_id: Annotated[str, Field(pattern=ID)]
    round: int = Field(ge=1)
    item: Annotated[str, Field(min_length=1, max_length=120)]
    price_chf: float = Field(gt=0)
    includes: list[str] = Field(default_factory=list, max_length=10)
    conditions: list[str] = Field(default_factory=list, max_length=10)
    valid_until: Timestamp


class Rejection(Message):
    """The business ends the negotiation without an agreement; its offer still stands."""
    type: Literal["rejection"] = "rejection"
    offer_id: Annotated[str, Field(pattern=ID)]
    round: int = Field(ge=1)
    reason: Annotated[str, Field(min_length=1, max_length=200)]


class Posting(Message):
    """What a woken business agent gets: the user agent's signed request, unchanged, so it
    can verify the requester itself, plus where to send its signed offer."""
    request_id: str
    requester_id: str
    request: dict  # the signed envelope whose payload is a Request
    offer_url: str
    expires_at: Timestamp


class PostingCreated(Message):
    """Wake-up event sent to POST {node}/agent/invoke when a matching posting appears."""
    type: Literal["posting.created"] = "posting.created"
    posting: Posting
