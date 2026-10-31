"""The business side of bargaining: the `counter_offer` tool (POST /tools/counter_offer).

The tool is stateless, like `book`: every counter carries what the hotel needs to check it,
signed by whoever is responsible for each part:

    counter  the guest agent's Counter, signed by the user agent (Tuttie); its registry
             record must hold and the user's delegation must grant "negotiate"
    offer    the hotel's own Offer the negotiation is about, signed by this hotel
    last     the hotel's own previous Counter (rounds 2+), signed by this hotel

So the hotel trusts only its own signatures for its earlier prices and rounds; nobody can
make it "remember" a price it never proposed. Replaying an older state gains nothing: the
answer depends only on the signed prices and the round, and never goes below the floor.

The decision itself is negotiation/rules.py: limits compared in code, no LLM, and the
limits never appear in a reply. Every reply is signed by the node: a Counter, an Agreement
or a Rejection (marketplace/messages.py), or {"status": "refused"} for invalid input.

Mount it in node/server.py's create_app:
    app.include_router(counter_offer_router(config, signed))
"""

import json
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, ValidationError

from aps import evaluate_record, load_signing_key, public_key_b64, verify_envelope
from aps.delegation import verify_delegation
from aps.envelope import is_fresh, parse_timestamp
from aps.keys import load_public_key
from marketplace.messages import Agreement, Counter, Offer, Rejection
from negotiation.rules import Limits, decide, floor_total

ROOT = Path(__file__).resolve().parent.parent
MAX_COUNTER_AGE_S = 300  # a guest's counter must be this fresh (replay protection)
REGISTRY_URL = os.environ.get("REGISTRY_URL", f"http://localhost:{os.environ.get('REGISTRY_PORT', '4000')}")

Lookup = Callable[[str], Awaitable[dict | None]]


class CounterOfferRequest(BaseModel):
    counter: dict           # signed envelope from the user agent, payload: Counter
    offer: dict             # this hotel's signed envelope, payload: Offer
    last: dict | None = None  # this hotel's signed previous Counter (rounds 2 and later)


def load_authorities() -> dict:
    """The trusted authorities from data/authorities.json, by issuer id."""
    return {a["issuer"]: a for a in json.loads((ROOT / "data" / "authorities.json").read_text())}


async def registry_lookup(node_id: str) -> dict | None:
    """A record from the registry service, or None if it is unknown or unreachable."""
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            response = await http.get(f"{REGISTRY_URL}/nodes/{node_id}")
    except httpx.HTTPError:
        return None
    return response.json() if response.status_code == 200 else None


def message(payload: dict) -> dict:
    """A reply payload without the node's "tool" label, i.e. the bare message.

    Raises TypeError for anything that is not a JSON object, so callers refuse it cleanly
    (a signed list or string is still not a message).
    """
    if not isinstance(payload, dict):
        raise TypeError("a message must be a JSON object")
    return {k: v for k, v in payload.items() if k != "tool"}


class CounterOfferRefused(Exception):
    """Invalid input: answered with a signed {"status": "refused", "reason"}."""


