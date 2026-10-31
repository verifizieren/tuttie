"""Tests for the node's book tool over MCP: the action gate (aps/gate.py), commitments, agreements, replays."""

import json
from pathlib import Path

from fastapi import FastAPI
from nacl.signing import SigningKey

from aps import load_signing_key, sign_envelope
from aps.approval import booking_terms, sign_decision
from aps.call import sign_call
from node.server import create_app
from tests.mcp_helpers import TUTTIE, call_tool, registry_record, signed_book

CONFIG = json.loads((Path(__file__).resolve().parent.parent / "data" / "nodes" / "hotel-rheinblick.json").read_text())
NODE_ID = CONFIG["node_id"]
DOG = {"item": "late check-in with dog", "price_chf": 15, "conditions": [], "valid_until": "2026-11-15T00:00:00Z"}


def approval(amount: float, approval_id: str = "ap-1", key: SigningKey | None = None, terms: dict | None = None) -> dict:
    request = {"id": approval_id, "action": "book", "payee_node_id": NODE_ID, "amount_chf": amount, "terms": terms}
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
    assert result["checked"] == ["caller", "signature", "delegation", "approval", "commitments"]


def test_approval_cannot_be_replayed():
    client = node()
    assert book(client, approval(180), [])["status"] == "confirmed"
    assert book(client, approval(180), [])["reason"] == "the approval was already used"


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
    assert "not a known user agent" in call_tool(client, "book", {"call": stranger})["payload"]["reason"]


def test_book_refuses_a_replayed_call_and_a_call_for_another_tool():
    client = node()
    call = sign_call("book", booking_args(180, "ap-r"), TUTTIE, load_signing_key(TUTTIE))
    assert call_tool(client, "book", {"call": call})["payload"]["status"] == "confirmed"
    assert "already used" in call_tool(client, "book", {"call": call})["payload"]["reason"]
    other = sign_call("get_policies", booking_args(180, "ap-o"), TUTTIE, load_signing_key(TUTTIE))
    assert "not book" in call_tool(client, "book", {"call": other})["payload"]["reason"]


def test_an_agreement_booking_names_the_signatures_it_checked():
    deal = signed_agreement(172, load_signing_key(NODE_ID), offer_id="of-rheinblick-9")
    result = book_agreement(node(), approval(172, "ap-c"), deal)
    assert result["checked"] == ["caller", "signature", "delegation", "agreement", "approval"]


# --- the booking is bound to the selected offer ------------------------------------------

BEST, FLEX = "best rate, non-refundable", "flexible, free cancellation until 48h before arrival"


def bound_agreement(price: float, offer_id: str, room: str = "double", rate: str = BEST) -> dict:
    """An agreement as the hotel now signs it: the offer's room, night and rate as fields."""
    payload = {"type": "agreement", "request_id": "rq-test1", "offer_id": offer_id, "round": 2,
               "item": f"{room} room 2026-11-14", "room_type": room, "date": "2026-11-14", "rate": rate,
               "price_chf": price, "includes": [], "conditions": [rate], "valid_until": "2099-01-01T00:00:00Z"}
    return sign_envelope(NODE_ID, payload, load_signing_key(NODE_ID))


def book_terms(client: FastAPI, decision: dict, agreement: dict, room: str = "double",
               date: str = "2026-11-14", extras: list | None = None) -> dict:
    body = {"date": date, "room_type": room, "guest_name": "Alex Muster", "extras": extras or [],
            "approval": decision, "agreement": agreement}
    return signed_book(client, body)


def test_an_agreement_books_exactly_its_room_night_and_rate():
    client = node()
    deal = bound_agreement(172, "of-rheinblick-b1")
    terms = booking_terms("double", "2026-11-14", BEST, [], "of-rheinblick-b1")
    result = book_terms(client, approval(172, "ap-b1", terms=terms), deal)
    assert result["status"] == "confirmed" and result["total_chf"] == 172
    assert (result["room_type"], result["rate"], result["offer_id"]) == ("double", BEST, "of-rheinblick-b1")


def test_an_agreement_cannot_be_switched_to_the_flexible_rate_or_another_night():
    client = node()
    deal = bound_agreement(172, "of-rheinblick-b2")  # the non-refundable double
    flex = book_terms(client, approval(172, "ap-b2"), deal, room="double-flex")
    assert flex["status"] == "refused" and "agreement is for a double room" in flex["reason"]
    other_night = book_terms(client, approval(172, "ap-b3"), deal, date="2026-11-15")
    assert "night of 2026-11-14" in other_night["reason"]
    extra = book_terms(client, approval(172, "ap-b4"), deal, extras=[commitment(load_signing_key(NODE_ID))])
    assert "without extras" in extra["reason"]
    # Nothing was used up: the agreement still books its own terms.
    assert book_terms(client, approval(172, "ap-b5"), deal)["status"] == "confirmed"


def test_an_approval_signed_for_other_terms_does_not_book():
    client = node()
    deal = bound_agreement(172, "of-rheinblick-b6")
    seen = booking_terms("double-flex", "2026-11-14", FLEX, [], "of-rheinblick-b6")  # what the phone showed
    result = book_terms(client, approval(172, "ap-b6", terms=seen), deal)
    assert result["status"] == "refused" and "other terms" in result["reason"]


def test_a_list_price_booking_names_its_rate_and_checks_the_approved_terms():
    client = node()
    terms = booking_terms("double-flex", "2026-11-14", FLEX, [])
    body = {"date": "2026-11-14", "room_type": "double-flex", "guest_name": "Alex Muster",
            "approval": approval(205, "ap-b7", terms=terms)}
    result = signed_book(client, body)
    assert result["status"] == "confirmed" and result["rate"] == FLEX and result["offer_id"] is None
    swapped = {**body, "room_type": "double", "approval": approval(180, "ap-b8", terms=terms)}
    assert "other terms" in signed_book(client, swapped)["reason"]
