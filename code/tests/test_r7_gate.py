"""Round 7 hardening: where the services listen, the market's posting limits, old approvals,
and node ids that are not node ids.

1. Every internal service (registry, marketplace, nodes, services) listens on SERVICE_HOST
   (default 0.0.0.0, unchanged); the assistant on 4040 stays public.
2. The marketplace takes at most POSTINGS_PER_MIN signed postings per requester a minute
   (429 with Retry-After) and keeps at most MAX_OPEN_POSTINGS in memory; Tuttie turns a
   refusal into a calm tool error.
3. The gate refuses an approval decided too long ago (or in the future): after a node restart
   forgot the used approvals, an old one does not book again.
4. registry_lookup refuses an id that is not a node id ("../search" reached GET /search), and
   the gate refuses instead of raising.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import marketplace.market as market_module
import negotiation.hotel as hotel
import registry.app as registry_app
from aps import load_signing_key, sign_envelope
from aps.approval import booking_terms, sign_decision
from aps.call import sign_call
from aps.gate import ActionGate, Needs
from aps.keys import load_public_key
from assistant.events import EventBus
from assistant.marketplace import MarketDesk
from assistant.tools import load_authorities
from marketplace.app import create_app as create_market_app
from marketplace.market import MarketError
from node.server import create_app
from tests.mcp_helpers import TUTTIE, call_tool, registry_record
from tests.test_marketplace import World, request, stamp, tuttie_envelope

CODE = Path(__file__).resolve().parent.parent
GUESTHOUSE = json.loads((CODE / "data" / "nodes" / "guesthouse-am-rhein.json").read_text())
RHEINBLICK = json.loads((CODE / "data" / "nodes" / "hotel-rheinblick.json").read_text())


# --- 1. SERVICE_HOST ------------------------------------------------------------------------

def test_service_host_defaults_to_all_interfaces_and_follows_the_setting(monkeypatch):
    from hosting import service_host
    monkeypatch.delenv("SERVICE_HOST", raising=False)
    assert service_host() == "0.0.0.0"
    monkeypatch.setenv("SERVICE_HOST", "127.0.0.1")
    assert service_host() == "127.0.0.1"
    monkeypatch.setenv("SERVICE_HOST", "  ")
    assert service_host() == "0.0.0.0"


def test_run_all_passes_service_host_from_the_env_file_to_every_service():
    from scripts import run_all
    assert run_all.service_env({"SERVICE_HOST": "127.0.0.1"}, {})["SERVICE_HOST"] == "127.0.0.1"
    assert "SERVICE_HOST" not in run_all.service_env({}, {})


def test_every_internal_service_binds_service_host_and_the_assistant_stays_public():
    for path in ("registry/app.py", "marketplace/app.py", "node/server.py", "services/server.py"):
        source = (CODE / path).read_text()
        assert "0.0.0.0" not in source and "service_host()" in source, path
    assert 'host="0.0.0.0"' in (CODE / "assistant" / "app.py").read_text()


@pytest.mark.parametrize("bind", ["0.0.0.0", "127.0.0.1"])
@pytest.mark.parametrize("host", ["localhost:4009", "127.0.0.1:4009", "testserver"])
def test_mcp_over_http_answers_whatever_the_bind_address(monkeypatch, tmp_path, bind, host):
    """The bind address decides who can connect; the MCP Host-header check stays off either way,
    so Tuttie's calls to http://localhost:<port>/mcp/ pass with SERVICE_HOST=127.0.0.1 too."""
    monkeypatch.setenv("SERVICE_HOST", bind)
    app = create_app(GUESTHOUSE, lookup=registry_record, deployments_dir=tmp_path)
    with TestClient(app, base_url=f"http://{host}") as client:
        response = client.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                               headers={"Accept": "application/json, text/event-stream"})
    assert response.status_code == 200 and "get_availability" in response.text


