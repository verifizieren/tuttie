"""The action gate (aps/gate.py): a booking runs only with every signature in place.

Real demo keys and the real registry record of Tuttie; one test per refusal, named by the
signature that is missing.
"""

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from nacl.signing import SigningKey

from aps import load_signing_key, public_key_b64, sign_envelope
from aps.approval import sign_decision
from aps.call import CALL_MAX_AGE_S, sign_call
from aps.delegation import sign_delegation
from aps.gate import ActionGate, Needs
from aps.keys import load_public_key
from negotiation.agreement import AgreementRedeemer
from negotiation.hotel import load_authorities

DATA = Path(__file__).resolve().parent.parent / "data"
REGISTRY = {r["node_id"]: r for r in json.loads((DATA / "registry.json").read_text())}
TUTTIE = "ch.tuttie.alex-muster"
HOTEL = "ch.basel.gaestehaus-am-rhein"
NOW = datetime.now(timezone.utc)
BOOK = Needs("book", scope="book", approval=True, amount_chf=135)


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_gate(records=None, agreements=True) -> ActionGate:
    records = REGISTRY if records is None else records

    async def lookup(node_id):
        return records.get(node_id)

    redeemer = AgreementRedeemer(HOTEL, load_public_key(HOTEL)) if agreements else None
    return ActionGate(HOTEL, load_public_key(HOTEL), load_public_key("user"), load_authorities(), lookup, redeemer)


def approval(amount=135, action="book", payee=HOTEL, decision="approved", approval_id="ap-1", key=None) -> dict:
    request = {"id": approval_id, "action": action, "payee_node_id": payee, "amount_chf": amount}
    return sign_decision(request, decision, key or load_signing_key("user"))


def agreement(price=128, valid_until=NOW + timedelta(hours=2), key=None) -> dict:
    payload = {"type": "agreement", "request_id": "rq-1", "offer_id": "of-gaestehaus-1", "round": 3,
               "item": "double room 2026-11-14", "price_chf": price, "includes": ["late arrival with dog"],
               "conditions": ["flexible rate"], "valid_until": stamp(valid_until)}
    return sign_envelope(HOTEL, {"tool": "counter_offer", **payload}, key or load_signing_key(HOTEL))


def book_call(args=None, tool="book", agent=TUTTIE, key=None, **kwargs) -> dict:
    args = {"date": "2026-11-14", "room_type": "double", "approval": approval()} if args is None else args
    return sign_call(tool, args, agent, key or load_signing_key(agent), REGISTRY[TUTTIE]["delegation"], **kwargs)


def check(gate, call, needs=BOOK, now=None):
    return asyncio.run(gate.check_action(call, needs, now=now))


# --- passing ----------------------------------------------------------------------------


def test_a_fully_signed_booking_passes_and_lists_its_checks():
    verdict = check(make_gate(), book_call())
    assert verdict.ok, verdict.reason
    assert verdict.checks == ["caller", "signature", "delegation", "approval"]
    assert verdict.amount_chf == 135 and verdict.caller["node_id"] == TUTTIE


def test_an_agreement_sets_the_amount_the_user_must_approve():
    gate = make_gate()
    call = book_call({"date": "2026-11-14", "approval": approval(128), "agreement": agreement(128)})
    verdict = check(gate, call, Needs("book", scope="book", approval=True))  # no own total needed
    assert verdict.ok, verdict.reason
    assert verdict.checks == ["caller", "signature", "delegation", "agreement", "approval"]
    assert verdict.amount_chf == 128 and verdict.agreement.price_chf == 128


def test_the_delegation_falls_back_to_the_registry_record():
    call = book_call()
    del call["delegation"]  # outside the signature, so the call still verifies
    assert check(make_gate(), call).ok


def test_an_action_without_approval_needs_only_caller_signature_and_scope():
    verdict = check(make_gate(), book_call(args={}), Needs("book", scope="book"))
    assert verdict.ok and verdict.checks == ["caller", "signature", "delegation"]


# --- refusals: one per missing signature ------------------------------------------------


def test_refuses_a_call_that_is_not_a_signed_call():
    for bad in ({}, "book", {**book_call(), "args": "x"}):
        assert check(make_gate(), bad).reason == "the call is not a signed call"


def test_refuses_a_call_for_another_tool():
    verdict = check(make_gate(), book_call(tool="pay"))
    assert not verdict.ok and verdict.reason == "the call is for pay, not book"


def test_refuses_an_unknown_caller_or_one_that_is_not_a_user_agent():
    key = SigningKey.generate()
    assert check(make_gate(), book_call(agent="ch.nobody.agent", key=key)).reason == "the caller is not a known user agent"
    hotel_call = sign_call("book", {}, HOTEL, load_signing_key(HOTEL))
    assert check(make_gate(), hotel_call).reason == "the caller is not a known user agent"


def test_refuses_a_caller_whose_seals_are_forged():
    forged = copy.deepcopy(REGISTRY[TUTTIE])
    forged["seals"][0]["signature"] = forged["seals"][1 % len(forged["seals"])]["signature"][::-1]
    verdict = check(make_gate({TUTTIE: forged}), book_call())
    assert verdict.reason == "the caller's seals do not verify" and verdict.checks == []


def test_refuses_a_caller_without_a_verified_seal():
    unsealed = {**REGISTRY[TUTTIE], "seals": []}
    assert check(make_gate({TUTTIE: unsealed}), book_call()).reason == "the caller has no verified seal"


