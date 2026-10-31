"""Run the whole demo in one process, without ports or a browser.

The real registry and node apps are served through an in-memory transport; the
LLM, signatures and verification are real. A fake phone taps the decision.

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
from assistant.tools import Toolbox  # noqa: E402
from llm import LLM  # noqa: E402
from node.server import create_app  # noqa: E402
from registry.app import app as registry_app  # noqa: E402

REQUEST = "Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 for 14 Nov, I arrive around 1am."
REGISTRY_PORT = 4000


class PortRouter(httpx.AsyncBaseTransport):
    """Send each request to the in-process app registered for its port."""

    def __init__(self, apps: dict):
        self.transports = {port: httpx.ASGITransport(app=app) for port, app in apps.items()}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self.transports[request.url.port].handle_async_request(request)


async def fake_phone(approvals: ApprovalBook, decision: str) -> None:
    while True:
        await asyncio.sleep(0.2)
        for approval in list(approvals.pending.values()):
            print(f"phone: {approval['payee_name']} CHF {approval['amount_chf']:g} -> {decision}")
            approvals.decide(approval["id"], decision)


async def main(decision: str, request: str) -> None:
    apps = {REGISTRY_PORT: registry_app}
    for path in (ROOT / "data" / "nodes").glob("*.json"):
        config = json.loads(path.read_text())
        apps[config["port"]] = create_app(config)

    bus, approvals = EventBus(), ApprovalBook()
    async with httpx.AsyncClient(transport=PortRouter(apps), timeout=60) as http:
        toolbox = Toolbox(http, f"http://localhost:{REGISTRY_PORT}", bus, approvals)
        phone = asyncio.create_task(fake_phone(approvals, decision))
        answer = await Assistant(LLM(), toolbox, bus).chat(request)
        phone.cancel()

    for event in [e for e in bus.history[:-1] if e["kind"] != "thinking"]:
        seals = " ".join(s["tier"] if s["valid"] else f"BROKEN({s['issuer']})" for s in event["seals"])
        print(f"{event['step']:>2} {event['kind']:<9} {event['status']:<9} {event['node_name'] or '':<20} {seals:<12} "
              f"{event['summary'][:110]}")
    print(f"\n{answer}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "approved", sys.argv[2] if len(sys.argv) > 2 else REQUEST))
