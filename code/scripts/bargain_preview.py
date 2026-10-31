"""Preview how the bargaining plays out, to tune the strategy numbers for the demo.

Runs the real negotiation code in one process: the real hotel apps (with their counter_offer
tool and private limits), the registry, and Tuttie's negotiator with its subagents and trust
gate. No LLM is needed: bargaining is deterministic code on both sides. The offers are built
like make_offer does (config prices), so the prices match what the hotels really offer.

Usage (from code/):
    .venv/bin/python scripts/bargain_preview.py                       # defaults: budget 200, double + dog at Rheinblick
    .venv/bin/python scripts/bargain_preview.py --budget 190 --opening 0.1 --tuttie-step 0.5 --hotel-step 0.34
    .venv/bin/python scripts/bargain_preview.py --offer ch.basel.hotel-rheinblick:double:dog --offer ch.basel.alpina-grand:double

Prints every round per hotel. The numbers you pass only change this run; to keep them, set
OPENING_DISCOUNT / TUTTIE_STEP in negotiation/tuttie.py and HOTEL_STEP in negotiation/rules.py.
This is a dev tool for tuning, not a demo screen: the demo runs the real app.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import negotiation.rules as rules  # noqa: E402
import negotiation.tuttie as tuttie  # noqa: E402
from aps import load_signing_key, sign_envelope  # noqa: E402
from assistant.approvals import ApprovalBook  # noqa: E402
from assistant.events import EventBus  # noqa: E402
from assistant.subagents import SubagentPool  # noqa: E402
from assistant.tools import Toolbox  # noqa: E402
from node.server import create_app  # noqa: E402
from registry.app import app as registry_app  # noqa: E402
from sessions import Context  # noqa: E402

TUTTIE = "ch.tuttie.alex-muster"
CONFIGS = {c["node_id"]: c for c in (json.loads(p.read_text()) for p in (ROOT / "data" / "nodes").glob("*.json"))}
REGISTRY = {r["node_id"]: r for r in json.loads((ROOT / "data" / "registry.json").read_text())}
DEFAULT_OFFERS = ["ch.basel.hotel-rheinblick:double:dog", "ch.basel.alpina-grand:double",
                  "ch.basel.hotel-spalenhof:double", "ch.basel.hotel-gundeli:double"]


class PortRouter(httpx.AsyncBaseTransport):
    """Send each request to the in-process app registered for its port."""

    def __init__(self, apps: dict):
        self.transports = {port: httpx.ASGITransport(app=app) for port, app in apps.items()}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Hand the request to the app on its port."""
        return await self.transports[request.url.port].handle_async_request(request)


async def registry_lookup(node_id: str) -> dict | None:
    """What a hotel sees when it looks up Tuttie: the committed registry."""
    return REGISTRY.get(node_id)


def signed_offer(spec: str) -> dict:
    """"node_id:room[:add-on,...]" -> an offer as make_offer builds it, signed by the hotel."""
    node_id, room_type, *rest = spec.split(":")
    facts = CONFIGS[node_id]["facts"]
    room = next(r for r in facts["rooms"] if r["room_type"] == room_type)
    wanted = rest[0].split(",") if rest and rest[0] else []
    add_ons = [a for a in facts.get("add_ons", []) if a["id"] in wanted]
    valid_until = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"type": "offer", "request_id": "rq-preview", "offer_id": f"of-{node_id.rsplit('.', 1)[-1]}-preview",
               "item": f"{room_type} room 2026-11-14", "price_chf": room["price_chf"] + sum(a["price_chf"] for a in add_ons),
               "includes": [a["item"] for a in add_ons], "conditions": [room["rate"]], "valid_until": valid_until}
    return {"node_id": node_id, "name": CONFIGS[node_id]["name"],
            "envelope": sign_envelope(node_id, payload, load_signing_key(node_id))}


def story(outcome: tuttie.Outcome, name: str) -> str:
    """The negotiation as the demo would tell it, one line per round."""
    lines = [f"{name}: offer CHF {outcome.offer_price_chf:g}"]
    for step in outcome.history:
        hotel = step["hotel"]
        if hotel.get("type") == "counter":
            answer = f"hotel CHF {hotel['price_chf']:g}" + (" (final)" if hotel.get("final") else "")
        elif hotel.get("type") == "agreement":
            answer = f"agreed at CHF {hotel['price_chf']:g}"
        else:
            answer = hotel.get("reason", "no agreement")
        lines.append(f"  round {step['round']}: Tuttie CHF {step['own_chf']:g} → {answer}")
    result = f"CHF {outcome.price_chf:g}" if outcome.price_chf else outcome.reason or outcome.status
    lines.append(f"  → {outcome.status}: {result} ({outcome.rounds} rounds)")
    return "\n".join(lines)


async def run(offers: list[dict], budget: float) -> list[tuttie.Outcome]:
    """Negotiate all offers in parallel against the real in-process hotel apps."""
    apps = {4000: registry_app}
    apps.update({c["port"]: create_app(c, lookup=registry_lookup) for c in CONFIGS.values()})
    async with httpx.AsyncClient(transport=PortRouter(apps)) as http:
        toolbox = Toolbox(http, "http://localhost:4000", EventBus(), ApprovalBook())
        negotiator = tuttie.TuttieNegotiator(SubagentPool(toolbox), TUTTIE, load_signing_key(TUTTIE))
        context = Context().add("date", "2026-11-14", "public").add(tuttie.BUDGET_LIMIT, budget, "private")
        return await negotiator.negotiate_all(offers, context)


def main() -> None:
    """Parse the strategy numbers, run the negotiations and print each hotel's story."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--budget", type=float, default=200, help="Tuttie's private limit in CHF")
    parser.add_argument("--opening", type=float, default=tuttie.OPENING_DISCOUNT, help="Tuttie's opening discount")
    parser.add_argument("--tuttie-step", type=float, default=tuttie.TUTTIE_STEP)
    parser.add_argument("--hotel-step", type=float, default=rules.HOTEL_STEP)
    parser.add_argument("--offer", action="append", help="node_id:room[:add-on,...] (repeatable)")
    args = parser.parse_args()
    tuttie.OPENING_DISCOUNT, tuttie.TUTTIE_STEP, rules.HOTEL_STEP = args.opening, args.tuttie_step, args.hotel_step

    offers = [signed_offer(spec) for spec in args.offer or DEFAULT_OFFERS]
    outcomes = asyncio.run(run(offers, args.budget))
    print(f"budget CHF {args.budget:g}, opening {args.opening:g}, Tuttie step {args.tuttie_step:g}, "
          f"hotel step {args.hotel_step:g}\n")
    for offer, outcome in zip(offers, outcomes):
        print(story(outcome, offer["name"]) + "\n")
    winner = tuttie.best(outcomes)
    print(f"best: {CONFIGS[winner.node_id]['name']} at CHF {winner.price_chf:g}" if winner else "no agreement")


if __name__ == "__main__":
    main()
