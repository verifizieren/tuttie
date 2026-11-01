"""The marketplace's agent layer (step 2): signed postings in, signed offers out.

1. A user agent (Tuttie) posts a Request in a signed envelope. The market accepts it only
   if the agent's seals hold, the envelope is fresh and signed by the agent's key, and the
   user's delegation grants "post_requests".
2. The market finds matching businesses in the registry (category + tags). Only verified
   ones (gold or blue) are considered: broken and untrusted (grey) businesses are listed as
   skipped and never contacted. For each, it reads the agent's signed card (GET /agent/card)
   and wakes it with a PostingCreated event at POST {endpoint}/agent/invoke only if the agent
   subscribed to "posting.created" (its `wakes_on`). The posting carries Tuttie's signed
   request unchanged, so every business can verify the requester itself.
3. Woken businesses send signed Offers to the posting's offer_url. The market accepts an
   offer only from an invited business, signed with its key, fresh, for this request and
   still valid. It never changes a price; it only checks and stores signed offers.

The market decides nothing for the user: it hands every accepted offer to the user agent,
which builds the shortlist (assistant/marketplace.py). No LLM runs here.
"""

import asyncio
import re
import time
from collections import deque
from datetime import datetime, timezone

import httpx
from pydantic import ValidationError

from aps import agent_key, evaluate_record, verify_envelope
from aps.delegation import verify_delegation
from aps.envelope import is_fresh, parse_timestamp
from marketplace.messages import Offer, Posting, PostingCreated, Request

NODE_ID = re.compile(r"^[a-z0-9.-]{1,80}$")
MAX_MESSAGE_AGE_S = 300  # signed postings and offers must be this fresh (replay protection)
MAX_CARD_AGE_S = 300  # a node signs its agent card on every GET; an older card is a replay
INVOKE_TIMEOUT_S = 20  # a business agent may run an LLM before it answers the wake-up
TRUSTED_TIERS = ("gold", "blue")  # untrusted (grey) and broken businesses are never woken
EVENT = "posting.created"
# Every posting wakes every subscribed hotel (two paid LLM calls each), and the demo keys are
# public: so postings are limited per requester. All wallet users share Tuttie's agent id, so the
# limit leaves room for a full room scanning the QR code at once.
POSTINGS_PER_MIN = 120
MAX_OPEN_POSTINGS = 500  # postings kept in memory; the oldest is dropped beyond this


