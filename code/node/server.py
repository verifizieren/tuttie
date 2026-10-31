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
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel, ValidationError

from aps import load_signing_key, public_key_b64, sign_envelope, verify_envelope
from aps.call import call_body
from aps.gate import ActionGate, Needs
from aps.keys import load_public_key
from negotiation.agreement import AgreementRedeemer
from negotiation.hotel import counter_offer_mcp_tool, counter_offer_router, load_authorities, registry_lookup
from node.agent import BusinessAgent
from node.deployments import DeploymentStore
from node.mcp_tools import mcp_app, mcp_server
from node.owner import owner_app
from node.settings import apply as apply_settings
from node.settings import validate as validate_settings
from sessions import SessionClosed, SessionStore


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
    gate = ActionGate(node_id, own_public_key, load_public_key("user"), load_authorities(), lookup, agreements)
    bookings: set[str] = set()  # booking ids confirmed here, so charges can follow them
    paid: set[tuple[str, str]] = set()  # (booking id, purpose) already charged
    business_agent = BusinessAgent(config)
    sessions = SessionStore(owner=node_id)
    background: set[asyncio.Task] = set()  # offers being prepared and sent

    def signed(payload: dict) -> dict:
        """Wrap a response payload in this node's signed envelope."""
        return sign_envelope(node_id, payload, signing_key)

    def get_availability(date: str, guests: int = 1) -> dict:
        """Signed list of available rooms and prices for a date."""
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
        for "book" and the user's approval for exactly that amount. The confirmation lists the
        checks it rests on.
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
        total, items = None, []
        if req.agreement is None:
            room = next((r for r in facts().get("rooms", []) if r["room_type"] == req.room_type and r.get("available")), None)
            if room is None:
                return refuse(f"no available room of type {req.room_type}")
            total = room["price_chf"]
            for extra in req.extras:
                commitment = extra.get("payload", {}).get("commitment") if isinstance(extra, dict) else None
                if not commitment or not verify_envelope(extra, own_public_key, expected_node_id=node_id):
                    return refuse("an extra is not a commitment signed by this hotel")
                total += commitment["price_chf"]
                items.append(commitment["item"])

        verdict = await gate.check_action(call, Needs("book", scope="book", approval=True, amount_chf=total))
        if not verdict.ok:
            return refuse(verdict.reason)
        if verdict.agreement is not None:
            items = list(verdict.agreement.includes)
        gate.commit(verdict)  # the approval and the agreement cannot be used again
        booking_id = "BK-" + secrets.token_hex(3).upper()
        bookings.add(booking_id)
        return signed({
            "tool": "book",
            "status": "confirmed",
            "booking_id": booking_id,
            "hotel": config["name"],
            "date": req.date,
            "room_type": req.room_type,
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
                                                      amount_chf=charge["price_chf"], purpose=purpose))
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

    app = FastAPI(title=config["name"], lifespan=lifespan)
    app.state.mcp = tools  # in-process MCP clients (tests, headless demo) connect to this directly
    app.mount("/mcp", mcp_app(tools))
    # The owner view (apps/owner): read the live business, deploy new settings (node/owner.py).
    app.mount("/owner", owner_app(config, store, lambda: business_agent.apply(config)))

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
