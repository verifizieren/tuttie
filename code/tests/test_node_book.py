"""Tests for the node's book tool: approval, redeemed commitments and replay protection."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from nacl.signing import SigningKey

from aps import load_signing_key, sign_envelope
from aps.approval import sign_decision
from node.server import create_app

CONFIG = json.loads((Path(__file__).resolve().parent.parent / "data" / "nodes" / "hotel-rheinblick.json").read_text())
NODE_ID = CONFIG["node_id"]
DOG = {"item": "late check-in with dog", "price_chf": 15, "conditions": [], "valid_until": "2026-11-15T00:00:00Z"}


def approval(amount: float, approval_id: str = "ap-1", key: SigningKey | None = None) -> dict:
    request = {"id": approval_id, "action": "book", "payee_node_id": NODE_ID, "amount_chf": amount}
    return sign_decision(request, "approved", key or load_signing_key("user"))


def book(client: TestClient, decision: dict, extras: list[dict]) -> dict:
    body = {"date": "2026-11-14", "room_type": "double", "guest_name": "Alex Muster",
            "extras": extras, "approval": decision}
    return client.post("/tools/book", json=body).json()["payload"]


def commitment(signer: SigningKey) -> dict:
    return sign_envelope(NODE_ID, {"answer": "ok", "commitment": DOG}, signer)


def test_booking_confirmed_with_matching_approval_and_own_commitment():
    client = TestClient(create_app(CONFIG))
    result = book(client, approval(195), [commitment(load_signing_key(NODE_ID))])
    assert result["status"] == "confirmed"
    assert result["total_chf"] == 195 and result["extras"] == ["late check-in with dog"]


def test_approval_cannot_be_replayed():
    client = TestClient(create_app(CONFIG))
    assert book(client, approval(180), [])["status"] == "confirmed"
    assert book(client, approval(180), [])["reason"] == "approval was already used"


def test_refuses_wrong_amount_forged_extra_and_unsigned_approval():
    client = TestClient(create_app(CONFIG))
    assert "does not match" in book(client, approval(99), [])["reason"]
    assert "not a commitment" in book(client, approval(195), [commitment(SigningKey.generate())])["reason"]
    assert "not signed by the user" in book(client, approval(180, key=SigningKey.generate()), [])["reason"]
