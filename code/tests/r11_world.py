"""r11: the real registry, market and hotel nodes in process (only the hotel LLM is a stub),
with a router that honours httpx timeouts (ASGITransport ignores them) and can inject faults."""

import asyncio
import json
from pathlib import Path

import httpx

from aps.keys import load_public_key
from assistant.approvals import ApprovalBook
from assistant.events import EventBus
from assistant.marketplace import MarketDesk
from assistant.tools import Toolbox, load_authorities
from marketplace.app import create_app as create_market_app
from marketplace.market import Market
from negotiation_helpers import registry_lookup
from node.server import create_app
from registry.app import app as registry_app
from tests.mcp_helpers import in_process_link

DATA = Path(__file__).resolve().parent.parent / "data"


class Router(httpx.AsyncBaseTransport):
    """Routes by port to in-process apps; applies the request's read timeout; `fault(request)` may
    return an exception to raise (or None)."""

    def __init__(self):
        self.transports = {}
        self.fault = lambda request: None
        self.seen = []

    async def handle_async_request(self, request):
        self.seen.append((request.method, str(request.url)))
        error = self.fault(request)
        if error is not None:
            raise error
        timeout = (request.extensions.get("timeout") or {}).get("read")
        call = self.transports[request.url.port].handle_async_request(request)
        try:
            return await asyncio.wait_for(call, timeout) if timeout else await call
        except asyncio.TimeoutError:
            raise httpx.ReadTimeout("timed out", request=request) from None


async def world(http: httpx.AsyncClient, router: Router, offer_wait_s: float = 3):
    """(toolbox, bus, market, apps) on `http`, whose transport is `router`."""
    apps = {4000: registry_app}
    for path in (DATA / "nodes").glob("*.json"):
        config = json.loads(path.read_text())
        apps[config["port"]] = create_app(config, http=http, lookup=registry_lookup)
    market_app = create_market_app(http)
    market = Market(http, "http://localhost:4000", load_authorities(), load_public_key("user"),
                    "http://localhost:4010")
    market_app.state.market = market
    apps[4010] = market_app
    router.transports.update({port: httpx.ASGITransport(app=app) for port, app in apps.items()})
    bus = EventBus()
    desk = MarketDesk(http, "http://localhost:4000", bus, load_authorities(),
                      market_url="http://localhost:4010", offer_wait_s=offer_wait_s)
    link = in_process_link({f"http://localhost:{port}": app for port, app in apps.items()})
    toolbox = Toolbox(http, "http://localhost:4000", bus, ApprovalBook(), market=desk, mcp=link)
    return toolbox, bus, market, apps
