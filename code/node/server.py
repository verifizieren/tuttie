"""Generic business node: one FastAPI app, started once per config in data/nodes/.

Usage: python -m node.server --config data/nodes/hotel-rheinblick.json [--port 4001]

Every response is a signed envelope from this node's key (keys/<node_id>.json).
The business's tools (get_availability, get_policies, book) are an MCP server at /mcp/
(node/mcp_tools.py); they answer only from the config's "facts". The company's agent (node/agent.py) answers other
agents (POST /agent), is woken by the marketplace (POST /agent/invoke) and describes itself
(GET /agent/card). Agents that want an ongoing conversation open a session
(POST /agent/sessions): each session has its own memory, so many run in parallel.
When the marketplace wakes an interested agent for a new posting, the node sends the agent's
signed offer to the posting's offer_url in the background (make_offer).
"""

import argparse
import asyncio
import copy
import hmac
import json
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date as Date
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError, field_validator

from apidocs import api_docs
from aps import agent_key
from aps import evaluate_record, load_signing_key, public_key_b64, sign_envelope, verify_envelope
from aps.approval import booking_terms
from aps.call import call_body
from aps.delegation import verify_delegation
from aps.envelope import is_fresh, parse_timestamp
from aps.gate import ActionGate, Needs
from aps.keys import load_public_key
from hosting import service_host
from marketplace.messages import PostingCreated
from marketplace.messages import Request as MarketRequest
from negotiation.agreement import AgreementRedeemer
from negotiation.hotel import counter_offer_mcp_tool, counter_offer_router, load_authorities, registry_lookup
from node.agent import MAX_DAYS_AHEAD, BusinessAgent
from node.deployments import DeploymentStore
from node.mcp_tools import mcp_app, mcp_server
from node.owner import owner_app
from node.settings import POSTING_EVENTS
from node.settings import apply as apply_settings
from node.settings import validate as validate_settings
from sessions import SessionClosed, SessionFull, SessionStore, StoreFull


SWISS_TIME = ZoneInfo("Europe/Zurich")
ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_GUESTS = 10


def stay_problem(day, guests=1, today: Date | None = None) -> str | None:
    """Why a night and guest count cannot be offered or booked, or None.

    The night must be a YYYY-MM-DD date from today (Swiss time) up to MAX_DAYS_AHEAD; guests
    a whole number from 1 to MAX_GUESTS. A business signs its answers, so it never signs
    rooms for a night that does not exist or has passed.
    """
    today = today or datetime.now(SWISS_TIME).date()
    if not isinstance(day, str) or not ISO_DAY.match(day):
        return "date must be YYYY-MM-DD"
    try:
        night = Date.fromisoformat(day)
    except ValueError:
        return "date must be YYYY-MM-DD"
    if not today <= night <= today + timedelta(days=MAX_DAYS_AHEAD):
        return f"bookable nights are from {today} to {today + timedelta(days=MAX_DAYS_AHEAD)}"
    if isinstance(guests, bool) or not isinstance(guests, int) or not 1 <= guests <= MAX_GUESTS:
        return f"guests must be a whole number from 1 to {MAX_GUESTS}"
    return None


def commitment_expired(commitment: dict, night: str, now: datetime | None = None) -> bool:
    """True if a signed commitment no longer holds for this booking: its valid_until is missing,
    has passed, or ends before the booked night (a promise for one arrival is not one for later)."""
    valid_until = parse_timestamp(commitment.get("valid_until"))
    if valid_until is None or valid_until <= (now or datetime.now(timezone.utc)):
        return True
    return Date.fromisoformat(night) >= valid_until.date()


LOOPBACK = {"localhost", "127.0.0.1", "::1"}
MAX_REQUEST_AGE_S = 300  # as fresh as the market wants a posted request (marketplace/market.py)


def market_url() -> str:
    """The marketplace this node sends offers to (same variables as marketplace/app.py)."""
    return os.environ.get("MARKETPLACE_URL", f"http://localhost:{os.environ.get('MARKETPLACE_PORT', '4010')}")


