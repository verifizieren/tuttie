"""Sessions between agents: hotel-side memory, and Tuttie's parallel subagents.

The hotel apps are the real ones (served in process); only the LLM is a stub.
"""

import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import node.agent
from aps import verify_envelope
from assistant.approvals import ApprovalBook
from assistant.events import EventBus
from assistant.subagents import SubagentPool
from assistant.tools import Toolbox
from node.server import create_app
from registry.app import app as registry_app
from sessions import Context

DATA = Path(__file__).resolve().parent.parent / "data"
REGISTRY = {r["node_id"]: r for r in json.loads((DATA / "registry.json").read_text())}
HOTELS = ["hotel-alpina-grand.json", "hotel-rheinblick.json", "guesthouse-am-rhein.json"]
LLM_DELAY = 0.2  # seconds the stub "thinks", to show that subagents run in parallel


class StubLLM:
    """Stands in for the LLM: echoes how many earlier turns it saw and what context it got."""

    prompts: list[dict] = []

    async def complete_json(self, system: str, user: str) -> dict:
        request = json.loads(user)
        StubLLM.prompts.append(request)
        await asyncio.sleep(LLM_DELAY)
        seen = len(request.get("conversation_so_far", []))
        return {"answer": f"seen {seen} earlier turns", "add_on": None, "arrival_date": None}


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    StubLLM.prompts = []
    monkeypatch.setattr(node.agent, "LLM", StubLLM)


def hotel(name: str) -> dict:
    return json.loads((DATA / "nodes" / name).read_text())


# ---------- Hotel side: one memory per session ----------

def test_a_session_remembers_earlier_turns():
    cfg = hotel("hotel-rheinblick.json")
    client = TestClient(create_app(cfg))
    opened = client.post("/agent/sessions", json={"peer": "tuttie/a", "context": {"date": "2026-11-14"}}).json()
    session_id = opened["payload"]["session_id"]
    first = client.post(f"/agent/sessions/{session_id}/messages", json={"message": "A room on 14 Nov?"}).json()
    second = client.post(f"/agent/sessions/{session_id}/messages", json={"message": "And with a dog?"}).json()
    assert first["payload"]["answer"] == "seen 1 earlier turns"   # only the "opened" note
    assert second["payload"]["answer"] == "seen 3 earlier turns"  # opened, message, reply
    assert StubLLM.prompts[-1]["context"] == {"date": "2026-11-14"}
    memory = client.get(f"/agent/sessions/{session_id}").json()
    assert verify_envelope(memory, REGISTRY[cfg["node_id"]]["public_key"], expected_node_id=cfg["node_id"])
    assert [t["kind"] for t in memory["payload"]["turns"]] == ["opened", "message", "reply", "message", "reply"]


def test_parallel_sessions_with_one_hotel_do_not_mix():
    client = TestClient(create_app(hotel("guesthouse-am-rhein.json")))
    a = client.post("/agent/sessions", json={"peer": "tuttie/a"}).json()["payload"]["session_id"]
    b = client.post("/agent/sessions", json={"peer": "tuttie/b"}).json()["payload"]["session_id"]
    client.post(f"/agent/sessions/{a}/messages", json={"message": "one"})
    client.post(f"/agent/sessions/{a}/messages", json={"message": "two"})
    reply_b = client.post(f"/agent/sessions/{b}/messages", json={"message": "first in b"}).json()
    assert reply_b["payload"]["answer"] == "seen 1 earlier turns"


def test_closed_and_unknown_sessions_are_refused():
    client = TestClient(create_app(hotel("hotel-alpina-grand.json")))
    session_id = client.post("/agent/sessions", json={"peer": "tuttie/a"}).json()["payload"]["session_id"]
    assert client.post(f"/agent/sessions/{session_id}/close").json()["payload"]["status"] == "closed"
    assert client.post(f"/agent/sessions/{session_id}/messages", json={"message": "hi"}).status_code == 409
    assert client.post("/agent/sessions/se-unknown/messages", json={"message": "hi"}).status_code == 404


# ---------- Tuttie side: parallel subagents with limited context ----------

class PortRouter(httpx.AsyncBaseTransport):
    """Send each request to the in-process app registered for its port."""

    def __init__(self, apps: dict):
        self.transports = {port: httpx.ASGITransport(app=app) for port, app in apps.items()}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self.transports[request.url.port].handle_async_request(request)


def make_pool() -> tuple[SubagentPool, httpx.AsyncClient]:
    apps = {4000: registry_app}
    for path in (DATA / "nodes").glob("*.json"):
        cfg = json.loads(path.read_text())
        apps[cfg["port"]] = create_app(cfg)
    http = httpx.AsyncClient(transport=PortRouter(apps))
    return SubagentPool(Toolbox(http, "http://localhost:4000", EventBus(), ApprovalBook())), http


def user_context() -> Context:
    return (Context().add("date", "2026-11-14", "public").add("requirements", ["quiet", "dog"], "negotiation")
            .add("max_price_chf", 200, "private").add("guest_name", "Alex Muster", "private"))


def test_subagents_run_in_parallel_with_only_shared_context():
    async def scenario():
        pool, http = make_pool()
        subagents = [pool.spawn(hotel(name)["node_id"], "negotiation", user_context()) for name in HOTELS]
        opened = await pool.open_all(subagents)
        start = time.perf_counter()
        replies = await pool.send_all(subagents, "Can you do 14 Nov with a dog?")
        elapsed = time.perf_counter() - start
        await http.aclose()
        return subagents, opened, replies, elapsed

    subagents, opened, replies, elapsed = asyncio.run(scenario())
    assert all("session_id" in o for o in opened)
    assert all(r["answer"] == "seen 1 earlier turns" for r in replies)
    assert elapsed < LLM_DELAY * len(HOTELS) * 0.8  # parallel, not one after the other
    # Hotels only ever received the shared context: no private item left Tuttie.
    for prompt in StubLLM.prompts:
        assert prompt["context"] == {"date": "2026-11-14", "requirements": ["quiet", "dog"]}
    # Each subagent has its own memory.
    assert len({s.id for s in subagents}) == 3
    assert all([t.kind for t in s.memory.turns] == ["opened", "message", "reply"] for s in subagents)


def test_a_subagent_cannot_open_a_session_with_a_forged_hotel():
    async def scenario():
        pool, http = make_pool()
        subagent = pool.spawn("ch.basel.cheap-hotels", "negotiation", user_context())
        result = await subagent.open()
        await http.aclose()
        return subagent, result

    subagent, result = asyncio.run(scenario())
    assert result["rejected"] is True and subagent.remote_session is None
    assert StubLLM.prompts == []  # the forged hotel's agent was never reached
