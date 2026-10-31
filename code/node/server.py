"""Generic business node: one FastAPI app, started once per config in data/nodes/.

Usage: python -m node.server --config data/nodes/hotel-rheinblick.json [--port 4001]

Every response is a signed envelope from this node's key (keys/<node_id>.json).
Tools answer only from the config's "facts"; the company's agent (node/agent.py) answers other
agents (POST /agent), is woken by the marketplace (POST /agent/invoke) and describes itself
(GET /agent/card). Agents that want an ongoing conversation open a session
(POST /agent/sessions): each session has its own memory, so many run in parallel.
When the marketplace wakes an interested agent for a new posting, the node sends the agent's
signed offer to the posting's offer_url in the background (make_offer).
"""

import argparse
import asyncio
import json
import secrets
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel

from aps import load_signing_key, public_key_b64, sign_envelope, verify_envelope
from aps.approval import verify_decision
from aps.keys import load_public_key
from negotiation.agreement import AgreementInvalid, AgreementRedeemer
from negotiation.hotel import counter_offer_router, registry_lookup
from node.agent import BusinessAgent
from sessions import SessionClosed, SessionStore


class AvailabilityRequest(BaseModel):
    date: str
    guests: int = 1


class AgentRequest(BaseModel):
    question: str
    context: dict = {}


class SessionOpenRequest(BaseModel):
    peer: str                      # who opens the session, e.g. a Tuttie subagent's id
    purpose: str = "negotiation"
    context: dict = {}             # what the peer chose to share (never its private context)


class SessionMessageRequest(BaseModel):
    message: str


class BookRequest(BaseModel):
    date: str
    room_type: str
    guest_name: str
    extras: list[dict] = []  # signed A2A envelopes from this node that carry a commitment
    approval: dict  # the user's signed decision, see aps/approval.py
    agreement: dict | None = None  # this node's signed Agreement from a negotiation (negotiation/agreement.py)


