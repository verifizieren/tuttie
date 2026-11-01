"""APS trust bindings: what a seal binds (name, kind, endpoint) and who can pose as an authority.

Regression tests for the round 4b red team findings (all failed before the fix)."""

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from nacl.signing import SigningKey

from aps import evaluate_record, issue_seal, load_signing_key, public_key_b64, sign_envelope
from marketplace import market as market_mod
from aps.delegation import sign_delegation, verify_delegation
from aps.keys import load_public_key
from node.server import requester_problem
from scripts.issue_seals import build_record

CODE = Path(__file__).resolve().parent if (Path(__file__).parent / "aps").exists() else Path.cwd()
AUTHS = {a["issuer"]: a for a in json.loads((CODE / "data/authorities.json").read_text())}
REGISTRY = {r["node_id"]: r for r in json.loads((CODE / "data/registry.json").read_text())}


def self_sealed(node_id, capabilities, uid=None):
    """A grey record whose only seal is its own, as anybody can make."""
    key = SigningKey.generate()
    record = {"node_id": node_id, "name": "Advokatur Muster", "kind": "agent", "uid": uid,
              "public_key": public_key_b64(key), "capabilities": capabilities, "tags": ["basel"],
              "endpoint": "http://localhost:4005"}
    record["seals"] = [issue_seal(record, node_id, "grey", key)]
    return record


def test_a_self_seal_named_after_the_bar_association_does_not_license():
    """The fake lawyer only renames its node_id to the authority's issuer id."""
    verdict = evaluate_record(self_sealed("bar-association-ch", ["licensed_legal_ch"]), AUTHS)
    assert verdict["tier"] == "grey"
    assert "licensed_legal_ch" not in verdict["capabilities"]  # FAILS: granted


def test_a_self_seal_named_after_the_register_does_not_vouch_for_a_uid():
    verdict = evaluate_record(self_sealed("handelsregister-bs", ["can_book"], uid="CHE-526.018.151"), AUTHS)
    assert verdict["tier"] == "grey"
    assert verdict["uid"] is None  # FAILS: Rheinblick's UID shown as register-vouched on a grey node


def test_the_seal_binds_the_name_the_user_sees():
    """Blue Spalenhof calls itself 'Hotel Rheinblick' (approval sheet payee_name, cards)."""
    record = copy.deepcopy(REGISTRY["ch.basel.hotel-spalenhof"])
    record["name"] = REGISTRY["ch.basel.hotel-rheinblick"]["name"]
    assert evaluate_record(record, AUTHS)["tier"] == "broken"  # FAILS: still blue


def test_the_seal_binds_the_kind():
    """A sealed hotel relabelled 'user-agent' passes the node's requester check (no delegation asked)."""
    record = copy.deepcopy(REGISTRY["ch.basel.hotel-rheinblick"])
    record["kind"] = "user-agent"
    envelope = sign_envelope(record["node_id"], {"request_id": "rq-1"}, load_signing_key(record["node_id"]))
    posting = SimpleNamespace(request=envelope, requester_id=record["node_id"], request_id="rq-1")

    async def lookup(_):
        return record
    problem = asyncio.run(requester_problem(posting, lookup, AUTHS))
    assert problem is not None  # FAILS: None, the hotel is accepted as a user agent


def test_the_seal_binds_the_endpoint_the_market_sends_its_agent_key_to(monkeypatch):
    """Registry swaps Rheinblick's endpoint; the evil host replays the genuine signed card and gets the key."""
    monkeypatch.setenv("AGENT_WEB_KEY", "s3cret")
    record = copy.deepcopy(REGISTRY["ch.basel.hotel-rheinblick"])
    record["endpoint"] = "http://evil.test"
    card = sign_envelope(record["node_id"], {"wakes_on": [market_mod.EVENT], "persona": {"name": "x"}},
                         load_signing_key(record["node_id"]), timestamp="2020-01-01T00:00:00Z")  # old card
    stolen = []

    def handler(request: httpx.Request):
        if request.url.host == "registry.test":
            return httpx.Response(200, json=[record])
        if request.url.path == "/agent/card":
            return httpx.Response(200, json=card)
        stolen.append(request.headers.get("X-Agent-Web-Key"))
        return httpx.Response(200, json={})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            market = market_mod.Market(http, "http://registry.test", AUTHS, "", "http://market.test")
            entry = {}
            posting = SimpleNamespace(model_dump=lambda **_: {})
            monkeypatch.setattr(market_mod, "PostingCreated", lambda posting: SimpleNamespace(model_dump=lambda: {}))
            await market.wake(posting, ["basel"], entry)
    asyncio.run(run())
    assert stolen == []  # FAILS: ['s3cret'] goes to evil.test


