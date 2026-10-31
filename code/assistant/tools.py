"""Tools the LLM may call, each wrapped in the APS trust gate.

Before the LLM sees any result, the node's registry record is checked against
data/authorities.json and every response envelope is verified with the node's
key. Anything that fails is replaced by {"rejected": true, "reason": ...} and
shown in red on the timeline. The node is never even contacted when its seals
are broken.

A business's tools are called over MCP (assistant/mcp_client.py). Reading tools are open;
`book` goes out as a call signed with Tuttie's key and carrying the user's delegation
(aps/call.py), so the hotel knows who asks and that the call is not replayed.

Results carry "source_step", the timeline step that proves them, so the final
answer can cite its sources.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from aps import evaluate_record, load_signing_key, verify_envelope
from aps.call import sign_call
from aps.delegation import verify_delegation
from aps.envelope import is_fresh
from aps.keys import load_public_key
from assistant.approvals import ApprovalBook
from assistant.marketplace import MarketDesk
from assistant.mcp_client import McpCallFailed, McpLink
from sessions import Context
from assistant.events import EventBus

AUTHORITIES_PATH = Path(__file__).resolve().parent.parent / "data" / "authorities.json"
TOOL_NAME = re.compile(r"^[a-z_]{1,40}$")
NODE_ID = re.compile(r"^[a-z0-9.-]{1,80}$")
# Tools the assistant may call freely; book needs the user's approval first.
READ_TOOLS = {"get_availability", "get_policies"}
# Node replies must be this fresh, so an old signed reply (e.g. an outdated price) cannot be replayed.
MAX_REPLY_AGE_S = 300


def function(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    """A tool definition in the chat-completions schema (llm.py converts it)."""
    parameters = {"type": "object", "properties": properties, "required": required or []}
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


SCHEMAS = [
    function(
        "post_request",
        "Post the user's request on the marketplace: matching verified businesses are woken and "
        "send signed offers; returns the shortlist (verified, within budget, cheapest first). "
        "Use this first when the user looks for a hotel.",
        {
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "guests": {"type": "integer"},
            "requirements": {"type": "array", "items": {"type": "string"},
                             "description": "public needs, e.g. [\"quiet\", \"dog\", \"arrival around 01:00\"]"},
            "tags": {"type": "array", "items": {"type": "string", "enum": ["basel", "basel-sbb", "kleinbasel"]},
                     "description": "only the place: \"basel\" for the whole city, \"basel-sbb\" or \"kleinbasel\" "
                                    "only if the user named that area; everything else (quiet, dog, ...) goes into requirements"},
            "budget_chf": {"type": "number",
                           "description": "the user's price limit. PRIVATE: it is never posted, only used for the shortlist"},
        },
        ["date"],
    ),
    function(
        "negotiate",
        "Bargain with every hotel on the last shortlist at once (one subagent each) and return the "
        "best signed agreement. Use it only when the user asks for a better price or to negotiate.",
        {"budget_chf": {"type": "number",
                        "description": "the user's price limit. PRIVATE: only compared by Tuttie's code, never sent"}},
    ),
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
            "use_agreement": {"type": "boolean",
                              "description": "book the price agreed in the last negotiate with this hotel "
                                             "(no get_availability or extras needed)"},
        },
        ["node_id", "date", "room_type", "guest_name"],
    ),
]


@dataclass
class Verified:
    """A node response that passed the trust gate: its record, verdict and signed envelope."""
    record: dict
    verdict: dict
    envelope: dict

    @property
    def payload(self) -> dict:
        return self.envelope["payload"]


def load_authorities() -> dict:
    """The trusted authorities from data/authorities.json, by issuer id."""
    return {a["issuer"]: a for a in json.loads(AUTHORITIES_PATH.read_text())}


def rejected(record: dict, reason: str) -> dict:
    """What the LLM sees instead of a node that failed verification."""
    return {"node_id": record.get("node_id"), "name": record.get("name"), "rejected": True, "reason": reason}


def node_view(record: dict, verdict: dict) -> dict:
    """What the LLM gets to know about a verified node."""
    return {
        "node_id": record["node_id"],
        "name": record["name"],
        "kind": record["kind"],
        "trust_tier": verdict["tier"],
        "uid": verdict["uid"],  # only set when the commercial register vouched for it
        "verified_by": [s["issuer"] for s in verdict["seals"]],
        "capabilities": verdict["capabilities"],
        "tags": record["tags"],
    }


def broken_reason(verdict: dict) -> str:
    """A short reason why a node's seals failed, for the LLM and the timeline."""
    failed = [f"{s['issuer']}/{s['tier']}" for s in verdict["seals"] if not s["valid"]]
    return f"seal does not verify: {', '.join(failed)}" if failed else "no seals"


