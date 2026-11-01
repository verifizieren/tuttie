"""Run the whole demo in one process, without ports or a browser.

The real registry, marketplace and node apps are served through an in-memory transport;
the LLM, signatures and verification are real. A fake phone taps the decision.

Usage (from code/): .venv/bin/python scripts/demo_headless.py [approved|declined] ["request"]
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import httpx  # noqa: E402

from assistant.agent import Assistant  # noqa: E402
from assistant.approvals import ApprovalBook  # noqa: E402
from assistant.events import EventBus  # noqa: E402
from assistant.mcp_client import McpLink  # noqa: E402
from assistant.tools import Toolbox  # noqa: E402
from aps.keys import load_public_key  # noqa: E402
from llm import LLM  # noqa: E402
from mcp import Client  # noqa: E402
from marketplace.app import create_app as create_market_app  # noqa: E402
from marketplace.app import load_authorities  # noqa: E402
from marketplace.market import Market  # noqa: E402
from node.server import create_app  # noqa: E402
from registry.app import app as registry_app  # noqa: E402

REQUEST = "Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 for 14 Nov, I arrive around 1am."
REGISTRY_PORT, MARKET_PORT = 4000, 4010


class PortRouter(httpx.AsyncBaseTransport):
    """Send each request to the in-process app registered for its port (filled in by `serve`)."""

    def __init__(self):
        self.transports: dict[int, httpx.ASGITransport] = {}

    def serve(self, apps: dict) -> None:
        self.transports = {port: httpx.ASGITransport(app=app) for port, app in apps.items()}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self.transports[request.url.port].handle_async_request(request)


def booking_request(liked: list[dict]) -> str:
    """The wallet's message after swiping (lib/picks.js): book the cheapest liked deal, name the rest."""
    price = lambda c: c["agreed_chf"] if c["agreed_chf"] is not None else c["price_chf"]  # noqa: E731
    best, *others = sorted(liked, key=price)
    text = f"Book {best['name']} ({best['node_id']})" + (" at the agreed price." if best["agreed_chf"] is not None else ".")
    if others:
        text += " If I decline it, I also liked: " + ", ".join(f"{c['name']} ({c['node_id']})" for c in others) + "."
    return text


async def fake_phone(approvals: ApprovalBook, decision: str) -> None:
    """Stand in for the phone: answer every pending approval with `decision`."""
    while True:
        await asyncio.sleep(0.2)
        for approval in list(approvals.pending.values()):
            print(f"phone: {approval['payee_name']} CHF {approval['amount_chf']:g} -> {decision}")
            approvals.decide(approval["id"], decision, allow_mandate=True)  # also allows the offered city tax mandate


async def main(decision: str, request: str) -> None:
    bus, approvals = EventBus(), ApprovalBook()
    router = PortRouter()
    async with httpx.AsyncClient(transport=router, timeout=60) as http:
        # Nodes and market share the in-process client, so hotels can send offers to the market.
        async def lookup(node_id: str) -> dict | None:
            """Registry records from the in-process registry (the nodes check who calls them)."""
            response = await http.get(f"http://localhost:{REGISTRY_PORT}/nodes/{node_id}")
            return response.json() if response.status_code == 200 else None

        apps = {REGISTRY_PORT: registry_app}
        for path in (ROOT / "data" / "nodes").glob("*.json"):
            config = json.loads(path.read_text())
            apps[config["port"]] = create_app(config, http=http, lookup=lookup)
        market_app = create_market_app(http)
        market_app.state.market = Market(http, f"http://localhost:{REGISTRY_PORT}", load_authorities(),
                                         load_public_key("user"), f"http://localhost:{MARKET_PORT}")
        apps[MARKET_PORT] = market_app
        router.serve(apps)
        # Business tools over MCP, also in-process: each endpoint reaches its node's MCP server.
        servers = {f"http://localhost:{port}": app.state.mcp for port, app in apps.items() if hasattr(app.state, "mcp")}
        mcp = McpLink(lambda endpoint: Client(servers[endpoint]))
        toolbox = Toolbox(http, f"http://localhost:{REGISTRY_PORT}", bus, approvals, mcp=mcp)
        phone = asyncio.create_task(fake_phone(approvals, decision))
        assistant = Assistant(LLM(), toolbox, bus)
        answer = await assistant.chat(request)
        # Like the wallet: the user swipes right on every card, Tuttie books the cheapest liked
        # deal and hears about the others for after a decline (apps/wallet/src/lib/picks.js).
        cards = [e for e in bus.history if e["detail"].get("phase") == "cards"]
        liked = cards[-1]["detail"]["cards"] if cards else []
        if liked:
            print(f"\nwallet: liked {[c['name'] for c in liked]}\n{answer}\n")
            answer = await assistant.chat(booking_request(liked), first_tool="book")
            if decision == "approved":
                print(f"\nbooked: {answer}\nuser: What time is check-in?")
                answer = await assistant.chat("What time is check-in?")
        phone.cancel()

    for event in [e for e in bus.history[:-1] if e["kind"] != "thinking"]:
        seals = " ".join(s["tier"] if s["valid"] else f"BROKEN({s['issuer']})" for s in event["seals"])
        print(f"{event['step']:>2} {event['kind']:<9} {event['status']:<9} {event['node_name'] or '':<20} {seals:<12} "
              f"{event['summary'][:110]}")
    print(f"\n{answer}\n(mood: {bus.history[-1]['detail'].get('mood')})")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "approved", sys.argv[2] if len(sys.argv) > 2 else REQUEST))