def offer_url_allowed(offer_url: str, request_id: str, market: str) -> bool:
    """Whether `offer_url` is the market's own offer door for this request.

    The node signs and POSTs an offer to it, so it must never be an arbitrary address (SSRF):
    same scheme, host (any loopback name counts as one) and effective port (443 for https) as
    `market`, no user info at all, and exactly the path /postings/{request_id}/offers.
    """
    try:
        url, allowed = urlsplit(offer_url), urlsplit(market)
        same_port = effective_port(url) == effective_port(allowed)
    except ValueError:
        return False
    host, allowed_host = url.hostname or "", allowed.hostname or ""
    same_host = host == allowed_host or (host in LOOPBACK and allowed_host in LOOPBACK)
    expected_path = f"{allowed.path.rstrip('/')}/postings/{request_id}/offers"
    return (url.scheme == allowed.scheme and same_host and same_port and url.path == expected_path
            and not url.query and not url.fragment and "@" not in url.netloc)


def effective_port(url) -> int | None:
    """The port a split URL really uses: the explicit one, else its scheme's default."""
    return url.port or {"http": 80, "https": 443}.get(url.scheme)


async def requester_problem(posting, lookup, authorities: dict, now=None,
                            user_public_key: str | None = None) -> str | None:
    """Why a posting's request is not a fresh one signed by a verified user agent, or None.

    The user agent must also carry the user's delegation with the "post_requests" scope
    (checked against `user_public_key`, by default the demo user's key in keys/).
    Only then is a posting worth an LLM call: a made-up posting costs the business nothing.
    """
    envelope, requester = posting.request, posting.requester_id
    record = await lookup(requester)
    if not record or record.get("kind") != "user-agent":
        return "the requester is not a user agent in the registry"
    if evaluate_record(record, authorities)["tier"] not in ("gold", "blue"):
        return "the requester's seals do not verify"
    if not verify_delegation(record.get("delegation") or {}, user_public_key or load_public_key("user"),
                             record["node_id"], record["public_key"], scope="post_requests", now=now):
        return "the requester has no valid delegation from the user to post requests"
    if not verify_envelope(envelope, record["public_key"], expected_node_id=requester):
        return "the request is not signed by the requester"
    if not is_fresh(envelope["timestamp"], MAX_REQUEST_AGE_S, now):
        return "the request is outdated"
    payload = envelope.get("payload")
    if not isinstance(payload, dict) or payload.get("request_id") != posting.request_id:
        return "the signed request is for another posting"
    try:
        MarketRequest.model_validate(payload)
    except ValidationError:
        return "the signed request is not a valid request"
    return None


class UsedCommitments:
    """Signed commitments already redeemed in a booking here: each one adds its add-on once.

    A commitment is known by its envelope's signature (Ed25519 signs deterministically, so the
    same signed promise always has the same one) and remembered until its valid_until (after
    that commitment_expired refuses it anyway), at most MAX_ENTRIES at once.
    """
    MAX_ENTRIES = 10_000

    def __init__(self) -> None:
        self.used: dict[str, datetime] = {}  # signature -> valid_until

    def problem(self, extras: list[dict]) -> str | None:
        """Why these commitments cannot be redeemed now (one used before, or twice here), or None."""
        now = datetime.now(timezone.utc)
        self.used = {sig: until for sig, until in self.used.items() if until > now}
        signatures = [str(extra.get("signature")) for extra in extras]
        if len(set(signatures)) != len(signatures):
            return "the same commitment is attached twice"
        if any(sig in self.used for sig in signatures):
            return "a commitment was already used for another booking: ask the hotel again"
        if len(self.used) + len(signatures) > self.MAX_ENTRIES:
            return "too many bookings right now, try again later"
        return None

    def redeem(self, extras: list[dict]) -> None:
        """Remember these (checked) commitments as used."""
        for extra in extras:
            until = parse_timestamp(extra["payload"]["commitment"].get("valid_until"))
            self.used[str(extra.get("signature"))] = until


