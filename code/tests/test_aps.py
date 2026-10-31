"""Tests for the aps library: envelopes, freshness, seals, Swiss UIDs and the committed demo registry."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from nacl.signing import SigningKey

from aps import (canonical, evaluate_record, is_valid_uid, issue_seal, public_key_b64, sign_envelope,
                 verify_envelope)
from aps.delegation import sign_delegation, verify_delegation
from aps.envelope import is_fresh
from aps.keys import load_public_key
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
        "ch.basel.alpina-grand": "gold",
        "ch.basel.gaestehaus-am-rhein": "gold",
        "ch.basel.cheap-hotels": "broken",
        "ch.legal.consumer-law": "gold",
        "ch.legal.advisor": "grey",
        "ch.tuttie.alex-muster": "blue",
        "ch.weather.open-meteo": "gold",     # services/: public information, signed
        "ch.transport.timetable": "gold",
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
    assert {node_id for node_id, uid in uids.items() if uid} == {
        "ch.basel.hotel-rheinblick", "ch.basel.hotel-gundeli", "ch.basel.alpina-grand", "ch.basel.gaestehaus-am-rhein",
        "ch.weather.open-meteo", "ch.transport.timetable"}
    assert all(is_valid_uid(r["uid"]) for r in records if r["uid"])


# --- delegations (Tuttie acts for the user) --------------------------------------------


def make_delegation(user_key, agent_key, scopes=("ask_agents", "negotiate"), expires_at="2027-01-01T00:00:00Z"):
    return sign_delegation("ch.tuttie.test", public_key_b64(agent_key), list(scopes), expires_at, user_key,
                           issued_at=stamp(NOW))


def test_delegation_verifies_for_its_agent_and_scope():
    user_key, agent_key = SigningKey.generate(), SigningKey.generate()
    delegation = make_delegation(user_key, agent_key)
    args = (public_key_b64(user_key), "ch.tuttie.test", public_key_b64(agent_key))
    assert verify_delegation(delegation, *args, now=NOW)
    assert verify_delegation(delegation, *args, scope="negotiate", now=NOW)
    assert not verify_delegation(delegation, *args, scope="post_requests", now=NOW)


def test_delegation_rejects_other_agent_key_user_or_tampering():
    user_key, agent_key = SigningKey.generate(), SigningKey.generate()
    delegation = make_delegation(user_key, agent_key)
    user, agent = public_key_b64(user_key), public_key_b64(agent_key)
    assert not verify_delegation(delegation, user, "ch.other.agent", agent, now=NOW)
    assert not verify_delegation(delegation, user, "ch.tuttie.test", public_key_b64(SigningKey.generate()), now=NOW)
    assert not verify_delegation(delegation, public_key_b64(SigningKey.generate()), "ch.tuttie.test", agent, now=NOW)
    widened = {**delegation, "scopes": ["ask_agents", "negotiate", "post_requests"]}
    assert not verify_delegation(widened, user, "ch.tuttie.test", agent, now=NOW)
    assert not verify_delegation({"agent_id": "ch.tuttie.test"}, user, "ch.tuttie.test", agent, now=NOW)


def test_delegation_expires():
    user_key, agent_key = SigningKey.generate(), SigningKey.generate()
    delegation = make_delegation(user_key, agent_key, expires_at=stamp(NOW - timedelta(seconds=1)))
    assert not verify_delegation(delegation, public_key_b64(user_key), "ch.tuttie.test",
                                 public_key_b64(agent_key), now=NOW)


def test_delegation_refuses_unknown_scopes_and_bad_expiry():
    """Paying is never delegated: it always needs the user's own approval."""
    user_key, agent_key = SigningKey.generate(), SigningKey.generate()
    with pytest.raises(ValueError):
        make_delegation(user_key, agent_key, scopes=("pay",))
    with pytest.raises(ValueError):
        make_delegation(user_key, agent_key, expires_at="next year")


def test_demo_tuttie_acts_for_the_demo_user():
    records = {r["node_id"]: r for r in json.loads((DATA / "registry.json").read_text())}
    tuttie = records["ch.tuttie.alex-muster"]
    assert tuttie["kind"] == "user-agent"
    assert verify_delegation(tuttie["delegation"], load_public_key("user"), tuttie["node_id"],
                             tuttie["public_key"], scope="post_requests")


# --- key files and remaining edge cases ----------------------------------------------------


def test_key_files_are_created_once_and_round_trip(tmp_path):
    from aps.keys import generate_key_file, load_public_key as load_public, load_signing_key as load_signing

    path = generate_key_file("ch.test.node", tmp_path / "keys")
    first = path.read_text()
    assert generate_key_file("ch.test.node", tmp_path / "keys").read_text() == first  # kept, not regenerated
    key = load_signing(("ch.test.node"), tmp_path / "keys")
    assert public_key_b64(key) == load_public("ch.test.node", tmp_path / "keys") == json.loads(first)["public_key"]
    env = sign_envelope("ch.test.node", {"ok": True}, key)
    assert verify_envelope(env, load_public("ch.test.node", tmp_path / "keys"))


def test_incomplete_approval_decision_does_not_verify():
    from aps.approval import sign_decision, verify_decision

    user_key = SigningKey.generate()
    approval = {"id": "ap-1", "action": "book", "payee_node_id": "ch.test.node", "amount_chf": 195}
    decision = sign_decision(approval, "approved", user_key)
    del decision["decided_at"]
    assert not verify_decision(decision, public_key_b64(user_key))
    assert not verify_decision(None, public_key_b64(user_key))


def test_self_signed_seal_cannot_claim_a_higher_tier(authorities):
    _, auths = authorities
    node_key = SigningKey.generate()
    record = make_record(node_key)
    record["seals"] = [issue_seal(record, record["node_id"], "gold", node_key)]
    assert evaluate_record(record, auths)["tier"] == "broken"