def test_the_mcp_host_check_is_off_explicitly():
    source = (CODE / "node" / "mcp_tools.py").read_text()
    assert "enable_dns_rebinding_protection=False" in source and "0.0.0.0" not in source


# --- 2. posting limits ----------------------------------------------------------------------

def flood(market, count: int) -> tuple[int, list[MarketError]]:
    """Post `count` fresh signed requests; returns (accepted, refusals)."""
    accepted, refusals = 0, []

    async def run():
        nonlocal accepted
        for i in range(count):
            req = request(request_id=f"rq-flood-{i}", tags=["basel"], budget=None,
                          expires=datetime.now(timezone.utc) + timedelta(hours=2))
            try:
                await market.post_request(tuttie_envelope(req, timestamp=stamp(datetime.now(timezone.utc))))
                accepted += 1
            except MarketError as error:
                refusals.append(error)

    asyncio.run(run())
    return accepted, refusals


def test_a_burst_of_signed_postings_is_throttled_before_it_wakes_hotels(monkeypatch):
    monkeypatch.setattr(market_module, "POSTINGS_PER_MIN", 5)
    accepted, refusals = flood(World().market(), 8)
    assert accepted == 5 and len(refusals) == 3
    assert all(r.status == 429 and r.retry_after >= 1 for r in refusals)


def test_the_default_limit_leaves_room_for_a_full_room_at_the_pitch():
    assert market_module.POSTINGS_PER_MIN >= 100


def test_only_the_newest_postings_are_kept(monkeypatch):
    monkeypatch.setattr(market_module, "MAX_OPEN_POSTINGS", 3)
    market = World().market()
    accepted, _ = flood(market, 5)
    assert accepted == 5
    assert list(market.postings) == ["rq-flood-2", "rq-flood-3", "rq-flood-4"]


def test_http_429_carries_retry_after(monkeypatch):
    monkeypatch.setattr(market_module, "POSTINGS_PER_MIN", 1)
    world = World()
    with TestClient(create_market_app(world.http)) as client:
        for i, expected in ((1, 201), (2, 429)):
            req = request(request_id=f"rq-http-{i}", tags=["basel"], budget=None,
                          expires=datetime.now(timezone.utc) + timedelta(hours=2))
            response = client.post("/postings", json=tuttie_envelope(req, timestamp=stamp(datetime.now(timezone.utc))))
            assert response.status_code == expected
    assert int(response.headers["Retry-After"]) >= 1 and response.json()["refused"] is True


@pytest.mark.parametrize("response", [
    httpx.Response(429, json={"refused": True, "reason": "too many postings"}, headers={"Retry-After": "30"}),
    httpx.Response(502, text="<html>Bad gateway</html>"),
])
def test_tuttie_turns_a_market_refusal_into_a_calm_tool_error(response):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)) as http:
            desk = MarketDesk(http, "http://reg", EventBus(), load_authorities(), market_url="http://market")
            return await desk.find("2026-11-14", tags=["basel"])

    result = asyncio.run(scenario())
    assert set(result) == {"error"} and "market" in result["error"]


def test_tuttie_survives_an_unreachable_market():
    def down(_):
        raise httpx.ConnectError("refused")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as http:
            desk = MarketDesk(http, "http://reg", EventBus(), load_authorities(), market_url="http://market")
            return await desk.find("2026-11-14", tags=["basel"])

    assert "error" in asyncio.run(scenario())


# --- 3. old approvals -----------------------------------------------------------------------

NIGHT = (datetime.now(timezone.utc) + timedelta(days=3)).date().isoformat()


def approval(decided: datetime | None = None) -> dict:
    """The user's signed approval for the guesthouse's single room, decided at `decided`."""
    room = next(r for r in GUESTHOUSE["facts"]["rooms"] if r["room_type"] == "single")
    body = {"id": "ap-age", "action": "book", "payee_node_id": GUESTHOUSE["node_id"], "amount_chf": room["price_chf"],
            "terms": booking_terms("single", NIGHT, room["rate"], [])}
    if decided is None:
        return sign_decision(body, "approved", load_signing_key("user"))
    import aps.approval as approval_module
    real = approval_module.utc_now
    approval_module.utc_now = lambda: stamp(decided)
    try:
        return sign_decision(body, "approved", load_signing_key("user"))
    finally:
        approval_module.utc_now = real