def test_refuses_a_call_signed_with_another_key():
    verdict = check(make_gate(), book_call(key=SigningKey.generate()))
    assert verdict.reason == "the call is not signed by the caller's key" and verdict.checks == ["caller"]


def test_refuses_tampered_args():
    call = book_call()
    call["args"]["approval"] = approval(1)
    assert check(make_gate(), call).reason == "the call is not signed by the caller's key"


def test_refuses_an_outdated_call():
    old = book_call(timestamp=stamp(NOW - timedelta(seconds=CALL_MAX_AGE_S + 5)))
    assert check(make_gate(), old, now=NOW).reason == "the call is outdated (possible replay)"


def test_refuses_a_replayed_nonce_even_after_a_refusal():
    gate = make_gate()
    call = book_call()
    assert check(gate, call).ok
    assert check(gate, call).reason == "the call was already used (replayed nonce)"
    wrong = book_call(args={"approval": approval(99)})
    assert not check(gate, wrong).ok
    assert check(gate, wrong).reason == "the call was already used (replayed nonce)"


def test_refuses_a_delegation_without_the_scope():
    agent_key = public_key_b64(load_signing_key(TUTTIE))
    narrow = sign_delegation(TUTTIE, agent_key, ["ask_agents", "negotiate"], stamp(NOW + timedelta(days=1)),
                             load_signing_key("user"))
    verdict = check(make_gate(), book_call() | {"delegation": narrow})
    assert verdict.reason.startswith("the user has not delegated book to this agent")
    assert verdict.checks == ["caller", "signature"]


def test_refuses_an_expired_or_foreign_delegation():
    agent_key = public_key_b64(load_signing_key(TUTTIE))
    expired = sign_delegation(TUTTIE, agent_key, ["book"], stamp(NOW + timedelta(days=1)), load_signing_key("user"),
                              issued_at=stamp(NOW - timedelta(days=30)))
    gate = make_gate()
    assert check(gate, book_call() | {"delegation": expired}, now=NOW + timedelta(days=2)).reason.startswith(
        "the call is outdated")  # an old call fails first; a fresh one with the old delegation:
    late = NOW + timedelta(days=2)
    fresh = book_call(timestamp=stamp(late)) | {"delegation": expired}
    assert check(gate, fresh, now=late).reason.startswith("the user has not delegated book")
    self_signed = sign_delegation(TUTTIE, agent_key, ["book"], stamp(NOW + timedelta(days=1)), SigningKey.generate())
    assert check(gate, book_call() | {"delegation": self_signed}).reason.startswith("the user has not delegated book")


@pytest.mark.parametrize("bad, reason", [
    (None, "the approval is not signed by the user"),
    (approval(key=SigningKey.generate()), "the approval is not signed by the user"),
    (approval(decision="declined"), "the approval does not approve book with this business"),
    (approval(payee="ch.basel.hotel-rheinblick"), "the approval does not approve book with this business"),
    (approval(action="pay"), "the approval does not approve book with this business"),
    (approval(120), "approved CHF 120 does not match the total CHF 135"),
])
def test_refuses_an_approval_that_does_not_cover_this_booking(bad, reason):
    args = {"room_type": "double"} if bad is None else {"room_type": "double", "approval": bad}
    verdict = check(make_gate(), book_call(args))
    assert verdict.reason == reason and verdict.checks == ["caller", "signature", "delegation"]


def test_refuses_an_approval_without_an_amount_to_compare():
    verdict = check(make_gate(), book_call(), Needs("book", scope="book", approval=True))
    assert verdict.reason == "there is no amount to approve"


def test_refuses_an_approval_used_twice_once_committed():
    gate = make_gate()
    first = check(gate, book_call())
    assert check(gate, book_call()).ok  # not used up until the booking succeeded
    gate.commit(first)
    assert check(gate, book_call()).reason == "the approval was already used"


def test_refuses_an_agreement_the_hotel_did_not_sign_has_expired_or_was_booked():
    args = lambda env: {"approval": approval(128), "agreement": env}  # noqa: E731
    gate = make_gate()
    forged = agreement(key=SigningKey.generate())
    assert check(gate, book_call(args(forged))).reason == "the agreement is not signed by this hotel"
    expired = agreement(valid_until=NOW - timedelta(minutes=1))
    assert check(gate, book_call(args(expired))).reason == "the agreement has expired"
    good = check(gate, book_call(args(agreement())))
    gate.commit(good)
    assert check(gate, book_call(args(agreement()) | {"approval": approval(128, approval_id="ap-2")})).reason == (
        "the agreement was already booked")


def test_refuses_an_agreement_where_the_business_does_not_negotiate():
    verdict = check(make_gate(agreements=False), book_call({"approval": approval(128), "agreement": agreement()}))
    assert verdict.reason.startswith("this business does not negotiate")


def test_the_approval_must_match_the_agreed_price_not_the_list_price():
    call = book_call({"approval": approval(135), "agreement": agreement(128)})
    assert check(make_gate(), call).reason == "approved CHF 135 does not match the total CHF 128"


def test_only_a_passed_verdict_can_be_committed():
    verdict = check(make_gate(), book_call(tool="pay"))
    with pytest.raises(ValueError):
        make_gate().commit(verdict)