class HandledRequests:
    """The signed requests this node has already answered, so a replay is not answered again.

    An entry is kept for twice MAX_REQUEST_AGE_S (after that the request is refused as outdated
    anyway), and at most MAX_ENTRIES at once: when full of fresh entries, new ones are refused
    (better no answer than an unbounded memory or a second LLM call for the same request).
    """
    MAX_ENTRIES = 10_000
    KEEP_S = 2 * MAX_REQUEST_AGE_S

    def __init__(self) -> None:
        self.seen: dict[tuple, float] = {}  # key -> when it may be forgotten (monotonic), oldest first

    def claim(self, key: tuple) -> str | None:
        """None the first time `key` is seen (it is then remembered), else why it is not answered."""
        now = time.monotonic()
        while self.seen:
            oldest = next(iter(self.seen))
            if self.seen[oldest] > now:
                break
            del self.seen[oldest]
        if key in self.seen:
            return "already handled"
        if len(self.seen) >= self.MAX_ENTRIES:
            return "too many requests right now"
        self.seen[key] = now + self.KEEP_S
        return None


def agent_caller(request: Request) -> None:
    """Only the deployment's own services may make the agent think (aps/agent_key.py): 401 otherwise."""
    if not agent_key.allowed(request.headers.get(agent_key.HEADER)):
        raise HTTPException(status_code=401, detail="this agent answers only its marketplace and known agents")


MAX_MESSAGE_CHARS = 2000   # a question or session message
MAX_NAME_CHARS = 200       # a session's peer and purpose
MAX_CONTEXT_BYTES = 8000   # the shared context, as JSON
SESSION_TOKEN_HEADER = "X-Session-Token"  # the opener's secret for every later call on its session


def small_context(context: dict) -> dict:
    """A shared context that fits a prompt: at most MAX_CONTEXT_BYTES as JSON (else 422)."""
    if len(json.dumps(context, ensure_ascii=False, default=str).encode()) > MAX_CONTEXT_BYTES:
        raise ValueError(f"context must be at most {MAX_CONTEXT_BYTES} bytes as JSON")
    return context


class AgentRequest(BaseModel):
    question: str = Field(max_length=MAX_MESSAGE_CHARS)
    context: dict = {}

    _small = field_validator("context")(small_context)


class SessionOpenRequest(BaseModel):
    peer: str = Field(max_length=MAX_NAME_CHARS)  # who opens the session, e.g. a Tuttie subagent's id
    purpose: str = Field("negotiation", max_length=MAX_NAME_CHARS)
    context: dict = {}             # what the peer chose to share (never its private context)

    _small = field_validator("context")(small_context)


class SessionMessageRequest(BaseModel):
    message: str = Field(max_length=MAX_MESSAGE_CHARS)


class BookRequest(BaseModel):
    date: str
    room_type: str
    guest_name: str
    extras: list[dict] = []  # signed A2A envelopes from this node that carry a commitment
    approval: dict  # the user's signed decision, see aps/approval.py
    agreement: dict | None = None  # this node's signed Agreement from a negotiation (negotiation/agreement.py)