class CounterOfferTool:
    """Checks a counter and decides the hotel's answer within its private limits."""

    def __init__(self, config: dict, lookup: Lookup = registry_lookup):
        self.node_id = config["node_id"]
        facts = config.get("facts", {})
        self.add_ons = facts.get("add_ons", [])
        self.limits = Limits.from_facts(facts)  # private: compared here, never sent
        self.own_public_key = public_key_b64(load_signing_key(self.node_id))
        self.user_public_key = load_public_key("user")
        self.authorities = load_authorities()
        self.lookup = lookup

    def own(self, envelope: dict | None, model, what: str):
        """A payload this hotel signed itself, parsed with `model`."""
        if not isinstance(envelope, dict) or not verify_envelope(envelope, self.own_public_key, self.node_id):
            raise CounterOfferRefused(f"{what} is not signed by this hotel")
        try:
            return model.model_validate(message(envelope["payload"]))
        except (ValidationError, TypeError):
            raise CounterOfferRefused(f"{what} is not a valid {model.__name__}") from None

    async def guest_counter(self, envelope: dict, now: datetime) -> Counter:
        """The guest agent's counter: sealed, delegated to negotiate, signed, fresh."""
        sender = envelope.get("node_id") if isinstance(envelope, dict) else None
        record = await self.lookup(sender) if isinstance(sender, str) else None
        if record is None or record.get("kind") != "user-agent":
            raise CounterOfferRefused("counter is not from a known user agent")
        if evaluate_record(record, self.authorities)["tier"] == "broken":
            raise CounterOfferRefused("the user agent's seals do not verify")
        if not verify_envelope(envelope, record["public_key"], sender):
            raise CounterOfferRefused("counter signature does not verify")
        if not is_fresh(envelope["timestamp"], MAX_COUNTER_AGE_S, now):
            raise CounterOfferRefused("counter is outdated (possible replay)")
        if not verify_delegation(record.get("delegation") or {}, self.user_public_key, sender,
                                 record["public_key"], scope="negotiate", now=now):
            raise CounterOfferRefused("the user has not delegated negotiating to this agent")
        try:
            return Counter.model_validate(message(envelope["payload"]))
        except (ValidationError, TypeError):
            raise CounterOfferRefused("counter is not a valid Counter") from None

    async def answer(self, req: CounterOfferRequest, now: datetime | None = None) -> dict:
        """The hotel's reply payload: Counter, Agreement or Rejection."""
        now = now or datetime.now(timezone.utc)
        offer = self.own(req.offer, Offer, "offer")
        if parse_timestamp(offer.valid_until) <= now:
            raise CounterOfferRefused("the offer has expired")
        counter = await self.guest_counter(req.counter, now)
        if counter.offer_id != offer.offer_id:
            raise CounterOfferRefused("counter is about another offer")
        if (counter.includes, counter.conditions) != (offer.includes, offer.conditions):
            raise CounterOfferRefused("only the price is negotiable: includes and conditions must match the offer")

        if counter.round == 1:
            if req.last is not None:
                raise CounterOfferRefused("round 1 has no previous counter")
            previous_price, previous_final = offer.price_chf, False
        else:
            last = self.own(req.last, Counter, "previous counter")
            if last.offer_id != offer.offer_id or last.round != counter.round - 1:
                raise CounterOfferRefused("previous counter does not belong to this round")
            previous_price, previous_final = last.price_chf, last.final

        lowest = floor_total(offer.price_chf, offer.includes, self.add_ons, self.limits) if self.limits else None
        decision = decide(counter.price_chf, counter.round, previous_price, previous_final, lowest, self.limits)
        if decision.kind == "agreement":
            reply = Agreement(request_id=offer.request_id, offer_id=offer.offer_id, round=counter.round,
                              item=offer.item, price_chf=decision.price_chf, includes=offer.includes,
                              conditions=offer.conditions, valid_until=offer.valid_until)
        elif decision.kind == "counter":
            reply = Counter(offer_id=offer.offer_id, round=counter.round, price_chf=decision.price_chf,
                            includes=offer.includes, conditions=offer.conditions, final=decision.final)
        else:
            reply = Rejection(offer_id=offer.offer_id, round=counter.round, reason=decision.reason)
        return reply.model_dump()


def counter_offer_router(config: dict, signed: Callable[[dict], dict], lookup: Lookup = registry_lookup) -> APIRouter:
    """POST /tools/counter_offer for one node; `signed` wraps a payload in the node's envelope."""
    tool = CounterOfferTool(config, lookup)
    router = APIRouter()

    @router.post("/tools/counter_offer")
    async def counter_offer(req: CounterOfferRequest) -> dict:
        """Answer a guest's counter within the owner's private limits, signed."""
        try:
            return signed({"tool": "counter_offer", **await tool.answer(req)})
        except CounterOfferRefused as refusal:
            return signed({"tool": "counter_offer", "status": "refused", "reason": str(refusal)})

    return router
