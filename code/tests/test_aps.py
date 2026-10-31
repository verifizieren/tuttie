"""Tests for the aps library: envelopes, freshness, seals, Swiss UIDs and the committed demo registry."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from nacl.signing import SigningKey

from aps import (canonical, evaluate_record, is_valid_uid, issue_seal, public_key_b64, sign_envelope,
                 verify_envelope)
from aps.envelope import is_fresh
from aps.uid import check_digit

DATA = Path(__file__).resolve().parent.parent / "data"
TEST_UID = "CHE-786.579.750"  # made up, but with a correct check digit
NOW = datetime(2026, 11, 14, 0, 12, tzinfo=timezone.utc)


def make_authority(issuer, tier, licenses=(), vouches_for_uid=False):
    key = SigningKey.generate()
    entry = {"issuer": issuer, "tier": tier, "public_key": public_key_b64(key), "licenses": list(licenses),
             "vouches_for_uid": vouches_for_uid}
    return key, entry


def make_record(node_key, capabilities=("can_book", "can_take_payment"), uid=TEST_UID):
    return {
        "node_id": "ch.test.node",
        "uid": uid,
        "public_key": public_key_b64(node_key),
        "capabilities": list(capabilities),
    }


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def authorities():
    """Fresh authorities shaped like data/authorities.json (the register vouches for UIDs)."""
    gov_key, gov = make_authority("handelsregister-bs", "gold", vouches_for_uid=True)
    adobe_key, adobe = make_authority("adobe", "blue")
    bar_key, bar = make_authority("bar-association-ch", "gold", ["licensed_legal_ch"])
    keys = {"handelsregister-bs": gov_key, "adobe": adobe_key, "bar-association-ch": bar_key}
    return keys, {a["issuer"]: a for a in (gov, adobe, bar)}


def test_canonical_is_sorted_and_compact():
    assert canonical({"b": 1, "a": "ü"}) == '{"a":"ü","b":1}'.encode()


def test_envelope_roundtrip():
    key = SigningKey.generate()
    env = sign_envelope("ch.test.node", {"price_chf": 180}, key)
    assert verify_envelope(env, public_key_b64(key), expected_node_id="ch.test.node")


def test_tampered_payload_fails():
    key = SigningKey.generate()
    env = sign_envelope("ch.test.node", {"price_chf": 180}, key)
    env["payload"]["price_chf"] = 99
    assert not verify_envelope(env, public_key_b64(key))


def test_envelope_wrong_key_or_node_fails():
    key = SigningKey.generate()
    env = sign_envelope("ch.test.node", {"ok": True}, key)
    assert not verify_envelope(env, public_key_b64(SigningKey.generate()))
    assert not verify_envelope(env, public_key_b64(key), expected_node_id="ch.other.node")
    assert not verify_envelope({"payload": {}}, public_key_b64(key))


def test_valid_seals_verify(authorities):
    keys, auths = authorities
    record = make_record(SigningKey.generate())
    record["seals"] = [
        issue_seal(record, "handelsregister-bs", "gold", keys["handelsregister-bs"]),
        issue_seal(record, "adobe", "blue", keys["adobe"]),
    ]
    verdict = evaluate_record(record, auths)
    assert verdict["tier"] == "gold"
    assert all(s["valid"] for s in verdict["seals"])
    assert verdict["capabilities"] == ["can_book", "can_take_payment"]


def test_scam_seal_signed_with_own_key_is_broken(authorities):
    _, auths = authorities
    node_key = SigningKey.generate()
    record = make_record(node_key)
    record["seals"] = [issue_seal(record, "handelsregister-bs", "gold", node_key)]
    verdict = evaluate_record(record, auths)
    assert verdict["tier"] == "broken"
    assert verdict["capabilities"] == []


def test_seal_breaks_when_record_is_changed(authorities):
    keys, auths = authorities
    record = make_record(SigningKey.generate())
    record["seals"] = [issue_seal(record, "adobe", "blue", keys["adobe"])]
    record["capabilities"].append("licensed_legal_ch")
    assert evaluate_record(record, auths)["tier"] == "broken"


def test_wrong_tier_or_unknown_issuer_is_broken(authorities):
    keys, auths = authorities
    record = make_record(SigningKey.generate())
    record["seals"] = [issue_seal(record, "adobe", "gold", keys["adobe"])]
    assert evaluate_record(record, auths)["tier"] == "broken"
    record["seals"] = [issue_seal(record, "nobody", "gold", SigningKey.generate())]
    assert evaluate_record(record, auths)["tier"] == "broken"


def test_self_signed_is_grey_without_licence_or_payment(authorities):
    _, auths = authorities
    node_key = SigningKey.generate()
    record = make_record(node_key, ["licensed_legal_ch", "can_take_payment", "can_answer"])
    record["seals"] = [issue_seal(record, record["node_id"], "grey", node_key)]
    verdict = evaluate_record(record, auths)
    assert verdict["tier"] == "grey"
    assert verdict["capabilities"] == ["can_answer"]


def test_unsigned_node_is_grey_without_licence_or_payment(authorities):
    _, auths = authorities
    record = make_record(SigningKey.generate(), ["can_book", "can_take_payment", "licensed_legal_ch"])
    record["seals"] = []
    verdict = evaluate_record(record, auths)
    assert verdict["tier"] == "grey"
    assert verdict["capabilities"] == ["can_book"]


def test_licensed_capability_needs_licensing_authority(authorities):
    keys, auths = authorities
    record = make_record(SigningKey.generate(), ["licensed_legal_ch"])
    record["seals"] = [issue_seal(record, "adobe", "blue", keys["adobe"])]
    assert evaluate_record(record, auths)["capabilities"] == []
    record["seals"].append(issue_seal(record, "bar-association-ch", "gold", keys["bar-association-ch"]))
    assert evaluate_record(record, auths)["capabilities"] == ["licensed_legal_ch"]


def test_demo_registry_verdicts():
    """The committed demo data must produce exactly the verdicts the demo relies on."""
    auths = {a["issuer"]: a for a in json.loads((DATA / "authorities.json").read_text())}
    records = {r["node_id"]: r for r in json.loads((DATA / "registry.json").read_text())}
    tiers = {node_id: evaluate_record(r, auths)["tier"] for node_id, r in records.items()}
    assert tiers == {
        "ch.basel.hotel-rheinblick": "gold",
        "ch.basel.hotel-spalenhof": "blue",
        "ch.basel.hotel-gundeli": "gold",
        "ch.basel.budget-rooms": "grey",
        "ch.basel.cheap-hotels": "broken",
        "ch.legal.consumer-law": "gold",
        "ch.legal.advisor": "grey",
    }
    assert "licensed_legal_ch" in evaluate_record(records["ch.legal.consumer-law"], auths)["capabilities"]
    assert "licensed_legal_ch" not in evaluate_record(records["ch.legal.advisor"], auths)["capabilities"]


def test_approval_decision_verifies_and_detects_tampering():
    from aps.approval import sign_decision, verify_decision

    user_key = SigningKey.generate()
    approval = {"id": "ap-1", "action": "book", "payee_node_id": "ch.test.node", "amount_chf": 195}
    decision = sign_decision(approval, "approved", user_key)
    assert verify_decision(decision, public_key_b64(user_key))
    assert not verify_decision({**decision, "amount_chf": 1}, public_key_b64(user_key))
    assert not verify_decision(decision, public_key_b64(SigningKey.generate()))
    with pytest.raises(ValueError):
        sign_decision(approval, "maybe", user_key)


# --- envelope freshness -------------------------------------------------------------


def test_fresh_envelope_verifies_with_max_age():
    key = SigningKey.generate()
    env = sign_envelope("ch.test.node", {"ok": True}, key, timestamp=stamp(NOW - timedelta(seconds=30)))
    assert verify_envelope(env, public_key_b64(key), "ch.test.node", max_age_s=300, now=NOW)


def test_old_envelope_is_rejected_only_when_freshness_is_asked_for():
    key = SigningKey.generate()
    env = sign_envelope("ch.test.node", {"price_chf": 99}, key, timestamp=stamp(NOW - timedelta(hours=1)))
    assert not verify_envelope(env, public_key_b64(key), max_age_s=300, now=NOW)
    assert verify_envelope(env, public_key_b64(key))  # kept envelopes (commitments) still verify


def test_freshness_rejects_future_and_malformed_timestamps():
    assert is_fresh(stamp(NOW + timedelta(seconds=30)), 300, NOW)  # small clock skew is fine
    assert not is_fresh(stamp(NOW + timedelta(minutes=5)), 300, NOW)
    assert not is_fresh("2026-11-14 00:12:00", 300, NOW)
    assert not is_fresh(None, 300, NOW)


def test_backdated_timestamp_breaks_the_signature():
    """The timestamp is signed, so making an old envelope look fresh breaks it."""
    key = SigningKey.generate()
    env = sign_envelope("ch.test.node", {"ok": True}, key, timestamp=stamp(NOW - timedelta(hours=1)))
    env["timestamp"] = stamp(NOW)
    assert not verify_envelope(env, public_key_b64(key), max_age_s=300, now=NOW)


# --- Swiss UIDs ---------------------------------------------------------------------


def test_uid_check_digit():
    assert is_valid_uid("CHE-116.281.710")  # a published UID; its check digit is 0 (11 -> 0)
    assert is_valid_uid(TEST_UID)
    assert not is_valid_uid("CHE-116.281.711")  # wrong check digit
    assert check_digit("00000003") is None  # remainder 1 would need digit 10: no valid UID


def test_uid_format():
    for bad in ("CHE116281710", "che-116.281.710", "CHE-116.281.710 ", "CHE-116.281.71", "", None, 116281710):
        assert not is_valid_uid(bad)


def test_register_seal_verifies_the_uid(authorities):
    keys, auths = authorities
    record = make_record(SigningKey.generate())
    record["seals"] = [issue_seal(record, "handelsregister-bs", "gold", keys["handelsregister-bs"])]
    verdict = evaluate_record(record, auths)
    assert verdict["tier"] == "gold" and verdict["uid"] == TEST_UID


def test_register_seal_needs_a_valid_uid(authorities):
    keys, auths = authorities
    for uid in (None, "CHE-116.281.711"):
        record = make_record(SigningKey.generate(), uid=uid)
        record["seals"] = [issue_seal(record, "handelsregister-bs", "gold", keys["handelsregister-bs"])]
        assert evaluate_record(record, auths)["tier"] == "broken"


def test_changing_the_uid_breaks_every_seal(authorities):
    keys, auths = authorities
    record = make_record(SigningKey.generate())
    record["seals"] = [issue_seal(record, "adobe", "blue", keys["adobe"])]
    record["uid"] = "CHE-116.281.710"
    assert evaluate_record(record, auths)["tier"] == "broken"


def test_uid_without_register_seal_is_only_a_claim(authorities):
    keys, auths = authorities
    record = make_record(SigningKey.generate())
    record["seals"] = [issue_seal(record, "adobe", "blue", keys["adobe"])]
    verdict = evaluate_record(record, auths)
    assert verdict["tier"] == "blue" and verdict["uid"] is None
    record["seals"] = []
    assert evaluate_record(record, auths)["uid"] is None


def test_demo_registry_uids():
    """Only nodes sealed by the commercial register show a verified UID in the demo."""
    auths = {a["issuer"]: a for a in json.loads((DATA / "authorities.json").read_text())}
    records = json.loads((DATA / "registry.json").read_text())
    uids = {r["node_id"]: evaluate_record(r, auths)["uid"] for r in records}
    assert {node_id for node_id, uid in uids.items() if uid} == {"ch.basel.hotel-rheinblick", "ch.basel.hotel-gundeli"}
    assert all(is_valid_uid(r["uid"]) for r in records if r["uid"])