class MarketError(Exception):
    """A refused message; `status` is the HTTP status the app answers with."""

    def __init__(self, reason: str, status: int = 422, retry_after: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.retry_after = retry_after  # seconds, for a Retry-After header (429)


def utc(now: datetime | None) -> datetime:
    """`now` if given (tests pin the clock), else the current UTC time."""
    return now or datetime.now(timezone.utc)


class Market:
    """In-memory marketplace. One instance per service; postings live until restart."""

    def __init__(self, http: httpx.AsyncClient, registry_url: str, authorities: dict,
                 user_public_key: str, public_url: str):
        self.http = http
        self.registry_url = registry_url.rstrip("/")
        self.authorities = authorities
        self.user_public_key = user_public_key  # the (demo) user whose delegation Tuttie carries
        self.public_url = public_url.rstrip("/")  # how businesses reach this market
        self.postings: dict[str, dict] = {}  # oldest first (insertion order)
        self.recent_postings: dict[str, deque] = {}  # requester id -> times of its postings this minute

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
        self.throttle(record["node_id"])

        posting = Posting(
            request_id=request.request_id,
            requester_id=record["node_id"],
            request=envelope,
            offer_url=f"{self.public_url}/postings/{request.request_id}/offers",
            expires_at=request.expires_at,
        )
        entry = {"posting": posting.model_dump(), "request": request.model_dump(mode="json"),
                 "requester_tier": verdict["tier"], "invited": {}, "skipped": {}, "offers": []}
        self.postings[request.request_id] = entry
        while len(self.postings) > MAX_OPEN_POSTINGS:
            del self.postings[next(iter(self.postings))]
        await self.wake(posting, [request.category, *request.tags], entry)
        return self.view(request.request_id)

    def throttle(self, requester_id: str) -> None:
        """Count one posting for `requester_id`; refuse it (429) beyond POSTINGS_PER_MIN a minute.

        Only requesters in the registry get here, so the table stays small.
        """
        now = time.monotonic()
        times = self.recent_postings.setdefault(requester_id, deque())
        while times and now - times[0] > 60:
            times.popleft()
        if len(times) >= POSTINGS_PER_MIN:
            raise MarketError("too many postings right now, try again in a minute", 429,
                              retry_after=max(1, int(times[0] + 60 - now) + 1))
        times.append(now)

    async def wake(self, posting: Posting, tags: list[str], entry: dict) -> None:
        """Wake every matching, verified business that subscribed to new postings, in parallel.

        Fills entry["invited"] (woken; may send offers) and entry["skipped"] (untrusted, broken,
        not subscribed, card unreadable). Businesses are recorded as invited *before* they are
        woken, because an agent may send its offer before every wake-up has been answered.
        """
        response = await self.http.get(f"{self.registry_url}/search", params={"tags": ",".join(tags)})
        skipped, candidates = {}, []
        for record in response.json():
            if record.get("kind") != "business":
                continue
            verdict = evaluate_record(record, self.authorities)
            if verdict["tier"] in TRUSTED_TIERS:
                candidates.append((record, verdict))
            else:
                skipped[record["node_id"]] = {"name": record["name"], "trust_tier": verdict["tier"],
                                              "reason": "broken seal" if verdict["tier"] == "broken" else "untrusted"}
        cards = await asyncio.gather(*(self.agent_card(record) for record, _ in candidates))
        event = PostingCreated(posting=posting).model_dump()
        subscribed = []
        for (record, verdict), card in zip(candidates, cards):
            if card is None or EVENT not in card.get("wakes_on", []):
                reason = "no verifiable agent card" if card is None else "not subscribed to new postings"
                skipped[record["node_id"]] = {"name": record["name"], "trust_tier": verdict["tier"], "reason": reason}
            else:
                subscribed.append((record, verdict, card))
        entry["skipped"] = skipped
        entry["invited"] = {
            record["node_id"]: {"name": record["name"], "trust_tier": verdict["tier"],
                                "agent": card.get("persona", {}).get("name"), "profile": card.get("profile"),
                                "status": "invited"}
            for record, verdict, card in subscribed
        }
        replies = await asyncio.gather(*(self.invoke(record, event) for record, _, _ in subscribed))
        for (record, _, _), reply in zip(subscribed, replies):
            entry["invited"][record["node_id"]].update(reply)

    async def agent_card(self, record: dict) -> dict | None:
        """The business agent's card, if it is signed by the business and fresh; None otherwise.

        The endpoint it is fetched from is sealed in the record (aps/seals.py), and the card
        must be at most MAX_CARD_AGE_S old, so an old card replayed by another host is refused.
        """
        try:
            response = await self.http.get(f"{record['endpoint']}/agent/card", timeout=INVOKE_TIMEOUT_S)
            envelope = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        if response.status_code != 200 or not verify_envelope(envelope, record["public_key"],
                                                              expected_node_id=record["node_id"]):
            return None
        if not is_fresh(envelope["timestamp"], MAX_CARD_AGE_S):
            return None
        return envelope["payload"]

    async def invoke(self, record: dict, event: dict) -> dict:
        """Wake one business agent. Its answer (interested?, next tool) is kept for the timeline;
        it is advisory only, since only a signed offer counts."""
        try:
            response = await self.http.post(f"{record['endpoint']}/agent/invoke", json=event,
                                            headers=agent_key.headers(), timeout=INVOKE_TIMEOUT_S)
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

        accepted = {
            "node_id": sender,
            "name": record["name"],
            "trust_tier": verdict["tier"],
            "uid": verdict["uid"],
            "offer": offer.model_dump(),
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
        return {"request_id": request_id, **{k: entry[k] for k in ("posting", "request", "invited", "skipped", "offers")}}
