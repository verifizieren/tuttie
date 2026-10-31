"""Redeeming signed agreements at booking (negotiation/agreement.py)."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from nacl.signing import SigningKey

from aps import load_signing_key, sign_envelope
from aps.keys import load_public_key
from negotiation.agreement import AgreementInvalid, AgreementRedeemer
from negotiation_helpers import RHEINBLICK, TUTTIE, node_app, signed_offer, stamp

NOW = datetime.now(timezone.utc)


def redeemer() -> AgreementRedeemer:
    return AgreementRedeemer(RHEINBLICK, load_public_key(RHEINBLICK))


def agreement(price=185, valid_until=NOW + timedelta(hours=2), key=None, node_id=RHEINBLICK) -> dict:
    payload = {"type": "agreement", "request_id": "rq-neg1", "offer_id": "of-hotel-rheinblick-1", "round": 2,
               "item": "double room 2026-11-14", "price_chf": price, "includes": ["dog in the room"],
               "conditions": ["best rate, non-refundable"], "valid_until": stamp(valid_until)}
    return sign_envelope(node_id, {"tool": "counter_offer", **payload}, key or load_signing_key(node_id))


def test_own_agreement_is_redeemed_once():
    agreements = redeemer()
    signed = agreement()
    accepted = agreements.check(signed, now=NOW)
    assert accepted.price_chf == 185 and accepted.includes == ["dog in the room"]
    agreements.mark_used(accepted)
    with pytest.raises(AgreementInvalid, match="already booked"):
        agreements.check(signed, now=NOW)


@pytest.mark.parametrize("bad, reason", [
    (agreement(key=SigningKey.generate()), "not signed by this hotel"),
    (agreement(node_id="ch.basel.alpina-grand"), "not signed by this hotel"),
    (agreement(valid_until=NOW - timedelta(minutes=1)), "expired"),
    (sign_envelope(RHEINBLICK, {"type": "agreement", "price_chf": 1}, load_signing_key(RHEINBLICK)), "not a valid"),
    (None, "not signed by this hotel"),
])
def test_agreements_that_cannot_be_redeemed(bad, reason):
    with pytest.raises(AgreementInvalid, match=reason):
        redeemer().check(bad, now=NOW)


def test_a_changed_price_breaks_the_hotels_signature():
    signed = agreement()
    signed["payload"]["price_chf"] = 100
    with pytest.raises(AgreementInvalid, match="not signed"):
        redeemer().check(signed, now=NOW)


def test_an_agreement_from_the_real_counter_offer_tool_is_redeemable():
    """Integration: what counter_offer signs is exactly what booking can redeem."""
    client, offer = TestClient(node_app(RHEINBLICK)), signed_offer(add_ons=("dog",))

    def counter(round_, price):
        body = {"type": "counter", "offer_id": offer["payload"]["offer_id"], "round": round_, "price_chf": price,
                "includes": offer["payload"]["includes"], "conditions": offer["payload"]["conditions"]}
        return sign_envelope(TUTTIE, body, load_signing_key(TUTTIE))

    first = client.post("/tools/counter_offer", json={"counter": counter(1, 186), "offer": offer}).json()
    if first["payload"]["type"] != "agreement":  # accept the hotel's counter in round 2
        price = first["payload"]["price_chf"]
        first = client.post("/tools/counter_offer",
                            json={"counter": counter(2, price), "offer": offer, "last": first}).json()
    assert first["payload"]["type"] == "agreement"
    accepted = redeemer().check(json.loads(json.dumps(first)))
    assert 185 <= accepted.price_chf < 195