TUTTIE = "ch.tuttie.alex-muster"


def valid_request_posting(record: dict) -> SimpleNamespace:
    """A posting whose request is a valid Request, freshly signed by `record`'s node."""
    soon = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"type": "request", "request_id": "rq-1", "category": "hotel", "tags": ["basel"],
               "constraints": {"date": "2099-11-13", "guests": 1, "requirements": []}, "expires_at": soon}
    envelope = sign_envelope(record["node_id"], payload, load_signing_key(record["node_id"]))
    return SimpleNamespace(request=envelope, requester_id=record["node_id"], request_id="rq-1")


def requester_check(record: dict) -> str | None:
    """requester_problem for a posting by `record`, looked up from this one record."""
    async def lookup(_):
        return record
    return asyncio.run(requester_problem(valid_request_posting(record), lookup, AUTHS))


def test_a_hotel_relabelled_as_user_agent_fails_even_with_a_valid_request():
    record = copy.deepcopy(REGISTRY["ch.basel.hotel-rheinblick"])
    record["kind"] = "user-agent"
    assert evaluate_record(record, AUTHS)["tier"] == "broken"
    assert "seals do not verify" in requester_check(record)


def test_the_genuine_user_agent_may_post_requests():
    assert requester_check(copy.deepcopy(REGISTRY[TUTTIE])) is None


def test_a_user_agent_without_the_users_delegation_may_not_post_requests():
    record = copy.deepcopy(REGISTRY[TUTTIE])
    del record["delegation"]
    assert evaluate_record(record, AUTHS)["tier"] == "blue"  # the delegation is not part of the seal
    assert "delegation" in requester_check(record)


def test_a_delegation_with_a_string_of_scopes_is_no_delegation():
    """`"post" in "post_requests"` would be a substring match; only a list counts."""
    record = REGISTRY[TUTTIE]
    delegation = sign_delegation(TUTTIE, record["public_key"], ["post_requests"], "2099-01-01T00:00:00Z",
                                 load_signing_key("user"))
    user = load_public_key("user")
    assert verify_delegation(delegation, user, TUTTIE, record["public_key"], scope="post_requests")
    forged = {**delegation, "scopes": "post_requests"}
    assert not verify_delegation(forged, user, TUTTIE, record["public_key"], scope="post")


def wake_with(monkeypatch, record: dict, card: dict) -> tuple[list, dict]:
    """Run Market.wake against a registry holding only `record` whose node serves `card`."""
    monkeypatch.setenv("AGENT_WEB_KEY", "s3cret")
    keys_sent = []

    def handler(request: httpx.Request):
        if request.url.host == "registry.test":
            return httpx.Response(200, json=[record])
        if request.url.path == "/agent/card":
            return httpx.Response(200, json=card)
        keys_sent.append(request.headers.get("X-Agent-Web-Key"))
        return httpx.Response(200, json={})

    entry = {}

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            market = market_mod.Market(http, "http://registry.test", AUTHS, "", "http://market.test")
            monkeypatch.setattr(market_mod, "PostingCreated", lambda posting: SimpleNamespace(model_dump=lambda: {}))
            await market.wake(SimpleNamespace(model_dump=lambda **_: {}), ["basel"], entry)
    asyncio.run(run())
    return keys_sent, entry


def test_a_fresh_card_at_the_sealed_endpoint_wakes_the_agent(monkeypatch):
    record = copy.deepcopy(REGISTRY["ch.basel.hotel-rheinblick"])
    card = sign_envelope(record["node_id"], {"wakes_on": [market_mod.EVENT]}, load_signing_key(record["node_id"]))
    keys_sent, entry = wake_with(monkeypatch, record, card)
    assert keys_sent == ["s3cret"] and record["node_id"] in entry["invited"]


def test_issue_seals_refuses_a_node_named_after_an_authority():
    config = {"node_id": "bar-association-ch", "name": "x", "port": 4005, "kind": "agent",
              "capabilities": [], "tags": [], "seals": []}
    with pytest.raises(ValueError, match="authority"):
        build_record(config)
