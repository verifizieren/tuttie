"""Tests for the node's book tool over MCP: signed call, approval, commitments, agreements, replays."""

import json
from pathlib import Path

from fastapi import FastAPI
from nacl.signing import SigningKey

from aps import load_signing_key, sign_envelope
from aps.approval import sign_decision
from aps.call import sign_call
from node.server import create_app
from tests.mcp_helpers import TUTTIE, call_tool, registry_record, signed_book

CONFIG = json.loads((Path(__file__).resolve().parent.parent / "data" / "nodes" / "hotel-rheinblick.json").read_text())
NODE_ID = CONFIG["node_id"]
DOG = {"item": "late check-in with dog", "price_chf": 15, "conditions": [], "valid_until": "2026-11-15T00:00:00Z"}


def approval(amount: float, approval_id: str = "ap-1", key: SigningKey | None = None) -> dict:
    request = {"id": approval_id, "action": "book", "payee_node_id": NODE_ID, "amount_chf": amount}
    return sign_decision(request, "approved", key or load_signing_key("user"))


def node() -> FastAPI:
    return create_app(CONFIG, lookup=registry_record)


def book(client: FastAPI, decision: dict, extras: list[dict]) -> dict:
    body = {"date": "2026-11-14", "room_type": "double", "guest_name": "Alex Muster",
            "extras": extras, "approval": decision}
    return signed_book(client, body)


def commitment(signer: SigningKey) -> dict:
    return sign_envelope(NODE_ID, {"answer": "ok", "commitment": DOG}, signer)


def test_booking_confirmed_with_matching_approval_and_own_commitment():
    client = node()
    result = book(client, approval(195), [commitment(load_signing_key(NODE_ID))])
    assert result["status"] == "confirmed"
    assert result["total_chf"] == 195 and result["extras"] == ["late check-in with dog"]
    assert result["checked"] == ["caller signature", "user approval", "hotel commitments"]


def test_approval_cannot_be_replayed():
    client = node()
    assert book(client, approval(180), [])["status"] == "confirmed"
    assert book(client, approval(180), [])["reason"] == "approval was already used"


def test_refuses_wrong_amount_forged_extra_and_unsigned_approval():
    client = node()
    assert "does not match" in book(client, approval(99), [])["reason"]
    assert "not a commitment" in book(client, approval(195), [commitment(SigningKey.generate())])["reason"]
    assert "not signed by the user" in book(client, approval(180, key=SigningKey.generate()), [])["reason"]


def signed_agreement(price: float, signer: SigningKey, offer_id: str = "of-rheinblick-1") -> dict:
    payload = {"type": "agreement", "request_id": "rq-test1", "offer_id": offer_id, "round": 2,
               "item": "double room 2026-11-14", "price_chf": price, "includes": ["late check-in with dog"],
               "conditions": ["non-refundable"], "valid_until": "2099-01-01T00:00:00Z"}
    return sign_envelope(NODE_ID, payload, signer)


def book_agreement(client: FastAPI, decision: dict, agreement: dict) -> dict:
    body = {"date": "2026-11-14", "room_type": "double", "guest_name": "Alex Muster",
            "approval": decision, "agreement": agreement}
    return signed_book(client, body)


def test_a_signed_agreement_books_the_negotiated_price_once():
    client = node()
    deal = signed_agreement(172, load_signing_key(NODE_ID))
    result = book_agreement(client, approval(172, "ap-deal"), deal)
    assert result["status"] == "confirmed" and result["total_chf"] == 172
    assert result["extras"] == ["late check-in with dog"]
    assert "already booked" in book_agreement(client, approval(172, "ap-deal-2"), deal)["reason"]


def test_an_agreement_needs_the_hotels_signature_and_a_matching_approval():
    client = node()
    forged = signed_agreement(100, SigningKey.generate())
    assert "not signed by this hotel" in book_agreement(client, approval(100, "ap-f"), forged)["reason"]
    deal = signed_agreement(172, load_signing_key(NODE_ID), offer_id="of-rheinblick-2")
    assert "does not match" in book_agreement(client, approval(180, "ap-m"), deal)["reason"]


# --- the signed call around book (aps/call.py) -------------------------------------------

def booking_args(amount: float, approval_id: str) -> dict:
    return {"date": "2026-11-14", "room_type": "double", "guest_name": "Alex Muster",
            "approval": approval(amount, approval_id)}


def test_book_refuses_a_call_not_signed_by_the_registered_caller():
    client = node()
    forged = sign_call("book", booking_args(180, "ap-x"), TUTTIE, SigningKey.generate())
    assert "not signed by the caller" in call_tool(client, "book", {"call": forged})["payload"]["reason"]
    stranger = sign_call("book", booking_args(180, "ap-y"), "ch.nobody", SigningKey.generate())
    assert "not in the registry" in call_tool(client, "book", {"call": stranger})["payload"]["reason"]


def test_book_refuses_a_replayed_call_and_a_call_for_another_tool():
    client = node()
    call = sign_call("book", booking_args(180, "ap-r"), TUTTIE, load_signing_key(TUTTIE))
    assert call_tool(client, "book", {"call": call})["payload"]["status"] == "confirmed"
    assert call_tool(client, "book", {"call": call})["payload"]["reason"] == "call was already used"
    other = sign_call("get_policies", booking_args(180, "ap-o"), TUTTIE, load_signing_key(TUTTIE))
    assert "another tool" in call_tool(client, "book", {"call": other})["payload"]["reason"]


def test_an_agreement_booking_names_the_signatures_it_checked():
    deal = signed_agreement(172, load_signing_key(NODE_ID), offer_id="of-rheinblick-9")
    result = book_agreement(node(), approval(172, "ap-c"), deal)
    assert result["checked"] == ["caller signature", "user approval", "hotel agreement"]
