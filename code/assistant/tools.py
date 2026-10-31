"""Tools the LLM may call, each wrapped in the APS trust gate.

Before the LLM sees any result, the node's registry record is checked against
data/authorities.json and every response envelope is verified with the node's
key. Anything that fails is replaced by {"rejected": true, "reason": ...} and
shown in red on the timeline. The node is never even contacted when its seals
are broken.

Results carry "source_step", the timeline step that proves them, so the final
answer can cite its sources.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from aps import evaluate_record, verify_envelope
from assistant.approvals import ApprovalBook
from assistant.events import EventBus

AUTHORITIES_PATH = Path(__file__).resolve().parent.parent / "data" / "authorities.json"
TOOL_NAME = re.compile(r"^[a-z_]{1,40}$")
NODE_ID = re.compile(r"^[a-z0-9.-]{1,80}$")
# Tools the assistant may call freely; book needs the user's approval first.
READ_TOOLS = {"get_availability", "get_policies"}


def function(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    parameters = {"type": "object", "properties": properties, "required": required or []}
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


SCHEMAS = [
    function(
        "search_registry",
        "Find nodes on the agent web by tags (all must match) and/or a capability. "
        "Results are seal-checked: use only 'verified', never 'rejected'.",
        {
            "tags": {"type": "array", "items": {"type": "string"},
                     "description": "Known tags: hotel, basel-sbb, dog-friendly, quiet, family, legal, consumer-law, switzerland"},
            "capability": {"type": "string", "enum": ["can_book", "can_take_payment", "licensed_legal_ch"],
                           "description": "Optional. Omit it for hotels; tags are enough."},
        },
    ),
    function(
        "call_tool",
        "Call a signed tool on a verified node (A2T). The response is signature-checked.",
        {
            "node_id": {"type": "string"},
            "tool": {"type": "string", "enum": sorted(READ_TOOLS)},
            "args": {"type": "object",
                     "description": "get_availability: {date: YYYY-MM-DD, guests: int}; get_policies: {}"},
        },
        ["node_id", "tool"],
    ),
    function(
        "ask_agent",
        "Ask a verified node's own agent a question its signed facts do not settle (A2A). "
        "Returns a signed answer and possibly a commitment (a priced promise you can book as an extra).",
        {"node_id": {"type": "string"}, "question": {"type": "string"}},
        ["node_id", "question"],
    ),
    function(
        "book",
        "Book a room on a verified node. Needs a get_availability for that date first. "
        "Waits until the user approves or declines on their phone.",
        {
            "node_id": {"type": "string"},
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "room_type": {"type": "string"},
            "guest_name": {"type": "string"},
            "extras": {"type": "array", "items": {"type": "string"},
                       "description": "'item' names of commitments from ask_agent to include"},
        },
        ["node_id", "date", "room_type", "guest_name"],
    ),
]


@dataclass
class Verified:
    record: dict
    verdict: dict
    envelope: dict

    @property
    def payload(self) -> dict:
        return self.envelope["payload"]


def load_authorities() -> dict:
    return {a["issuer"]: a for a in json.loads(AUTHORITIES_PATH.read_text())}


def rejected(record: dict, reason: str) -> dict:
    return {"node_id": record.get("node_id"), "name": record.get("name"), "rejected": True, "reason": reason}


def node_view(record: dict, verdict: dict) -> dict:
    """What the LLM gets to know about a verified node."""
    return {
        "node_id": record["node_id"],
        "name": record["name"],
        "kind": record["kind"],
        "trust_tier": verdict["tier"],
        "verified_by": [s["issuer"] for s in verdict["seals"]],
        "capabilities": verdict["capabilities"],
        "tags": record["tags"],
    }


def broken_reason(verdict: dict) -> str:
    failed = [f"{s['issuer']}/{s['tier']}" for s in verdict["seals"] if not s["valid"]]
    return f"seal does not verify: {', '.join(failed)}" if failed else "no seals"


def summarize(tool: str, payload: dict) -> str:
    if payload.get("rooms"):
        rooms = ", ".join(f"{r['room_type']} CHF {r['price_chf']}" for r in payload["rooms"])
        return f"{tool} {payload.get('date', '')}: {rooms}"
    if "policies" in payload:
        dogs = "dogs allowed" if payload["policies"].get("dogs_allowed") else "no dogs"
        return f"{tool}: {dogs}, {payload['policies'].get('late_arrival', '')}"
    return tool


class Toolbox:
    def __init__(self, http: httpx.AsyncClient, registry_url: str, bus: EventBus, approvals: ApprovalBook):
        self.http = http
        self.registry_url = registry_url.rstrip("/")
        self.bus = bus
        self.approvals = approvals
        self.authorities = load_authorities()
        self.reset()

    def reset(self) -> None:
        # Signed facts remembered for booking, so prices never come from the LLM.
        self.availability: dict[str, dict] = {}  # node_id -> last get_availability payload
        self.commitments: dict[str, list[dict]] = {}  # node_id -> signed A2A envelopes with a commitment
        self.seen: dict[str, int] = {}  # node_id -> timeline step of its registry check, shown once

    async def dispatch(self, name: str, args: dict) -> dict:
        tools = {"search_registry": self.search_registry, "call_tool": self.call_tool,
                 "ask_agent": self.ask_agent, "book": self.book}
        if name not in tools:
            return {"error": f"unknown tool {name}"}
        return await tools[name](**args)

    async def search_registry(self, tags: list[str] | None = None, capability: str = "") -> dict:
        params = {"tags": ",".join(tags or []), "capability": capability}
        records = (await self.http.get(f"{self.registry_url}/search", params=params)).json()
        verified, refused = [], []
        for record in records:
            verdict = evaluate_record(record, self.authorities)
            if verdict["tier"] == "broken":
                reason = broken_reason(verdict)
                self.emit_once(record, "broken", f"{record['name']}: {reason}, ignored", verdict)
                refused.append(rejected(record, reason))
            else:
                step = self.emit_once(record, "verified", f"{record['name']}: {verdict['tier']} seal verified", verdict)
                verified.append({**node_view(record, verdict), "source_step": step})
        result = {"query": params, "verified": verified, "rejected": refused}
        if not records:
            everything = (await self.http.get(f"{self.registry_url}/search")).json()
            known = sorted({tag for record in everything for tag in record["tags"]})
            result["hint"] = f"No node has all these tags. Search with fewer tags; known tags: {known}"
        return result

    def emit_once(self, record: dict, status: str, summary: str, verdict: dict) -> int:
        """Show a node's registry check on the timeline only the first time it is found."""
        if record["node_id"] not in self.seen:
            event = self.bus.emit("registry", status, summary, record, verdict["seals"],
                                  {"capabilities": verdict["capabilities"]})
            self.seen[record["node_id"]] = event["step"]
        return self.seen[record["node_id"]]

    async def lookup(self, node_id: str) -> tuple[dict, dict] | None:
        if not NODE_ID.match(node_id):
            return None
        response = await self.http.get(f"{self.registry_url}/nodes/{node_id}")
        if response.status_code != 200:
            return None
        record = response.json()
        return record, evaluate_record(record, self.authorities)

    async def verified_post(self, node_id: str, path: str, body: dict, kind: str, label: str) -> Verified | dict:
        """Check the node's seals, call it, and verify the signed envelope it returns.

        Returns Verified, or a rejection dict for the LLM (already shown on the timeline).
        """
        found = await self.lookup(node_id)
        if found is None:
            return {"node_id": node_id, "rejected": True, "reason": "not in the registry"}
        record, verdict = found
        if verdict["tier"] == "broken":
            reason = broken_reason(verdict)
            self.bus.emit(kind, "broken", f"{label} refused: {reason}", record, verdict["seals"])
            return rejected(record, reason)

        envelope = (await self.http.post(f"{record['endpoint']}{path}", json=body)).json()
        if not verify_envelope(envelope, record["public_key"], expected_node_id=node_id):
            self.bus.emit(kind, "broken", f"{label}: response signature invalid, dropped", record, verdict["seals"])
            return rejected(record, "response signature does not verify")
        return Verified(record, verdict, envelope)

    def emit_verified(self, kind: str, summary: str, result: Verified) -> int:
        event = self.bus.emit(kind, "verified", summary, result.record, result.verdict["seals"],
                              {"timestamp": result.envelope["timestamp"], "payload": result.payload})
        return event["step"]

    async def call_tool(self, node_id: str, tool: str, args: dict | None = None) -> dict:
        if tool not in READ_TOOLS or not TOOL_NAME.match(tool):
            return {"error": f"tool {tool} is not available through call_tool"}
        result = await self.verified_post(node_id, f"/tools/{tool}", args or {}, "a2t", tool)
        if not isinstance(result, Verified):
            return result
        if tool == "get_availability":
            self.availability[node_id] = result.payload
        step = self.emit_verified("a2t", summarize(tool, result.payload), result)
        return {"node_id": node_id, "trust_tier": result.verdict["tier"], "source_step": step, "data": result.payload}

    async def ask_agent(self, node_id: str, question: str) -> dict:
        result = await self.verified_post(node_id, "/agent", {"question": question, "context": {}}, "a2a", "ask_agent")
        if not isinstance(result, Verified):
            return result
        reply = result.payload
        summary = f"Q: {question}  A: {reply.get('answer', '')}"
        if commitment := reply.get("commitment"):
            self.commitments.setdefault(node_id, []).append(result.envelope)
            summary += f"  Commitment: {commitment['item']}, CHF {commitment['price_chf']:g}"
        step = self.emit_verified("a2a", summary, result)
        return {"node_id": node_id, "trust_tier": result.verdict["tier"], "source_step": step, **reply}

    async def book(self, node_id: str, date: str, room_type: str, guest_name: str,
                   extras: list[str] | None = None) -> dict:
        found = await self.lookup(node_id)
        if found is None or found[1]["tier"] == "broken" or "can_book" not in found[1]["capabilities"]:
            return {"node_id": node_id, "rejected": True, "reason": "node is not verified for bookings"}
        record, verdict = found

        availability = self.availability.get(node_id)
        if not availability or availability.get("date") != date:
            return {"error": f"call get_availability on {node_id} for {date} first"}
        room = next((r for r in availability["rooms"] if r["room_type"] == room_type), None)
        if room is None:
            return {"error": f"room_type must be one of {[r['room_type'] for r in availability['rooms']]}"}
        offered = {env["payload"]["commitment"]["item"]: env for env in self.commitments.get(node_id, [])}
        missing = [item for item in extras or [] if item not in offered]
        if missing:
            return {"error": f"unknown extras {missing}; signed commitments available: {list(offered)}"}

        chosen = [offered[item] for item in extras or []]
        amount = room["price_chf"] + sum(env["payload"]["commitment"]["price_chf"] for env in chosen)
        parts = [f"{room_type} CHF {room['price_chf']:g}"]
        parts += [f"{env['payload']['commitment']['item']} CHF {env['payload']['commitment']['price_chf']:g}"
                  for env in chosen]
        summary = f"Book {record['name']}, {date}: {' + '.join(parts)} = CHF {amount:g}"

        approval = self.approvals.create("book", record, amount, summary, verdict["seals"])
        self.bus.emit("approval", "pending", f"Waiting for your phone. {summary}", record, verdict["seals"],
                      {"approval_id": approval["id"], "amount_chf": amount})
        decision = await self.approvals.wait(approval["id"])
        step = self.bus.emit("approval", decision["decision"], f"You {decision['decision']} CHF {amount:g} on your phone"
                             " (signed with your key)", record, verdict["seals"], {"decision": decision})["step"]
        if decision["decision"] != "approved":
            return {"declined": True, "source_step": step}

        body = {"date": date, "room_type": room_type, "guest_name": guest_name, "extras": chosen, "approval": decision}
        result = await self.verified_post(node_id, "/tools/book", body, "a2t", "book")
        if not isinstance(result, Verified):
            return result
        confirmation = result.payload
        if confirmation.get("status") == "confirmed":
            text = f"book: confirmed {confirmation['booking_id']}, CHF {confirmation['total_chf']:g}"
        else:
            text = f"book refused by hotel: {confirmation.get('reason')}"
        step = self.emit_verified("a2t", text, result)
        return {"node_id": node_id, "source_step": step, **confirmation}
