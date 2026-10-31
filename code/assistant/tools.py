"""Tools the LLM may call, each wrapped in the APS trust gate.

Before the LLM sees any result, the node's registry record is checked against
data/authorities.json and every response envelope is verified with the node's
key. Anything that fails is replaced by {"rejected": true, "reason": ...} and
shown in red on the timeline. The node is never even contacted when its seals
are broken.
"""

import json
import re
from pathlib import Path

import httpx

from aps import evaluate_record, verify_envelope
from assistant.events import EventBus

AUTHORITIES_PATH = Path(__file__).resolve().parent.parent / "data" / "authorities.json"
TOOL_NAME = re.compile(r"^[a-z_]{1,40}$")
NODE_ID = re.compile(r"^[a-z0-9.-]{1,80}$")
# Tools the assistant may call freely; book and pay need an approval first.
READ_TOOLS = {"get_availability", "get_policies"}

SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_registry",
            "description": "Find nodes on the agent web by tags (all must match) and/or a capability. "
                           "Every result is already seal-checked; rejected nodes must not be used.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tags": {"type": "array", "items": {"type": "string"},
                             "description": "e.g. [\"hotel\", \"basel-sbb\"]. Known tags: hotel, basel-sbb, "
                                            "dog-friendly, quiet, legal, consumer-law, switzerland"},
                    "capability": {"type": "string", "description": "e.g. licensed_legal_ch"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_tool",
            "description": "Call a signed tool on a verified node (A2T). The response is signature-checked.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "tool": {"type": "string", "enum": sorted(READ_TOOLS)},
                    "args": {"type": "object",
                             "description": "get_availability: {date: YYYY-MM-DD, guests: int}; get_policies: {}"},
                },
                "required": ["node_id", "tool"],
            },
        },
    },
]


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
    def __init__(self, http: httpx.AsyncClient, registry_url: str, bus: EventBus):
        self.http = http
        self.registry_url = registry_url.rstrip("/")
        self.bus = bus
        self.authorities = load_authorities()

    async def dispatch(self, name: str, args: dict) -> dict:
        if name == "search_registry":
            return await self.search_registry(**args)
        if name == "call_tool":
            return await self.call_tool(**args)
        return {"error": f"unknown tool {name}"}

    async def search_registry(self, tags: list[str] | None = None, capability: str = "") -> dict:
        params = {"tags": ",".join(tags or []), "capability": capability}
        records = (await self.http.get(f"{self.registry_url}/search", params=params)).json()
        verified, refused = [], []
        for record in records:
            verdict = evaluate_record(record, self.authorities)
            if verdict["tier"] == "broken":
                reason = broken_reason(verdict)
                self.bus.emit("registry", "broken", f"{record['name']}: {reason}, ignored", record, verdict["seals"])
                refused.append(rejected(record, reason))
            else:
                self.bus.emit("registry", "verified", f"{record['name']}: {verdict['tier']} seal verified",
                              record, verdict["seals"], {"capabilities": verdict["capabilities"]})
                verified.append(node_view(record, verdict))
        return {"query": params, "verified": verified, "rejected": refused}

    async def lookup(self, node_id: str) -> tuple[dict, dict] | None:
        if not NODE_ID.match(node_id):
            return None
        response = await self.http.get(f"{self.registry_url}/nodes/{node_id}")
        if response.status_code != 200:
            return None
        record = response.json()
        return record, evaluate_record(record, self.authorities)

    async def call_tool(self, node_id: str, tool: str, args: dict | None = None) -> dict:
        if tool not in READ_TOOLS or not TOOL_NAME.match(tool):
            return {"error": f"tool {tool} is not available through call_tool"}
        found = await self.lookup(node_id)
        if found is None:
            return {"node_id": node_id, "rejected": True, "reason": "not in the registry"}
        record, verdict = found
        if verdict["tier"] == "broken":
            reason = broken_reason(verdict)
            self.bus.emit("a2t", "broken", f"{tool} refused: {reason}", record, verdict["seals"])
            return rejected(record, reason)

        envelope = (await self.http.post(f"{record['endpoint']}/tools/{tool}", json=args or {})).json()
        if not verify_envelope(envelope, record["public_key"], expected_node_id=node_id):
            self.bus.emit("a2t", "broken", f"{tool}: response signature invalid, dropped", record, verdict["seals"])
            return rejected(record, "response signature does not verify")

        payload = envelope["payload"]
        self.bus.emit("a2t", "verified", summarize(tool, payload), record, verdict["seals"],
                      {"timestamp": envelope["timestamp"], "payload": payload})
        return {"node_id": node_id, "trust_tier": verdict["tier"], "signed_at": envelope["timestamp"], "data": payload}
