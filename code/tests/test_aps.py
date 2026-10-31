"""Tests for the aps library: envelopes, seals and the committed demo registry."""

import json
from pathlib import Path

import pytest
from nacl.signing import SigningKey

from aps import canonical, evaluate_record, issue_seal, public_key_b64, sign_envelope, verify_envelope

DATA = Path(__file__).resolve().parent.parent / "data"


def make_authority(issuer, tier, licenses=()):
    key = SigningKey.generate()
    entry = {"issuer": issuer, "tier": tier, "public_key": public_key_b64(key), "licenses": list(licenses)}
    return key, entry


def make_record(node_key, capabilities=("can_book", "can_take_payment")):
    return {
        "node_id": "ch.test.node",
        "public_key": public_key_b64(node_key),
        "capabilities": list(capabilities),
    }


@pytest.fixture
def authorities():
    gov_key, gov = make_authority("handelsregister-bs", "gold")
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
