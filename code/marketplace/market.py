"""The marketplace's agent layer (step 2): signed postings in, signed offers out.

1. A user agent (Tuttie) posts a Request in a signed envelope. The market accepts it only
   if the agent's seals hold, the envelope is fresh and signed by the agent's key, and the
   user's delegation grants "post_requests".
2. The market finds matching businesses in the registry (category + tags) and wakes each
   one with a PostingCreated event at POST {endpoint}/agent/invoke. Businesses with broken
   seals are never contacted. The posting carries Tuttie's signed request unchanged, so
   every business can verify the requester itself.
3. Woken businesses send signed Offers to the posting's offer_url. The market accepts an
   offer only from an invited business, signed with its key, fresh, for this request and
   still valid. It never changes a price; it only checks and stores signed offers.

The market decides nothing for the user: it hands every accepted offer to the user agent,
which picks (see shortlist). No LLM runs here.
"""

import asyncio
import re
from datetime import datetime, timezone

import httpx
from pydantic import ValidationError

from aps import evaluate_record, verify_envelope
from aps.delegation import verify_delegation
from aps.envelope import is_fresh, parse_timestamp
from marketplace.messages import Offer, Posting, PostingCreated, Request

NODE_ID = re.compile(r"^[a-z0-9.-]{1,80}$")
MAX_MESSAGE_AGE_S = 300  # signed postings and offers must be this fresh (replay protection)
INVOKE_TIMEOUT_S = 20  # a business agent may run an LLM before it answers the wake-up


class MarketError(Exception):
    """A refused message; `status` is the HTTP status the app answers with."""

    def __init__(self, reason: str, status: int = 422):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def utc(now: datetime | None) -> datetime:
    """`now` if given (tests pin the clock), else the current UTC time."""
    return now or datetime.now(timezone.utc)


def shortlist(offers: list[dict], size: int = 5, now: datetime | None = None) -> list[dict]:
    """The best `size` accepted offers for the user agent to look at.

    Offers that are expired or over the budget are left out. Gold and blue businesses
    rank by price alone, so a small gold guesthouse beats a big chain on price; grey
    (untrusted) ones come last because they may never be booked.
    """
    current = [
        o for o in offers
        if o["within_budget"] and parse_timestamp(o["offer"]["valid_until"]) > utc(now)
    ]
    ranked = sorted(current, key=lambda o: (o["trust_tier"] == "grey", o["offer"]["price_chf"]))
    return ranked[:size]


