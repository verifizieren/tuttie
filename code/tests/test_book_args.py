"""A TypeError inside a tool is a failure, not "bad arguments" (assistant/tools.py dispatch).

No LLM. In-process registry, hotels and market as in scripts/demo_headless.py.
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).resolve().parent.parent  # code/
sys.path.insert(0, str(ROOT / "scripts"))
from demo_headless import (PortRouter, ApprovalBook, EventBus, McpLink, Toolbox, Client,  # noqa: E402
                           create_app, create_market_app, load_authorities, Market, registry_app, load_public_key)
from assistant.agent import Assistant  # noqa: E402

RHEINBLICK = "ch.basel.hotel-rheinblick"
BOOK = {"node_id": RHEINBLICK, "guest_name": "Alex Muster", "date": "2026-11-14", "room_type": "double"}


async def run(stub_create: bool):
    bus, approvals = EventBus(), ApprovalBook()
    router = PortRouter()
    http = httpx.AsyncClient(transport=router, timeout=60)

    async def lookup(node_id):
        r = await http.get(f"http://localhost:4000/nodes/{node_id}")
        return r.json() if r.status_code == 200 else None

    apps = {4000: registry_app}
    for path in (ROOT / "data" / "nodes").glob("*.json"):
        config = json.loads(path.read_text())
        apps[config["port"]] = create_app(config, http=http, lookup=lookup)
    market_app = create_market_app(http)
    market_app.state.market = Market(http, "http://localhost:4000", load_authorities(), load_public_key("user"),
                                     "http://localhost:4010")
    apps[4010] = market_app
    router.serve(apps)
    servers = {f"http://localhost:{p}": a.state.mcp for p, a in apps.items() if hasattr(a.state, "mcp")}
    toolbox = Toolbox(http, "http://localhost:4000", bus, approvals, mcp=McpLink(lambda e: Client(servers[e])))
    created = []
    if stub_create:  # a wrapper with the old 6-argument signature
        orig = approvals.create

        def create(action, record, amount, summary, seals, offer_mandate=None):
            created.append(amount)
            return orig(action, record, amount, summary, seals, offer_mandate)
        approvals.create = create

    async def phone():
        while True:
            await asyncio.sleep(0.05)
            for a in list(approvals.pending.values()):
                created.append(a["amount_chf"])
                approvals.decide(a["id"], "declined", allow_mandate=False)
    task = asyncio.create_task(phone())
    me = SimpleNamespace(toolbox=toolbox)
    avail = await Assistant.run_tool(me, "call_tool", json.dumps(
        {"node_id": RHEINBLICK, "tool": "get_availability", "args": {"date": "2026-11-14", "guests": 2}}))
    result = await Assistant.run_tool(me, "book", json.dumps(BOOK))
    task.cancel()
    await http.aclose()
    return avail, result, created


def test_book_with_real_approval_book_reaches_the_phone():
    """The product path: the same args create an approval (declined by the phone), no error."""
    avail, result, created = asyncio.run(run(stub_create=False))
    assert "error" not in avail, avail
    assert result.get("declined") is True, result
    assert created, "no approval was created"


def test_internal_typeerror_is_not_reported_as_bad_arguments():
    """A TypeError raised INSIDE book (here: a stale approvals.create stub without the `terms`
    argument) must not be reported to the LLM as "bad arguments for book": it would retry the
    same correct call and tell the user its arguments were wrong."""
    _, result, created = asyncio.run(run(stub_create=True))
    assert not created
    assert "bad arguments" not in result.get("error", ""), result


def test_arguments_that_do_not_fit_the_tool_are_still_bad_arguments():
    toolbox = Toolbox(httpx.AsyncClient(), "http://registry", EventBus(), ApprovalBook())
    me = SimpleNamespace(toolbox=toolbox)
    for raw in ('{"verdict": "like", "extra": 1}', "{}", "[1]"):
        result = asyncio.run(Assistant.run_tool(me, "swipe_card", raw))
        assert result["error"].startswith("bad arguments for swipe_card"), (raw, result)