def book(decision: dict, tmp_path) -> dict:
    app = create_app(GUESTHOUSE, lookup=registry_record, deployments_dir=tmp_path)
    args = {"date": NIGHT, "room_type": "single", "guest_name": "Alex Muster", "approval": decision}
    return call_tool(app, "book", {"call": sign_call("book", args, TUTTIE, load_signing_key(TUTTIE))})["payload"]


def test_a_fresh_approval_books(tmp_path):
    assert book(approval(), tmp_path)["status"] == "confirmed"


def test_an_old_approval_does_not_book_after_a_restart(tmp_path):
    old = approval(datetime.now(timezone.utc) - timedelta(hours=1))
    result = book(old, tmp_path)
    assert result["status"] == "refused" and "approval" in result["reason"]


def test_an_approval_from_the_future_does_not_book(tmp_path):
    ahead = approval(datetime.now(timezone.utc) + timedelta(hours=1))
    assert book(ahead, tmp_path)["status"] == "refused"


# --- 4. node ids that are not node ids ------------------------------------------------------

@pytest.fixture
def registry_over_http(monkeypatch):
    """registry_lookup's own httpx client reaches the real registry app in-process."""
    real = httpx.AsyncClient

    def client(*a, **kw):
        kw["transport"] = httpx.ASGITransport(app=registry_app.app)
        return real(*a, **kw)

    monkeypatch.setattr(hotel.httpx, "AsyncClient", client)


@pytest.mark.parametrize("node_id", ["../search", "ch.basel/../../search", "", None, 42, "x" * 200])
def test_registry_lookup_refuses_ids_that_are_not_node_ids(registry_over_http, node_id):
    assert asyncio.run(hotel.registry_lookup(node_id)) is None


def test_registry_lookup_still_finds_a_real_node(registry_over_http):
    assert asyncio.run(hotel.registry_lookup(TUTTIE))["node_id"] == TUTTIE


def test_counter_offer_with_a_dot_dot_sender_is_a_signed_refusal_not_a_500(registry_over_http, tmp_path):
    app = create_app(RHEINBLICK, deployments_dir=tmp_path)  # default lookup = registry_lookup
    offer = sign_envelope(RHEINBLICK["node_id"], {"type": "offer", "request_id": "rq-x", "offer_id": "of-x",
                                                  "item": "double", "price_chf": 195,
                                                  "valid_until": "2099-01-01T00:00:00Z"},
                          load_signing_key(RHEINBLICK["node_id"]))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/tools/counter_offer",
                               json={"counter": {"node_id": "../search", "timestamp": "x", "payload": {}, "signature": ""},
                                     "offer": offer, "last": None})
    assert response.status_code == 200, f"HTTP {response.status_code}: {response.text[:120]}"


def test_the_gate_refuses_a_dot_dot_agent_id_instead_of_raising(registry_over_http):
    gate = ActionGate("n", "k", load_public_key("user"), {}, hotel.registry_lookup)
    call = {"tool": "book", "args": {}, "agent_id": "../search", "nonce": "n", "timestamp": "t", "signature": "s"}
    verdict = asyncio.run(gate.check_action(call, Needs("book", scope="book")))
    assert not verdict.ok


def test_the_gate_refuses_a_lookup_that_answers_a_list():
    async def lookup(_):
        return [{"kind": "user-agent"}]

    gate = ActionGate("n", "k", load_public_key("user"), {}, lookup)
    call = {"tool": "book", "args": {}, "agent_id": TUTTIE, "nonce": "n", "timestamp": "t", "signature": "s"}
    assert not asyncio.run(gate.check_action(call, Needs("book", scope="book"))).ok
