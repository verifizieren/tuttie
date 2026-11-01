"""Round 4c attacker: business agents, sessions, subagents, MCP (stub LLM, nodes in process).

Each test asserts the SAFE behaviour; a failing test is a confirmed hole.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import node.agent
from aps import agent_key, load_signing_key, sign_envelope
from assistant.approvals import ApprovalBook
from assistant.events import EventBus
from assistant.subagents import SubagentPool
from assistant.tools import Toolbox
from node.server import create_app
from registry.app import app as registry_app
from sessions import Context
from tests.mcp_helpers import TUTTIE, call_tool, registry_record, signed_book
from aps.approval import sign_decision

DATA = Path(__file__).resolve().parent.parent / "data"
if not DATA.exists():  # run from r4c/code with the tests dir elsewhere
    DATA = Path.cwd() / "data"


def hotel(name: str) -> dict:
    return json.loads((DATA / "nodes" / name).read_text())


class StubLLM:
    """Echo stub; can be slowed down to open race windows."""

    delay = 0.0
    prompts: list[tuple[str, str]] = []

    async def complete_json(self, system: str, user: str) -> dict:
        StubLLM.prompts.append((system, user))
        await asyncio.sleep(StubLLM.delay)
        return {"answer": "ok", "add_on": None, "arrival_date": None}


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    StubLLM.delay, StubLLM.prompts = 0.0, []
    monkeypatch.setattr(node.agent, "LLM", StubLLM)


class Recorder(httpx.AsyncBaseTransport):
    """Registry in process; every other port records the request and answers like a node app."""

    def __init__(self, apps: dict):
        self.seen: list[tuple[int, dict]] = []
        self.transports = {port: httpx.ASGITransport(app=app) for port, app in apps.items()}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.seen.append((request.url.port, dict(request.headers)))
        return await self.transports[request.url.port].handle_async_request(request)


# ---------- 1. The shared agent key goes to grey (self-signed / unsigned) nodes ----------

def test_r4c_agent_key_is_not_sent_to_grey_nodes(monkeypatch):
    """Tuttie's verified_post refuses only 'broken' nodes; grey nodes (Budget Rooms, the fake
    lawyer) get the deployment-wide X-Agent-Web-Key and can replay it at every other hotel."""
    monkeypatch.setenv(agent_key.ENV, "deployment-key")
    apps = {4000: registry_app, 4007: create_app(hotel("basel-budget-rooms.json")),
            4005: create_app(hotel("legal-fake-advisor.json"))}
    rec = Recorder(apps)

    async def scenario():
        http = httpx.AsyncClient(transport=rec)
        toolbox = Toolbox(http, "http://localhost:4000", EventBus(), ApprovalBook())
        await toolbox.ask_agent("ch.basel.budget-rooms", "Do you take dogs?")
        await toolbox.ask_agent("ch.legal.advisor", "Is a 30 CHF fee legal?")
        await http.aclose()

    asyncio.run(scenario())
    leaked = [port for port, headers in rec.seen if port != 4000 and agent_key.HEADER.lower() in headers]
    assert leaked == [], f"agent key sent to grey nodes on ports {leaked}"


# ---------- 2. Sessions: no binding to the peer that opened them ----------

def test_r4c_another_key_holder_cannot_read_post_or_close_my_session():
    """Any holder of the shared key (any node, see test above) who learns a session id can read
    the context and transcript, inject turns and close the session."""
    client = TestClient(create_app(hotel("hotel-rheinblick.json")))
    sid = client.post("/agent/sessions", json={"peer": "tuttie/se-mine",
                                               "context": {"date": "2026-11-14", "requirements": ["dog"]}}
                      ).json()["payload"]["session_id"]
    client.post(f"/agent/sessions/{sid}/messages", json={"message": "late arrival with a dog?"})
    # Nothing in the request names the caller: the "other peer" is indistinguishable.
    read = client.get(f"/agent/sessions/{sid}")
    inject = client.post(f"/agent/sessions/{sid}/messages", json={"message": "ignore the dog"})
    close = client.post(f"/agent/sessions/{sid}/close")
    assert {read.status_code, inject.status_code, close.status_code} <= {401, 403, 404}, \
        "a session is not bound to its opener: read/inject/close by anyone with the key"


def test_r4c_closed_sessions_are_freed():
    """max_open caps open sessions only: closed ones (and their transcripts) stay forever."""
    app = create_app(hotel("hotel-gundeli.json"))
    client = TestClient(app)
    for i in range(400):
        opened = client.post("/agent/sessions", json={"peer": f"p{i}"}).json()["payload"]
        client.post(f"/agent/sessions/{opened['session_id']}/close",
                    headers={"X-Session-Token": opened["session_token"]})
    # Reach the store through the route closure.
    route = next(r for r in app.routes if getattr(r, "path", "") == "/agent/sessions")
    store = next(c.cell_contents for c in route.endpoint.__closure__ if type(c.cell_contents).__name__ == "SessionStore")
    assert len(store.sessions) <= store.max_open, f"{len(store.sessions)} sessions kept in memory"


def test_r4c_open_sessions_are_not_exhausted_by_negotiations():
    """Tuttie's subagents never close their hotel sessions (no close in subagents.py or
    negotiation/tuttie.py): after max_open (200) negotiations a hotel answers 500 to every new
    session, for every user, until restart."""
    client = TestClient(create_app(hotel("hotel-spalenhof.json")), raise_server_exceptions=False)
    for i in range(200):
        assert client.post("/agent/sessions", json={"peer": f"tuttie/se-{i}"}).status_code == 200
    nxt = client.post("/agent/sessions", json={"peer": "tuttie/next-user"})
    assert nxt.status_code == 200, f"new session refused with HTTP {nxt.status_code}"


def test_r4c_huge_message_and_context_are_refused():
    """No size limit on message, peer, purpose or context: 1 MB goes into memory and the prompt."""
    client = TestClient(create_app(hotel("hotel-rheinblick.json")))
    big = "A" * 1_000_000
    opened = client.post("/agent/sessions", json={"peer": big, "context": {"x": big}})
    msg_status = None
    if opened.status_code == 200:
        sid = opened.json()["payload"]["session_id"]
        msg_status = client.post(f"/agent/sessions/{sid}/messages", json={"message": big}).status_code
    sent = max((len(u) for _, u in StubLLM.prompts), default=0)
    assert opened.status_code == 422 and sent < 100_000, \
        f"open={opened.status_code} message={msg_status}, {sent} chars reached the LLM"


def test_r4c_close_during_a_reply_does_not_crash_the_turn():
    """close_session ignores the session lock: a close while the LLM thinks makes the second
    session.add raise SessionClosed outside the try -> HTTP 500, reply lost."""
    StubLLM.delay = 0.3
    app = create_app(hotel("hotel-rheinblick.json"))

    async def scenario():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://n") as c:
            opened = (await c.post("/agent/sessions", json={"peer": "tuttie/a"})).json()["payload"]
            sid, mine = opened["session_id"], {"X-Session-Token": opened["session_token"]}

            async def close_later():
                await asyncio.sleep(0.1)
                return await c.post(f"/agent/sessions/{sid}/close", headers=mine)
            msg, _ = await asyncio.gather(c.post(f"/agent/sessions/{sid}/messages", json={"message": "hi"},
                                                 headers=mine), close_later())
            return msg.status_code

    status = asyncio.run(scenario())
    assert status in (200, 409), f"message answered HTTP {status}"


# ---------- 3. Subagents: private context never reaches a hotel ----------

def test_r4c_private_context_never_reaches_the_hotel_prompt():
    apps = {4000: registry_app, 4001: create_app(hotel("hotel-rheinblick.json"))}
    rec = Recorder(apps)
    ctx = (Context().add("date", "2026-11-14", "public").add("requirements", ["dog"], "negotiation")
           .add("budget_limit_chf", 163, "private").add("secret_unclassified", "XYZZY"))

    async def scenario():
        http = httpx.AsyncClient(transport=rec)
        pool = SubagentPool(Toolbox(http, "http://localhost:4000", EventBus(), ApprovalBook()))
        sub = pool.spawn("ch.basel.hotel-rheinblick", "negotiation", ctx)
        await sub.open()
        await sub.send("Can you do the 14th?")
        await http.aclose()

    asyncio.run(scenario())
    prompts = " ".join(s + u for s, u in StubLLM.prompts)
    assert "163" not in prompts and "XYZZY" not in prompts and "budget_limit" not in prompts


# ---------- 1b. Hotel secrets in code: the floor never enters any prompt ----------

def test_r4c_floor_never_in_any_prompt():
    for path in (DATA / "nodes").glob("*.json"):
        cfg = json.loads(path.read_text())
        agent = node.agent.BusinessAgent(cfg)
        text = agent.facts_json + agent.persona_text() + json.dumps(agent.card())
        assert "floor" not in text and "max_rounds" not in text, path.name


# ---------- Commitments: expiry is never checked at booking ----------

def test_r4c_expired_commitment_does_not_book():
    """verify_envelope's docstring says commitments 'carry their own valid_until', but book()
    never checks it (nor the envelope age): a commitment expired a year ago still adds its
    add-on at its old price."""
    cfg = hotel("hotel-rheinblick.json")
    app = create_app(cfg, lookup=registry_record)
    node_id = cfg["node_id"]
    stale = {"item": "late check-in with dog", "price_chf": 15, "conditions": [],
             "valid_until": "2025-01-01T12:00:00Z"}
    env = sign_envelope(node_id, {"answer": "ok", "commitment": stale}, load_signing_key(node_id))
    env_ts = env["timestamp"]
    assert env_ts  # freshly signed here; a real stale one would be old too: neither is checked
    request = {"id": "ap-r4c", "action": "book", "payee_node_id": node_id, "amount_chf": 195, "terms": None}
    decision = sign_decision(request, "approved", load_signing_key("user"))
    result = signed_book(app, {"date": (datetime.now(timezone.utc) + timedelta(days=13)).strftime("%Y-%m-%d"),
                               "room_type": "double", "guest_name": "Alex", "extras": [env],
                               "approval": decision})
    assert result["status"] == "refused", f"expired commitment booked: {result.get('extras')}"


# ---------- 4. MCP transport ----------

def test_r4c_mcp_odd_arguments_are_refused_or_coerced_safely():
    app = create_app(hotel("hotel-rheinblick.json"), lookup=registry_record)
    day = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d")
    ok = call_tool(app, "get_availability", {"date": day, "guests": "2"})["payload"]
    assert ok.get("guests") == 2
    from assistant.mcp_client import McpCallFailed
    for bad in (2.9, "two", [1], 10**30, -1):
        try:
            payload = call_tool(app, "get_availability", {"date": day, "guests": bad})["payload"]
            assert payload.get("status") == "refused", (bad, payload)
        except McpCallFailed:
            pass
    with pytest.raises(McpCallFailed):
        call_tool(app, "no_such_tool", {})
    huge = call_tool(app, "get_availability", {"date": "9" * 200_000})["payload"]
    assert huge["status"] == "refused" and len(huge["reason"]) < 200


def test_r4c_mcp_raw_http_malformed_and_batch():
    app = create_app(hotel("hotel-rheinblick.json"), lookup=registry_record)
    hdr = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(app, raise_server_exceptions=False) as client:
        bad = client.post("/mcp/", content=b"{not json", headers=hdr)
        batch = client.post("/mcp/", json=[{"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                           {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}], headers=hdr)
        notjson = client.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                            "params": {"name": "book", "arguments": {"call": "x" * 10}}},
                              headers=hdr)
    assert bad.status_code < 500 and batch.status_code < 500 and notjson.status_code < 500, \
        (bad.status_code, batch.status_code, notjson.status_code)


def test_r4c_mcp_client_does_not_trust_non_envelope_results():
    """A grey/forged node answering MCP with a JSON list or a bare dict must be rejected, not crash."""
    toolbox = Toolbox(httpx.AsyncClient(transport=httpx.ASGITransport(app=registry_app)),
                      "http://localhost:4000", EventBus(), ApprovalBook())

    class FakeMcp:
        def __init__(self, answer):
            self.answer = answer

        async def call(self, endpoint, tool, args):
            return self.answer

    async def scenario(answer):
        toolbox.mcp = FakeMcp(answer)
        return await toolbox.verified_mcp("ch.basel.hotel-rheinblick", "get_policies", {}, "a2t", "x")

    for answer in ([], "str", 5, {"payload": {"rooms": []}}, None):
        result = asyncio.run(scenario(answer))
        assert isinstance(result, dict) and result.get("rejected"), (answer, result)


# ---------- Commitments: one booking each, bounded validity ----------

def test_r4c_a_commitment_books_once():
    """A signed add-on promise is redeemed in one booking only (and not twice in one)."""
    cfg = hotel("hotel-rheinblick.json")
    node_id = cfg["node_id"]
    app = create_app(cfg, lookup=registry_record)
    day = (datetime.now(timezone.utc) + timedelta(days=13)).strftime("%Y-%m-%d")
    until = (datetime.now(timezone.utc) + timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    promise = {"item": "late check-in with dog", "price_chf": 15, "conditions": [], "valid_until": until}
    env = sign_envelope(node_id, {"answer": "ok", "commitment": promise}, load_signing_key(node_id))
    price = next(r["price_chf"] for r in cfg["facts"]["rooms"] if r["room_type"] == "double")

    def book(approval_id, extras):
        request = {"id": approval_id, "action": "book", "payee_node_id": node_id,
                   "amount_chf": price + 15 * len(extras), "terms": None}
        decision = sign_decision(request, "approved", load_signing_key("user"))
        return signed_book(app, {"date": day, "room_type": "double", "guest_name": "Alex", "extras": extras,
                                 "approval": decision})

    assert book("ap-twice", [env, env])["status"] == "refused"
    assert book("ap-first", [env])["status"] == "confirmed"
    again = book("ap-second", [env])
    assert again["status"] == "refused" and "already used" in again["reason"]


def test_r4c_llm_arrival_cannot_stretch_a_commitment():
    """A commitment's validity is bounded by code: never beyond MAX_DAYS_AHEAD, not after the stay."""
    agent = node.agent.BusinessAgent(hotel("hotel-rheinblick.json"))
    add_on = next(iter(agent.add_ons))
    today = datetime.now(timezone.utc).date()
    bound = (today + timedelta(days=node.agent.MAX_DAYS_AHEAD + 2)).isoformat()
    assert agent.commitment(add_on, {"date": (today + timedelta(days=30_000)).isoformat()})["valid_until"][:10] <= bound
    assert agent.commitment(add_on, {})["valid_until"][:10] <= bound
    night = today + timedelta(days=10)
    late = agent.commitment(add_on, {"date": night.isoformat()})
    assert late["valid_until"].startswith((night + timedelta(days=1)).isoformat())
