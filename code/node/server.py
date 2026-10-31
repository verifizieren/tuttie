"""Generic business node: one FastAPI app, started once per config in data/nodes/.

Usage: python -m node.server --config data/nodes/hotel-rheinblick.json [--port 4001]

Every response is a signed envelope from this node's key (keys/<node_id>.json).
Tools and the /agent endpoint answer only from the config's "facts".
"""

import argparse
import json
import secrets
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from aps import load_signing_key, public_key_b64, sign_envelope, verify_envelope
from aps.approval import verify_decision
from aps.keys import load_public_key
from node.agent import NodeAgent


class AvailabilityRequest(BaseModel):
    date: str
    guests: int = 1


class AgentRequest(BaseModel):
    question: str
    context: dict = {}


class BookRequest(BaseModel):
    date: str
    room_type: str
    guest_name: str
    extras: list[dict] = []  # signed A2A envelopes from this node that carry a commitment
    approval: dict  # the user's signed decision, see aps/approval.py


def create_app(config: dict) -> FastAPI:
    """Build the FastAPI app for one node config."""
    node_id = config["node_id"]
    facts = config.get("facts", {})
    signing_key = load_signing_key(node_id)
    own_public_key = public_key_b64(signing_key)
    user_public_key = load_public_key("user")
    used_approvals: set[str] = set()
    node_agent = NodeAgent(config)
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
        """Signed policies: location, quietness, dogs, check-in, cancellation."""
        return signed({
            "tool": "get_policies",
            "hotel": config["name"],
            "address": facts.get("address"),
            "distance_to_basel_sbb_m": facts.get("distance_to_basel_sbb_m"),
            "quiet": facts.get("quiet"),
            "quiet_note": facts.get("quiet_note"),
            "policies": facts.get("policies", {}),
        })

    @app.post("/tools/book")
    def book(req: BookRequest) -> dict:
        """Confirm a booking only with the user's signed approval for exactly this total.

        Extras are this node's own signed A2A commitments, so their price is the one
        the node promised, whatever the caller claims.
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
        """The node's own agent answers another agent (A2A), signed."""
        return signed(await node_agent.answer(req.question, req.context))

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