def verified_summary(record: dict, verdict: dict) -> str:
    """Timeline text for a node whose seals verified; grey nodes are called untrusted."""
    if verdict["tier"] != "grey":
        return f"{record['name']}: {verdict['tier']} seal verified"
    signed = "no seals (unsigned)" if not verdict["seals"] else "self-signed only"
    unlicensed = [c for c in record["capabilities"] if c not in verdict["capabilities"] and c.startswith("licensed_")]
    claim = f", claims {', '.join(unlicensed)} without a valid licence" if unlicensed else ""
    return f"{record['name']}: {signed}, untrusted{claim}"


def summarize(tool: str, payload: dict) -> str:
    """A one-line timeline summary of a signed tool response."""
    if payload.get("rooms"):
        rooms = ", ".join(f"{r['room_type']} CHF {r['price_chf']}" for r in payload["rooms"])
        return f"{tool} {payload.get('date', '')}: {rooms}"
    if "policies" in payload:
        dogs = "dogs allowed" if payload["policies"].get("dogs_allowed") else "no dogs"
        return f"{tool}: {dogs}, {payload['policies'].get('late_arrival', '')}"
    return tool


class Toolbox:
    """The tools the LLM can call; every result passes the APS trust gate first."""

    def __init__(self, http: httpx.AsyncClient, registry_url: str, bus: EventBus, approvals: ApprovalBook,
                 market: MarketDesk | None = None, mcp: McpLink | None = None):
        self.http = http
        self.mcp = mcp or McpLink()
        self.registry_url = registry_url.rstrip("/")
        self.bus = bus
        self.approvals = approvals
        self.authorities = load_authorities()
        self.market = market or MarketDesk(http, registry_url, bus, self.authorities)
        self.user_public_key = load_public_key("user")  # checks that Tuttie really acts for this user
        self.reset()

    def reset(self) -> None:
        # Signed facts remembered for booking, so prices never come from the LLM.
        """Forget the signed facts of the last conversation."""
        self.availability: dict[str, dict] = {}  # node_id -> last get_availability payload
        self.commitments: dict[str, list[dict]] = {}  # node_id -> signed A2A envelopes with a commitment
        self.agreements: dict[str, dict] = {}  # node_id -> the hotel's signed Agreement from the last negotiation
        self.seen: dict[str, int] = {}  # node_id -> timeline step of its registry check, shown once

    async def dispatch(self, name: str, args: dict) -> dict:
        """Run a tool by name with the LLM's arguments."""
        tools = {"post_request": self.market.find, "negotiate": self.negotiate, "search_registry": self.search_registry,
                 "call_tool": self.call_tool, "ask_agent": self.ask_agent, "book": self.book}
        if name not in tools:
            return {"error": f"unknown tool {name}"}
        return await tools[name](**args)

    async def negotiate(self, budget_chf: float | None = None) -> dict:
        """Bargain over the last shortlist with dev member 2's negotiator (code/negotiation/).

        Only the date and the needs are shared with the hotels; the budget is a private context
        item that the negotiator compares in code and never sends.
        """
        # Imported here: negotiation builds on this module (Toolbox, Verified).
        from negotiation.tuttie import BUDGET_LIMIT, TuttieNegotiator, best
        from assistant.subagents import SubagentPool

        if not self.market.last_shortlist:
            return {"error": "post a request first: there is no shortlist to negotiate"}
        needs = self.market.last_request["constraints"]
        context = Context().add("date", needs["date"], "public").add("requirements", needs["requirements"], "negotiation")
        if budget_chf is not None:
            context.add(BUDGET_LIMIT, budget_chf, "private")
        negotiator = TuttieNegotiator(SubagentPool(self), self.market.agent_id, load_signing_key(self.market.agent_id))
        outcomes = await negotiator.negotiate_all(self.market.last_shortlist, context)
        winner = best(outcomes)
        self.agreements.update({o.node_id: o.agreement for o in outcomes if o.status == "agreed"})
        names = {o["node_id"]: o["name"] for o in self.market.last_shortlist}
        summary = (f"Best agreement: {names[winner.node_id]} at CHF {winner.price_chf:g} "
                   f"(offered CHF {winner.offer_price_chf:g})") if winner else "No hotel agreed within the budget"
        self.bus.emit("marketplace", "verified" if winner else "declined", summary,
                      detail={"phase": "agreement", "agreement": winner.agreement if winner else None})
        return {
            "outcomes": [{"hotel": names[o.node_id], "status": o.status, "offered_chf": o.offer_price_chf,
                          "agreed_chf": o.price_chf, "rounds": o.rounds, "reason": o.reason} for o in outcomes],
            "best": {"hotel": names[winner.node_id], "price_chf": winner.price_chf,
                     "offer_id": winner.offer_id} if winner else None,
        }

    async def search_registry(self, tags: list[str] | None = None, capability: str = "") -> dict:
        """Find nodes and split them into verified and rejected; each node shows once on the timeline."""
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
                status = "untrusted" if verdict["tier"] == "grey" else "verified"
                step = self.emit_once(record, status, verified_summary(record, verdict), verdict)
                verified.append({**node_view(record, verdict), "source_step": step})
        result = {"query": params, "verified": verified, "rejected": refused}
        if not records:
            everything = (await self.http.get(f"{self.registry_url}/search")).json()
            known = sorted({tag for record in everything for tag in record["tags"]})
            result["hint"] = f"No node has all these tags. Search with fewer tags; known tags: {known}"
        return result

    async def identity(self, agent_id: str) -> dict:
        """The verified identity of a user agent (Tuttie), for the wallet to show.

        Checks the agent's seals like any node and, on top, that the user's key signed
        a delegation for exactly this agent and key. Not shown on the timeline.
        """
        found = await self.lookup(agent_id)
        if found is None:
            return {"node_id": agent_id, "rejected": True, "reason": "not in the registry"}
        record, verdict = found
        if verdict["tier"] == "broken":
            return rejected(record, broken_reason(verdict))
        delegation = record.get("delegation") or {}
        acts_for_user = verify_delegation(delegation, self.user_public_key, record["node_id"], record["public_key"])
        return {
            **node_view(record, verdict),
            "acts_for_user": acts_for_user,
            "scopes": delegation.get("scopes", []) if acts_for_user else [],
            "delegation_expires_at": delegation.get("expires_at") if acts_for_user else None,
        }

    def emit_once(self, record: dict, status: str, summary: str, verdict: dict) -> int:
        """Show a node's registry check on the timeline only the first time it is found."""
        if record["node_id"] not in self.seen:
            event = self.bus.emit("registry", status, summary, record, verdict["seals"],
                                  {"capabilities": verdict["capabilities"]})
            self.seen[record["node_id"]] = event["step"]
        return self.seen[record["node_id"]]

    async def lookup(self, node_id: str) -> tuple[dict, dict] | None:
        """A node's registry record and trust verdict, or None if it is unknown."""
        if not NODE_ID.match(node_id):
            return None
        response = await self.http.get(f"{self.registry_url}/nodes/{node_id}")
        if response.status_code != 200:
            return None
        record = response.json()
        return record, evaluate_record(record, self.authorities)

    async def verified_post(self, node_id: str, path: str, body: dict, kind: str, label: str) -> Verified | dict:
        """Check the node's seals, POST to one of its agent endpoints, and verify the signed reply.

        Returns Verified, or a rejection dict for the LLM (already shown on the timeline).
        """
        async def send(record: dict) -> dict:
            return (await self.http.post(f"{record['endpoint']}{path}", json=body)).json()
        return await self.verified(node_id, send, kind, label)

    async def verified_mcp(self, node_id: str, tool: str, args: dict, kind: str, label: str) -> Verified | dict:
        """Check the node's seals, call one of its MCP tools, and verify the signed reply."""
        async def send(record: dict) -> dict:
            return await self.mcp.call(record["endpoint"], tool, args)
        return await self.verified(node_id, send, kind, label)

    async def verified(self, node_id: str, send, kind: str, label: str) -> Verified | dict:
        """The trust gate around one call: seals first, then `send(record)`, then the envelope."""
        found = await self.lookup(node_id)
        if found is None:
            return {"node_id": node_id, "rejected": True, "reason": "not in the registry"}
        record, verdict = found
        if verdict["tier"] == "broken":
            reason = broken_reason(verdict)
            self.bus.emit(kind, "broken", f"{label} refused: {reason}", record, verdict["seals"])
            return rejected(record, reason)

        try:
            envelope = await send(record)
        except (httpx.HTTPError, McpCallFailed, ValueError) as error:
            self.bus.emit(kind, "broken", f"{label}: {record['name']} did not answer", record, verdict["seals"])
            return rejected(record, f"unreachable: {error}")
        if not verify_envelope(envelope, record["public_key"], expected_node_id=node_id):
            self.bus.emit(kind, "broken", f"{label}: response signature invalid, dropped", record, verdict["seals"])
            return rejected(record, "response signature does not verify")
        if not is_fresh(envelope["timestamp"], MAX_REPLY_AGE_S):
            self.bus.emit(kind, "broken", f"{label}: signed reply is outdated, dropped", record, verdict["seals"])
            return rejected(record, "signed reply is outdated (possible replay)")
        return Verified(record, verdict, envelope)

    async def signed_call(self, tool: str, args: dict) -> dict:
        """A call of an action tool signed with Tuttie's key, with the user's delegation attached."""
        agent_id = self.market.agent_id
        found = await self.lookup(agent_id)
        delegation = found[0].get("delegation") if found else None
        return sign_call(tool, args, agent_id, load_signing_key(agent_id), delegation)

    def emit_verified(self, kind: str, summary: str, result: Verified) -> int:
        """Signature checked; the step is still "untrusted" when the node itself is only grey."""
        status = "untrusted" if result.verdict["tier"] == "grey" else "verified"
        event = self.bus.emit(kind, status, summary, result.record, result.verdict["seals"],
                              {"timestamp": result.envelope["timestamp"], "payload": result.payload})
        return event["step"]

    async def call_tool(self, node_id: str, tool: str, args: dict | None = None) -> dict:
        """Call a read-only tool on a node and return its verified payload."""
        if tool not in READ_TOOLS or not TOOL_NAME.match(tool):
            return {"error": f"tool {tool} is not available through call_tool"}
        result = await self.verified_mcp(node_id, tool, args or {}, "a2t", tool)
        if not isinstance(result, Verified):
            return result
        if tool == "get_availability":
            self.availability[node_id] = result.payload
        step = self.emit_verified("a2t", summarize(tool, result.payload), result)
        return {"node_id": node_id, "trust_tier": result.verdict["tier"], "source_step": step, "data": result.payload}

    async def ask_agent(self, node_id: str, question: str) -> dict:
        """Ask a node's own agent (A2A); a commitment in the reply is kept for booking."""
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
                   extras: list[str] | None = None, use_agreement: bool = False) -> dict:
        """Book a room: compute the total from signed facts only, wait for the user's signed
        approval on the phone, then let the node confirm the booking.

        With `use_agreement`, the total is the price in the hotel's signed Agreement from the
        last negotiation, which the node redeems once (negotiation/agreement.py).
        """
        found = await self.lookup(node_id)
        # A booking takes payment, which untrusted (grey) nodes never get.
        if found is None or not {"can_book", "can_take_payment"} <= set(found[1]["capabilities"]):
            return {"node_id": node_id, "rejected": True,
                    "reason": "node is not trusted for bookings and payments (needs a gold or blue seal)"}
        record, verdict = found

        if use_agreement:
            agreement = self.agreements.get(node_id)
            if agreement is None:
                return {"error": f"no signed agreement with {node_id}: call negotiate first"}
            amount = agreement["payload"]["price_chf"]
            summary = f"Book {record['name']}, {date}: negotiated {agreement['payload']['item']} = CHF {amount:g}"
            return await self._approve_and_book(record, verdict, date, room_type, guest_name, [], amount,
                                                summary, agreement)

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
        return await self._approve_and_book(record, verdict, date, room_type, guest_name, chosen, amount, summary)

    async def _approve_and_book(self, record: dict, verdict: dict, date: str, room_type: str, guest_name: str,
                                chosen: list[dict], amount: float, summary: str, agreement: dict | None = None) -> dict:
        """Wait for the user's signed approval of exactly `amount`, then let the node book."""
        node_id = record["node_id"]
        approval = self.approvals.create("book", record, amount, summary, verdict["seals"])
        self.bus.emit("approval", "pending", f"Waiting for your phone. {summary}", record, verdict["seals"],
                      {"approval_id": approval["id"], "amount_chf": amount})
        decision = await self.approvals.wait(approval["id"])
        step = self.bus.emit("approval", decision["decision"], f"You {decision['decision']} CHF {amount:g} on your phone"
                             " (signed with your key)", record, verdict["seals"], {"decision": decision})["step"]
        if decision["decision"] != "approved":
            return {"declined": True, "source_step": step}

        body = {"date": date, "room_type": room_type, "guest_name": guest_name, "extras": chosen, "approval": decision}
        if agreement is not None:
            body["agreement"] = agreement
        call = await self.signed_call("book", body)
        result = await self.verified_mcp(node_id, "book", {"call": call}, "a2t", "book")
        if not isinstance(result, Verified):
            return result
        confirmation = result.payload
        if confirmation.get("status") == "confirmed":
            text = f"book: confirmed {confirmation['booking_id']}, CHF {confirmation['total_chf']:g}"
            if confirmation.get("checked"):
                text += f" (checked: {', '.join(confirmation['checked'])})"
        else:
            text = f"book refused by hotel: {confirmation.get('reason')}"
        step = self.emit_verified("a2t", text, result)
        return {"node_id": node_id, "source_step": step, **confirmation}
