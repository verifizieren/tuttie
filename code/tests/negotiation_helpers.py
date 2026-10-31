"""Shared setup for the negotiation tests: real node apps with the counter_offer tool mounted.

`node_app` builds the real node app; node/server.py (create_app) mounts the tool.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from aps import load_signing_key, sign_envelope
from node.server import create_app

DATA = Path(__file__).resolve().parent.parent / "data"
REGISTRY = {r["node_id"]: r for r in json.loads((DATA / "registry.json").read_text())}
CONFIGS = {json.loads(p.read_text())["node_id"]: json.loads(p.read_text()) for p in (DATA / "nodes").glob("*.json")}
TUTTIE = "ch.tuttie.alex-muster"
RHEINBLICK = "ch.basel.hotel-rheinblick"


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


async def registry_lookup(node_id: str) -> dict | None:
    """The hotel's view of the registry, served from the committed registry.json."""
    return REGISTRY.get(node_id)


def node_app(node_id: str, lookup=registry_lookup, http: httpx.AsyncClient | None = None):
    """The real node app, including the counter_offer tool that node/server.py mounts.

    `http` is the client the node sends its offers to the marketplace with (in process).
    """
    return create_app(CONFIGS[node_id], http=http, lookup=lookup)  # node/server.py mounts counter_offer


def signed_offer(node_id: str = RHEINBLICK, room: str = "double", add_ons: tuple = (), offer_id: str | None = None,
                 valid_for: timedelta = timedelta(hours=2), request_id: str = "rq-neg1") -> dict:
    """An offer as make_offer builds it: config prices, signed by the hotel."""
    facts = CONFIGS[node_id]["facts"]
    room_entry = next(r for r in facts["rooms"] if r["room_type"] == room)
    chosen = [a for a in facts.get("add_ons", []) if a["id"] in add_ons]
    payload = {"type": "offer", "request_id": request_id,
               "offer_id": offer_id or f"of-{node_id.rsplit('.', 1)[-1]}-1",
               "item": f"{room} room 2026-11-14", "price_chf": room_entry["price_chf"] + sum(a["price_chf"] for a in chosen),
               "includes": [a["item"] for a in chosen], "conditions": [room_entry["rate"]],
               "valid_until": stamp(datetime.now(timezone.utc) + valid_for)}
    return sign_envelope(node_id, payload, load_signing_key(node_id))


class PortRouter(httpx.AsyncBaseTransport):
    """Send each request to the in-process app registered for its port."""

    def __init__(self, apps: dict):
        self.transports = {port: httpx.ASGITransport(app=app) for port, app in apps.items()}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self.transports[request.url.port].handle_async_request(request)