def create_app(config: dict, http: httpx.AsyncClient | None = None, lookup=registry_lookup) -> FastAPI:
    """Build the FastAPI app for one node config.

    `http` is the client used to send offers to the marketplace, `lookup` how the bargaining tool
    finds registry records (tests pass in-process ones for both).
    """
    node_id = config["node_id"]
    facts = config.get("facts", {})
    signing_key = load_signing_key(node_id)
    own_public_key = public_key_b64(signing_key)
    user_public_key = load_public_key("user")
    used_approvals: set[str] = set()
    agreements = AgreementRedeemer(node_id, own_public_key)  # negotiated prices, each bookable once
    business_agent = BusinessAgent(config)
    sessions = SessionStore(owner=node_id)
    background: set[asyncio.Task] = set()  # offers being prepared and sent
    app = FastAPI(title=config["name"])

    def signed(payload: dict) -> dict:
        """Wrap a response payload in this node's signed envelope."""
        return sign_envelope(node_id, payload, signing_key)

    @app.post("/tools/get_availability")
    def get_availability(req: AvailabilityRequest) -> dict:
        """Signed list of available rooms and prices for a date."""
        rooms = [
            {k: room[k] for k in ("room_type", "price_chf", "rate")}
            for room in facts.get("rooms", []) if room.get("available")
        ]
        return signed({
            "tool": "get_availability",
            "hotel": config["name"],
            "date": req.date,
            "guests": req.guests,
            "currency": "CHF",
            "rooms": rooms,
        })

    @app.post("/tools/get_policies")
    def get_policies() -> dict:
        """Signed policies: who the business is (size), location, quietness, dogs, check-in, cancellation."""
        return signed({
            "tool": "get_policies",
            "hotel": config["name"],
            "profile": facts.get("profile"),
            "address": facts.get("address"),
            "distance_to_basel_sbb_m": facts.get("distance_to_basel_sbb_m"),
            "quiet": facts.get("quiet"),
            "quiet_note": facts.get("quiet_note"),
            "policies": facts.get("policies", {}),
        })

    @app.post("/tools/book")
    def book(req: BookRequest) -> dict:
        """Confirm a booking only with the user's signed approval for exactly this total.

        The total is either a negotiated price (this node's own signed Agreement, redeemed
        once) or the room's price plus extras, which are this node's own signed A2A
        commitments: either way the price is the one the node promised, whatever the caller
        claims.
        """
        def refuse(reason: str) -> dict:
            """A signed refusal with the reason."""
            return signed({"tool": "book", "status": "refused", "reason": reason})

        approval = req.approval
        if not verify_decision(approval, user_public_key):
            return refuse("approval is not signed by the user")
        if (approval["action"], approval["payee_node_id"], approval["decision"]) != ("book", node_id, "approved"):
            return refuse("approval does not approve a booking with this hotel")
        if approval["approval_id"] in used_approvals:
            return refuse("approval was already used")
        agreement = None
        if req.agreement is not None:
            try:
                agreement = agreements.check(req.agreement)
            except AgreementInvalid as error:
                return refuse(str(error))
            total, items = agreement.price_chf, list(agreement.includes)
        else:
            room = next((r for r in facts.get("rooms", []) if r["room_type"] == req.room_type and r.get("available")), None)
            if room is None:
                return refuse(f"no available room of type {req.room_type}")
            total, items = room["price_chf"], []
            for extra in req.extras:
                commitment = extra.get("payload", {}).get("commitment") if isinstance(extra, dict) else None
                if not commitment or not verify_envelope(extra, own_public_key, expected_node_id=node_id):
                    return refuse("an extra is not a commitment signed by this hotel")
                total += commitment["price_chf"]
                items.append(commitment["item"])
        if round(total, 2) != round(approval["amount_chf"], 2):
            return refuse(f"approved CHF {approval['amount_chf']} does not match total CHF {total}")

        used_approvals.add(approval["approval_id"])
        if agreement is not None:
            agreements.mark_used(agreement)
        return signed({
            "tool": "book",
            "status": "confirmed",
            "booking_id": "BK-" + secrets.token_hex(3).upper(),
            "hotel": config["name"],
            "date": req.date,
            "room_type": req.room_type,
            "guest_name": req.guest_name,
            "extras": items,
            "total_chf": total,
            "approval_id": approval["approval_id"],
            "arrival": facts.get("policies", {}).get("late_arrival"),
        })

    @app.post("/agent")
    async def agent(req: AgentRequest) -> dict:
        """The company's agent answers another agent (A2A), signed."""
        return signed(await business_agent.answer(req.question, req.context))

    @app.get("/agent/card")
    def agent_card() -> dict:
        """The agent's signed card: persona, tools and the events it wakes on."""
        return signed(business_agent.card())

    def find_session(session_id: str):
        try:
            return sessions.get(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="no such session") from None

    @app.post("/agent/sessions")
    def open_session(req: SessionOpenRequest) -> dict:
        """Open an isolated conversation with its own memory (one per negotiation)."""
        session = sessions.open(req.peer, req.purpose, req.context)
        session.add("system", "opened", {"peer": req.peer, "purpose": req.purpose})
        return signed({"session_id": session.id, "agent": business_agent.persona["name"], "purpose": req.purpose})

    @app.post("/agent/sessions/{session_id}/messages")
    async def session_message(session_id: str, req: SessionMessageRequest) -> dict:
        """Answer a message inside a session; the agent sees the session's history."""
        session = find_session(session_id)
        async with session.lock:  # turns of one session stay in order; other sessions run in parallel
            try:
                session.add("peer", "message", {"text": req.message})
            except SessionClosed:
                raise HTTPException(status_code=409, detail="session is closed") from None
            reply = await business_agent.answer(req.message, session.context, history=session.transcript()[:-1])
            session.add("self", "reply", reply)
        return signed({"session_id": session.id, "turn": len(session.turns), **reply})

    @app.get("/agent/sessions/{session_id}")
    def read_session(session_id: str) -> dict:
        """The session's whole memory, signed (for audits and the timeline)."""
        return signed(find_session(session_id).to_dict())

    @app.post("/agent/sessions/{session_id}/close")
    def close_session(session_id: str) -> dict:
        """End a session; its memory stays readable."""
        find_session(session_id)
        return signed({"session_id": session_id, "status": sessions.close(session_id).status})

    @app.post("/agent/invoke")
    async def agent_invoke(event: dict = Body(...)) -> dict:
        """The marketplace wakes the agent on a change; it answers whether and how it would respond.

        The body is the event itself, e.g. {"type": "posting.created", "posting": {...}}
        (marketplace/messages.py, PostingCreated).
        """
        decision = await business_agent.invoke(event)
        if (event.get("type") == "posting.created" and decision.get("interested")
                and decision.get("next_tool") == "make_offer"):
            task = asyncio.create_task(send_offer(event["posting"]))  # the market need not wait for it
            background.add(task)
            task.add_done_callback(background.discard)
        return signed(decision)

    async def send_offer(posting: dict) -> None:
        """make_offer: let the agent compose an offer and post it, signed, to the market."""
        offer = await business_agent.make_offer(posting)
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
    uvicorn.run(create_app(config), host="0.0.0.0", port=args.port or config["port"])


if __name__ == "__main__":
    main()
