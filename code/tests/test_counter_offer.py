"""The hotel's counter_offer tool on the real node app: signatures, delegation, limits."""

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from nacl.signing import SigningKey

from aps import load_signing_key, sign_envelope, verify_envelope
from aps.keys import load_public_key
from negotiation_helpers import CONFIGS, REGISTRY, RHEINBLICK, TUTTIE, node_app, signed_offer, stamp

NOW = datetime.now(timezone.utc)


def counter(offer: dict, round_: int, price: float, key: SigningKey | None = None, sender: str = TUTTIE,
            timestamp: str | None = None, **changes) -> dict:
    body = {"type": "counter", "offer_id": offer["payload"]["offer_id"], "round": round_, "price_chf": price,
            "includes": offer["payload"]["includes"], "conditions": offer["payload"]["conditions"], **changes}
    return sign_envelope(sender, body, key or load_signing_key(sender), timestamp)


def ask(client: TestClient, offer: dict, counter_envelope: dict, last: dict | None = None) -> dict:
    envelope = client.post("/tools/counter_offer", json={"counter": counter_envelope, "offer": offer, "last": last}).json()
    assert verify_envelope(envelope, load_public_key(RHEINBLICK), RHEINBLICK)  # every reply is signed
    return envelope


def test_a_full_negotiation_ends_in_a_signed_agreement_above_the_floor():
    client, offer = TestClient(node_app(RHEINBLICK)), signed_offer(add_ons=("dog",))  # 180 + 15
    first = ask(client, offer, counter(offer, 1, 160))
    assert first["payload"]["type"] == "counter" and 185 <= first["payload"]["price_chf"] < 195
    second = ask(client, offer, counter(offer, 2, first["payload"]["price_chf"]), last=first)
    agreement = second["payload"]
    assert agreement["type"] == "agreement" and agreement["price_chf"] == first["payload"]["price_chf"]
    assert agreement["includes"] == ["dog in the room"] and agreement["request_id"] == "rq-neg1"


def test_limits_never_appear_in_a_reply():
    client, offer = TestClient(node_app(RHEINBLICK)), signed_offer()
    replies, last = [], None
    for round_, price in enumerate((100, 120, 140, 150), start=1):
        reply = ask(client, offer, counter(offer, round_, price), last=last)
        replies.append(reply)
        if reply["payload"]["type"] != "counter":
            break
        last = reply
    text = json.dumps(replies)
    assert "floor" not in text and "max_rounds" not in text and "negotiation" not in text
    assert all(r["payload"].get("price_chf", 170) >= 170 for r in replies)  # Rheinblick's floor


def test_counters_that_do_not_verify_are_refused():
    client, offer = TestClient(node_app(RHEINBLICK)), signed_offer()
    cases = {
        "not from a known user agent": counter(offer, 1, 160, sender=RHEINBLICK),
        "signature does not verify": counter(offer, 1, 160, key=SigningKey.generate()),
        "outdated": counter(offer, 1, 160, timestamp=stamp(NOW - timedelta(hours=1))),
        "only the price is negotiable": counter(offer, 1, 160, includes=["free spa"]),
        "not a valid Counter": counter(offer, 1, -5),
    }
    for reason, envelope in cases.items():
        payload = ask(client, offer, envelope)["payload"]
        assert payload["status"] == "refused" and reason in payload["reason"], (reason, payload)


def test_tuttie_needs_the_users_delegation_to_negotiate():
    registry = json.loads(json.dumps(REGISTRY))
    registry[TUTTIE]["delegation"]["scopes"] = ["post_requests"]

    async def lookup(node_id):
        return registry.get(node_id)

    client, offer = TestClient(node_app(RHEINBLICK, lookup)), signed_offer()
    assert "delegated" in ask(client, offer, counter(offer, 1, 160))["payload"]["reason"]


def test_the_hotel_trusts_only_its_own_signatures_for_offers_and_earlier_rounds():
    client, offer = TestClient(node_app(RHEINBLICK)), signed_offer()
    cheap = json.loads(json.dumps(offer))
    cheap["payload"]["price_chf"] = 100  # a "remembered" price the hotel never signed
    assert "offer is not signed" in ask(client, cheap, counter(cheap, 1, 100))["payload"]["reason"]
    other_hotel = signed_offer("ch.basel.alpina-grand")
    assert "offer is not signed" in ask(client, other_hotel, counter(other_hotel, 1, 200))["payload"]["reason"]
    first = ask(client, offer, counter(offer, 1, 160))
    forged_last = json.loads(json.dumps(first))
    forged_last["payload"]["price_chf"] = 161
    assert "previous counter is not signed" in ask(client, offer, counter(offer, 2, 161), forged_last)["payload"]["reason"]
    assert "does not belong to this round" in ask(client, offer, counter(offer, 3, 170), first)["payload"]["reason"]
    assert "round 1 has no previous" in ask(client, offer, counter(offer, 1, 170), first)["payload"]["reason"]


def test_expired_offer_cannot_be_negotiated():
    client, offer = TestClient(node_app(RHEINBLICK)), signed_offer(valid_for=timedelta(seconds=-1))
    assert "expired" in ask(client, offer, counter(offer, 1, 160))["payload"]["reason"]


def test_hotel_without_limits_keeps_its_price():
    node_id = next(n for n, c in CONFIGS.items() if c.get("kind") == "business" and c["facts"].get("rooms")
                   and not c["facts"].get("negotiation") and n in REGISTRY and "can_book" in c["capabilities"])
    client = TestClient(node_app(node_id))
    offer = signed_offer(node_id, room=CONFIGS[node_id]["facts"]["rooms"][0]["room_type"])
    envelope = client.post("/tools/counter_offer",
                           json={"counter": counter(offer, 1, 50), "offer": offer, "last": None}).json()
    assert envelope["payload"]["type"] == "rejection"


def test_a_counter_about_another_offer_is_refused():
    """A counter signed for offer A cannot be used to bargain over offer B of the same hotel."""
    client = TestClient(node_app(RHEINBLICK))
    offer_a, offer_b = signed_offer(offer_id="of-a"), signed_offer(offer_id="of-b")
    reply = ask(client, offer_b, counter(offer_a, 1, 160))["payload"]
    assert reply["status"] == "refused" and reply["reason"] == "counter is about another offer"