def create_app(config: dict, http: httpx.AsyncClient | None = None, lookup=registry_lookup,
               deployments_dir: Path | None = None) -> FastAPI:
    """Build the FastAPI app for one node config.

    `http` is the client used to send offers to the marketplace, `lookup` how the action gate
    and the bargaining tool find registry records (tests pass in-process ones for both).
    The owner's deployed settings (node/deployments.py, kept in `deployments_dir`) are applied
    over a copy of `config`; the app works on that copy, which a deploy changes in place.
    """
    store = DeploymentStore(config["node_id"], config, deployments_dir)
    config = copy.deepcopy(config)
    if store.versions:
        apply_settings(config, validate_settings(store.current["settings"])[0])  # checked when loaded
    node_id = config["node_id"]

    def facts() -> dict:
        """The business's facts as deployed right now (an owner deploy replaces them)."""
        return config.get("facts", {})

    signing_key = load_signing_key(node_id)
    own_public_key = public_key_b64(signing_key)
    agreements = AgreementRedeemer(node_id, own_public_key)  # negotiated prices, each bookable once
    # Checks every signed action call: caller, signature, delegation, agreement, approval.
    authorities = load_authorities()
    gate = ActionGate(node_id, own_public_key, load_public_key("user"), authorities, lookup, agreements)
    bookings: set[str] = set()  # booking ids confirmed here, so charges can follow them
    paid: set[tuple[str, str]] = set()  # (booking id, purpose) already charged
    business_agent = BusinessAgent(config)
    sessions = SessionStore(owner=node_id)
    background: set[asyncio.Task] = set()  # offers being prepared and sent
    handled = HandledRequests()  # requests already answered: a replay gets no second LLM call
    used_commitments = UsedCommitments()  # signed add-on promises already booked here

    def signed(payload: dict) -> dict:
        """Wrap a response payload in this node's signed envelope."""
        return sign_envelope(node_id, payload, signing_key)

    def get_availability(date: str, guests: int = 1) -> dict:
        """Signed list of available rooms and prices for a date, or a signed refusal (stay_problem)."""
        if problem := stay_problem(date, guests):
            return signed({"tool": "get_availability", "status": "refused", "reason": problem})
        rooms = [
            {k: room[k] for k in ("room_type", "price_chf", "rate")}
            for room in facts().get("rooms", []) if room.get("available")
        ]
        return signed({
            "tool": "get_availability",
            "hotel": config["name"],
            "date": date,
            "guests": guests,
            "currency": "CHF",
            "rooms": rooms,
        })

    def get_policies() -> dict:
        """Signed policies: who the business is (size), location, quietness, dogs, check-in, cancellation."""
        current = facts()  # one read: a deploy meanwhile must not mix old and new values
        return signed({
            "tool": "get_policies",
            "hotel": config["name"],
            "profile": current.get("profile"),
            "address": current.get("address"),
            "distance_to_basel_sbb_m": current.get("distance_to_basel_sbb_m"),
            "quiet": current.get("quiet"),
            "quiet_note": current.get("quiet_note"),
            "policies": current.get("policies", {}),
            "photos": current.get("photos", []),      # image paths, served with the wallet (apps/wallet/public)
            "rating": current.get("rating"),          # guests' average score out of 5, with the count
            "amenities": current.get("amenities", {}),  # breakfast, wifi, parking, kids' beds
            "charges": current.get("charges", []),  # collected after a booking with pay
        })

    async def book(call: dict) -> dict:
        """Book a room for a signed call that passes the action gate (aps/gate.py).

        The hotel computes the total itself: the room's price plus extras, which must be its own
        signed A2A commitments; an agreement in the call (its own signed deal) replaces it with
        the agreed price. The gate then checks the caller, its signature, the user's delegation
        for "book" and the user's approval for exactly that amount. An agreement binds the
        booking to its offer: another room type, night or rate, or extras on top, are refused,
        and so is an approval signed for other terms (aps/approval.py, booking_terms). The
        confirmation names the rate booked and lists the checks it rests on.
        """
        def refuse(reason: str) -> dict:
            """A signed refusal with the reason."""
            return signed({"tool": "book", "status": "refused", "reason": reason})

        body = call_body(call) if isinstance(call, dict) else None
        if body is None:
            return refuse("the call is not a signed call")
        try:
            req = BookRequest(**body["args"])
        except ValidationError as error:
            return refuse(f"invalid arguments: {error.errors()[0]['msg']}")
        if problem := stay_problem(req.date):
            return refuse(problem)
        total, items = None, []
        if req.agreement is not None and req.extras:
            return refuse("an agreement fixes what is included: book it without extras")
        room = next((r for r in facts().get("rooms", []) if r["room_type"] == req.room_type and r.get("available")), None)
        if room is None:
            return refuse(f"no available room of type {req.room_type}")
        if req.agreement is None:
            total = room["price_chf"]
            for extra in req.extras:
                commitment = extra.get("payload", {}).get("commitment") if isinstance(extra, dict) else None
                if not commitment or not verify_envelope(extra, own_public_key, expected_node_id=node_id):
                    return refuse("an extra is not a commitment signed by this hotel")
                if commitment_expired(commitment, req.date):
                    return refuse(f"the commitment for {commitment.get('item')!r} has expired: ask the hotel again")
                total += commitment["price_chf"]
                items.append(commitment["item"])
            if problem := used_commitments.problem(req.extras):
                return refuse(problem)

        verdict = await gate.check_action(call, Needs("book", scope="book", approval=True, amount_chf=total))
        if not verdict.ok:
            return refuse(verdict.reason)
        deal = verdict.agreement
        if deal is not None:
            # The agreement is the selected offer: book exactly its room, night and rate.
            if deal.room_type is not None and req.room_type != deal.room_type:
                return refuse(f"the agreement is for a {deal.room_type} room, not {req.room_type}")
            if deal.date is not None and req.date != deal.date:
                return refuse(f"the agreement is for the night of {deal.date}, not {req.date}")
            if deal.rate is not None and room["rate"] != deal.rate:
                return refuse(f"the agreement is for the rate {deal.rate!r}, not {room['rate']!r}")
            items = list(deal.includes)
        terms = booking_terms(req.room_type, req.date, room["rate"], items, deal.offer_id if deal else None)
        approved = verdict.approval.get("terms") if verdict.approval else None
        if approved is not None and approved != terms:
            return refuse("the approval is for other terms than this booking (room, night, rate or extras)")
        # The gate awaited the registry: another booking may have redeemed the same commitment.
        if req.extras and (problem := used_commitments.problem(req.extras)):
            return refuse(problem)
        gate.commit(verdict)  # the approval and the agreement cannot be used again
        used_commitments.redeem(req.extras)  # and neither can the commitments
        booking_id = "BK-" + secrets.token_hex(3).upper()
        bookings.add(booking_id)
        return signed({
            "tool": "book",
            "status": "confirmed",
            "booking_id": booking_id,
            "hotel": config["name"],
            "date": req.date,
            "room_type": req.room_type,
            "rate": room["rate"],  # the cancellation terms booked
            "offer_id": deal.offer_id if deal else None,
            "guest_name": req.guest_name,
            "extras": items,
            "total_chf": verdict.amount_chf,
            "approval_id": verdict.approval["approval_id"],
            "arrival": facts().get("policies", {}).get("late_arrival"),
            "checked": verdict.checks + (["commitments"] if req.extras and verdict.agreement is None else []),
        })

    async def pay(call: dict) -> dict:
        """Collect one of this business's own charges (e.g. the city tax) for one of its bookings.

        The business takes the amount from its config, never from the caller. The gate checks the
        caller, its signature and the user's delegation, then either the user's approval for
        exactly this amount or the user's mandate for this purpose (at most CHF 10 a payment).
        Each charge is collected once per booking.
        """
        def refuse(reason: str) -> dict:
            """A signed refusal with the reason."""
            return signed({"tool": "pay", "status": "refused", "reason": reason})

        body = call_body(call) if isinstance(call, dict) else None
        if body is None:
            return refuse("the call is not a signed call")
        purpose, booking_id = body["args"].get("purpose"), body["args"].get("booking_id")
        charge = next((c for c in facts().get("charges", []) if c["purpose"] == purpose), None)
        if charge is None:
            return refuse(f"this business has no charge for {purpose!r}")
        if not isinstance(booking_id, str) or booking_id not in bookings:
            return refuse("there is no such booking with this business")
        if (booking_id, purpose) in paid:
            return refuse(f"the {purpose} for {booking_id} is already paid")

        verdict = await gate.check_action(call, Needs("pay", scope=None, approval=True, mandate=True,
                                                      amount_chf=charge["price_chf"], purpose=purpose,
                                                      booking_id=booking_id))
        if not verdict.ok:
            return refuse(verdict.reason)
        # The gate awaited the registry, so another call for the same charge may have paid
        # meanwhile: check again, then commit, with no await in between.
        if (booking_id, purpose) in paid:
            return refuse(f"the {purpose} for {booking_id} is already paid")
        gate.commit(verdict)  # an approval is used up; a mandate counts what was paid with it
        paid.add((booking_id, purpose))
        return signed({
            "tool": "pay",
            "status": "paid",
            "receipt_id": "RC-" + secrets.token_hex(3).upper(),
            "booking_id": booking_id,
            "purpose": purpose,
            "amount_chf": verdict.amount_chf,
            "paid_with": "mandate" if verdict.mandate is not None else "approval",
            "checked": verdict.checks,
        })

    tools = mcp_server(config["name"], {"get_availability": get_availability, "get_policies": get_policies, "book": book,
                                        "pay": pay},
                       extra={"counter_offer": counter_offer_mcp_tool(config, signed, lookup)})

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Run the MCP server's session manager while the node runs."""
        async with tools.session_manager.run():
            yield

    app = FastAPI(title=config["name"], lifespan=lifespan, **api_docs())
    app.state.mcp = tools  # in-process MCP clients (tests, headless demo) connect to this directly
    app.mount("/mcp", mcp_app(tools))
    # The owner view (apps/owner): read the live business, deploy new settings (node/owner.py).
    app.mount("/owner", owner_app(config, store, lambda: business_agent.apply(config)))

    @app.post("/agent", dependencies=[Depends(agent_caller)])
    async def agent(req: AgentRequest) -> dict:
        """The company's agent answers another agent (A2A), signed."""
        return signed(await business_agent.answer(req.question, req.context))

    @app.get("/agent/card")
    def agent_card() -> dict:
        """The agent's signed card: persona, tools and the events it wakes on."""
        return signed(business_agent.card())

    def find_session(session_id: str, request: Request):
        """The session, for its opener only: 404 if unknown, 403 without the opener's token."""
        try:
            session = sessions.get(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="no such session") from None
        token = request.headers.get(SESSION_TOKEN_HEADER) or ""
        if not hmac.compare_digest(token.encode(), session.token.encode()):
            raise HTTPException(status_code=403, detail="this session belongs to the agent that opened it")
        return session

    @app.post("/agent/sessions", dependencies=[Depends(agent_caller)])
    def open_session(req: SessionOpenRequest) -> dict:
        """Open an isolated conversation with its own memory (one per negotiation).

        The answer carries a session_token: only the opener knows it, and every later call on
        the session must send it (header X-Session-Token). When every session slot is busy, 429.
        """
        try:
            session = sessions.open(req.peer, req.purpose, req.context)
        except StoreFull:
            raise HTTPException(status_code=429, detail="too many conversations right now, try again later") from None
        session.add("system", "opened", {"peer": req.peer, "purpose": req.purpose})
        return signed({"session_id": session.id, "session_token": session.token,
                       "agent": business_agent.persona["name"], "purpose": req.purpose})

    @app.post("/agent/sessions/{session_id}/messages", dependencies=[Depends(agent_caller)])
    async def session_message(session_id: str, req: SessionMessageRequest, request: Request) -> dict:
        """Answer a message inside a session; the agent sees the session's history.

        A closed or full session answers 409 (also when it was closed during the answer).
        """
        session = find_session(session_id, request)
        async with session.lock:  # turns of one session stay in order; other sessions run in parallel
            try:
                session.add("peer", "message", {"text": req.message})
                reply = await business_agent.answer(req.message, session.context, history=session.transcript()[:-1])
                session.add("self", "reply", reply)
            except SessionFull:
                raise HTTPException(status_code=409, detail="session is full: open a new one") from None
            except SessionClosed:
                raise HTTPException(status_code=409, detail="session is closed") from None
        return signed({"session_id": session.id, "turn": len(session.turns), **reply})

    @app.get("/agent/sessions/{session_id}", dependencies=[Depends(agent_caller)])
    def read_session(session_id: str, request: Request) -> dict:
        """The session's whole memory, signed (for audits and the timeline), for its opener only."""
        return signed(find_session(session_id, request).to_dict())

    @app.post("/agent/sessions/{session_id}/close", dependencies=[Depends(agent_caller)])
    async def close_session(session_id: str, request: Request) -> dict:
        """End a session (after a reply being written, never during it); its memory stays
        readable for a while, then it is freed (sessions/memory.py)."""
        session = find_session(session_id, request)
        async with session.lock:
            if session.status == "open":
                sessions.close(session_id)
        return signed({"session_id": session_id, "status": session.status})

    @app.post("/agent/invoke", dependencies=[Depends(agent_caller)])
    async def agent_invoke(event: dict = Body(...)) -> dict:
        """The marketplace wakes the agent on a change; it answers whether and how it would respond.

        The body is the event itself, e.g. {"type": "posting.created", "posting": {...}}
        (marketplace/messages.py, PostingCreated). Only posting events are answered, and each one
        (posting.created or posting.updated) must hold a valid posting whose offer_url is the
        configured market's offer door for it (offer_url_allowed); else 422. Its request must be
        fresh and signed by a verified user agent (requester_problem); else 403. A request
        already handled is answered "already handled" (no second LLM call, no second offer).
        All of this is checked before any LLM runs.
        """
        kind = event.get("type")
        if kind not in POSTING_EVENTS:
            return signed({"woken_by": kind, "interested": False, "ignored": True,
                           "reason": "this agent only answers posting events", "next_tool": None})
        try:
            posting = PostingCreated.model_validate({**event, "type": "posting.created"}).posting
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=f"not a valid {kind} event: "
                                                        f"{error.errors()[0]['msg']}") from None
        if not offer_url_allowed(posting.offer_url, posting.request_id, market_url()):
            raise HTTPException(status_code=422, detail="offer_url is not this marketplace's offer address")
        problem = await requester_problem(posting, lookup, authorities)
        if problem:
            raise HTTPException(status_code=403, detail=problem)
        refused = handled.claim((posting.requester_id, posting.request_id))
        if refused:
            return signed({"woken_by": kind, "interested": False, "reason": refused, "next_tool": None})
        decision = await business_agent.invoke(event)
        choice = decision.pop("offer_choice", None)  # chosen while deciding; not part of the reply
        if kind == "posting.created" and decision.get("interested") and decision.get("next_tool") == "make_offer":
            task = asyncio.create_task(send_offer(event["posting"], choice))  # the market need not wait for it
            background.add(task)
            task.add_done_callback(background.discard)
        return signed(decision)

    async def send_offer(posting: dict, choice=None) -> None:
        """make_offer: let the agent compose an offer and post it, signed, to the market."""
        offer = await business_agent.make_offer(posting, choice)
        if offer is None:
            return
        client = http or httpx.AsyncClient(timeout=20)
        try:
            await client.post(posting["offer_url"], json=signed(offer))
        except httpx.HTTPError:
            pass  # the market is unreachable: the offer is lost, like a missed phone call
        finally:
            if http is None:
                await client.aclose()

    # Bargaining (negotiation/hotel.py, owned by its own work area): POST /tools/counter_offer.
    app.include_router(counter_offer_router(config, signed, lookup))
    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # OPENAI_API_KEY for /agent
    config = json.loads(Path(args.config).read_text())
    uvicorn.run(create_app(config), host=service_host(), port=args.port or config["port"])


if __name__ == "__main__":
    main()