class Market:
    """In-memory marketplace. One instance per service; postings live until restart."""

    def __init__(self, http: httpx.AsyncClient, registry_url: str, authorities: dict,
                 user_public_key: str, public_url: str):
        self.http = http
        self.registry_url = registry_url.rstrip("/")
        self.authorities = authorities
        self.user_public_key = user_public_key  # the (demo) user whose delegation Tuttie carries
        self.public_url = public_url.rstrip("/")  # how businesses reach this market
        self.postings: dict[str, dict] = {}

    # --- registry ---------------------------------------------------------------------

    async def record(self, node_id: str) -> tuple[dict, dict]:
        """The registry record of `node_id` and its trust verdict; refuses unknown or broken nodes."""
        if not isinstance(node_id, str) or not NODE_ID.match(node_id):
            raise MarketError("invalid sender id")
        response = await self.http.get(f"{self.registry_url}/nodes/{node_id}")
        if response.status_code != 200:
            raise MarketError(f"{node_id} is not in the registry", 403)
        record = response.json()
        verdict = evaluate_record(record, self.authorities)
        if verdict["tier"] == "broken":
            raise MarketError(f"{node_id}: seals do not verify", 403)
        return record, verdict

    def check_signed(self, envelope: dict, record: dict, now: datetime | None) -> dict:
        """The payload of an envelope signed by `record`'s key and at most MAX_MESSAGE_AGE_S old."""
        if not verify_envelope(envelope, record["public_key"], record["node_id"]):
            raise MarketError("signature does not verify", 403)
        if not is_fresh(envelope["timestamp"], MAX_MESSAGE_AGE_S, now):
            raise MarketError("signed message is outdated (possible replay)", 403)
        return envelope["payload"]

    # --- postings ---------------------------------------------------------------------

    async def post_request(self, envelope: dict, now: datetime | None = None) -> dict:
        """Accept a signed Request from a user agent and wake the matching businesses."""
        requester_id = envelope.get("node_id") if isinstance(envelope, dict) else None
        record, verdict = await self.record(requester_id)
        if record.get("kind") != "user-agent":
            raise MarketError("only user agents may post requests", 403)
        payload = self.check_signed(envelope, record, now)
        if not verify_delegation(record.get("delegation") or {}, self.user_public_key, record["node_id"],
                                 record["public_key"], scope="post_requests", now=utc(now)):
            raise MarketError("no valid delegation from the user to post requests", 403)
        try:
            request = Request.model_validate(payload)
        except ValidationError as error:
            raise MarketError(f"not a valid request: {error.errors()[0]['msg']}") from None
        if parse_timestamp(request.expires_at) <= utc(now):
            raise MarketError("request has already expired")
        if request.request_id in self.postings:
            raise MarketError("request_id already posted", 409)

        posting = Posting(
            request_id=request.request_id,
            requester_id=record["node_id"],
            request=envelope,
            offer_url=f"{self.public_url}/postings/{request.request_id}/offers",
            expires_at=request.expires_at,
        )
        entry = {"posting": posting.model_dump(), "request": request.model_dump(mode="json"),
                 "requester_tier": verdict["tier"], "invited": {}, "offers": []}
        self.postings[request.request_id] = entry
        entry["invited"] = await self.wake(posting, [request.category, *request.tags])
        return self.view(request.request_id)

    async def wake(self, posting: Posting, tags: list[str]) -> dict[str, dict]:
        """Send PostingCreated to every matching business, in parallel; broken ones are skipped."""
        response = await self.http.get(f"{self.registry_url}/search", params={"tags": ",".join(tags)})
        candidates = []
        for record in response.json():
            if record.get("kind") != "business":
                continue
            verdict = evaluate_record(record, self.authorities)
            if verdict["tier"] != "broken":
                candidates.append((record, verdict))
        event = PostingCreated(posting=posting).model_dump()
        replies = await asyncio.gather(*(self.invoke(record, event) for record, _ in candidates))
        return {
            record["node_id"]: {"name": record["name"], "trust_tier": verdict["tier"], **reply}
            for (record, verdict), reply in zip(candidates, replies)
        }

    async def invoke(self, record: dict, event: dict) -> dict:
        """Wake one business agent. Its answer (interested?, next tool) is kept for the timeline;
        it is advisory only, since only a signed offer counts."""
        try:
            response = await self.http.post(f"{record['endpoint']}/agent/invoke", json=event,
                                            timeout=INVOKE_TIMEOUT_S)
        except httpx.HTTPError as error:
            return {"status": "unreachable", "detail": type(error).__name__}
        if response.status_code != 200:
            return {"status": "unreachable", "detail": f"HTTP {response.status_code}"}
        try:
            body = response.json()
        except ValueError:
            return {"status": "invited", "detail": "no JSON reply"}
        reply = body.get("payload", body) if isinstance(body, dict) else {}
        if not isinstance(reply, dict):
            reply = {}
        interested = reply.get("interested")
        status = "interested" if interested is True else "declined" if interested is False else "invited"
        return {"status": status, "next_tool": reply.get("next_tool") or reply.get("tool")}

    # --- offers -----------------------------------------------------------------------

    async def receive_offer(self, request_id: str, envelope: dict, now: datetime | None = None) -> dict:
        """Accept a signed Offer from an invited business for an open posting."""
        entry = self.postings.get(request_id)
        if entry is None:
            raise MarketError("no such posting", 404)
        if parse_timestamp(entry["posting"]["expires_at"]) <= utc(now):
            raise MarketError("posting has expired", 410)
        sender = envelope.get("node_id") if isinstance(envelope, dict) else None
        if sender not in entry["invited"]:
            raise MarketError("only businesses invited to this posting may offer", 403)
        record, verdict = await self.record(sender)  # re-checked: seals may have changed since
        payload = self.check_signed(envelope, record, now)
        try:
            offer = Offer.model_validate(payload)
        except ValidationError as error:
            raise MarketError(f"not a valid offer: {error.errors()[0]['msg']}") from None
        if offer.request_id != request_id:
            raise MarketError("offer is for another request")
        if parse_timestamp(offer.valid_until) <= utc(now):
            raise MarketError("offer has already expired")
        if any(o["offer"]["offer_id"] == offer.offer_id for o in entry["offers"]):
            raise MarketError("offer_id already received", 409)

        budget = entry["request"]["constraints"]["budget_chf"]
        accepted = {
            "node_id": sender,
            "name": record["name"],
            "trust_tier": verdict["tier"],
            "uid": verdict["uid"],
            "offer": offer.model_dump(),
            "within_budget": budget is None or offer.price_chf <= budget,
            "envelope": envelope,  # kept signed: the user agent re-verifies it, booking redeems it
        }
        entry["offers"].append(accepted)
        return accepted

    # --- reading ----------------------------------------------------------------------

    def view(self, request_id: str) -> dict:
        """A posting with who was invited and every accepted offer."""
        entry = self.postings.get(request_id)
        if entry is None:
            raise MarketError("no such posting", 404)
        return {"request_id": request_id, **{k: entry[k] for k in ("posting", "request", "invited", "offers")}}
