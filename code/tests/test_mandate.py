"""Payment mandates (aps/mandate.py) and `pay` through the action gate (aps/gate.py).

Real demo keys and registry: Gästehaus am Rhein (gold) as payee, Basel Budget Rooms
(unsigned → grey) and basel-cheap-hotels (forged seal → broken) as payees Tuttie must not
pay without asking.
"""

import asyncio
from datetime import timedelta

import pytest
from nacl.signing import SigningKey

from aps import load_signing_key
from aps.call import sign_call
from aps.gate import Needs
from aps.keys import load_public_key
from aps.mandate import AUTO_PAY_LIMIT_CHF, may_auto_pay, mandate_refusal, sign_mandate
from negotiation.hotel import load_authorities
from test_gate import HOTEL, NOW, REGISTRY, TUTTIE, approval, check, make_gate, stamp

USER = load_public_key("user")
PAY = Needs("pay", scope=None, approval=True, mandate=True, amount_chf=4, purpose="city tax")


def mandate(max_chf=10, payee=HOTEL, purpose="city tax", agent=TUTTIE, expires=NOW + timedelta(days=2), key=None,
            mandate_id="md-1") -> dict:
    return sign_mandate(agent, payee, max_chf, purpose, stamp(expires), key or load_signing_key("user"),
                        mandate_id=mandate_id)


def pay_call(args) -> dict:
    return sign_call("pay", args, TUTTIE, load_signing_key(TUTTIE), REGISTRY[TUTTIE]["delegation"])


# --- the mandate itself -----------------------------------------------------------------


def test_a_mandate_covers_small_payments_for_its_agent_payee_and_purpose():
    assert mandate_refusal(mandate(), USER, TUTTIE, HOTEL, "city tax", 4, now=NOW) is None
    assert mandate_refusal(mandate(), USER, TUTTIE, HOTEL, None, 4, now=NOW) is None  # any purpose
    assert mandate_refusal(mandate(), USER, TUTTIE, HOTEL, "city tax", 6, already_paid_chf=4, now=NOW) is None


@pytest.mark.parametrize("bad, kwargs, reason", [
    ("x", {}, "not a signed mandate"),
    (mandate(key=SigningKey.generate()), {}, "not signed by the user"),
    (mandate(agent="ch.someone.else"), {}, "for another agent"),
    (mandate(payee="ch.basel.hotel-rheinblick"), {}, "for another payee"),
    (mandate(purpose="minibar"), {}, "for minibar, not city tax"),
    (mandate(expires=NOW - timedelta(minutes=1)), {}, "expired"),
    (mandate(max_chf=50), {"amount_chf": 12}, "above the CHF 10 a mandate covers"),
    (mandate(max_chf=10), {"already_paid_chf": 8}, "used up"),
])
def test_a_mandate_refuses_what_it_does_not_cover(bad, kwargs, reason):
    args = {"amount_chf": 4, **kwargs}
    assert reason in mandate_refusal(bad, USER, TUTTIE, HOTEL, "city tax", now=NOW, **args)


def test_tampering_with_a_signed_mandate_breaks_it():
    raised = {**mandate(), "max_chf": 1000}
    assert mandate_refusal(raised, USER, TUTTIE, HOTEL, "city tax", 4, now=NOW) == "the mandate is not signed by the user"


def test_sign_mandate_rejects_nonsense():
    user = load_signing_key("user")
    with pytest.raises(ValueError):
        sign_mandate(TUTTIE, HOTEL, 0, "city tax", stamp(NOW), user)
    with pytest.raises(ValueError):
        sign_mandate(TUTTIE, HOTEL, 5, "  ", stamp(NOW), user)
    with pytest.raises(ValueError):
        sign_mandate(TUTTIE, HOTEL, 5, "city tax", "tomorrow", user)
    assert sign_mandate(TUTTIE, HOTEL, 5, "city tax", stamp(NOW), user)["mandate_id"].startswith("md-")


def test_tuttie_auto_pays_only_gold_or_blue_businesses():
    authorities = load_authorities()
    gold = REGISTRY[HOTEL]
    assert may_auto_pay(mandate(), USER, TUTTIE, gold, authorities, 4, "city tax", now=NOW) is None
    assert "above the CHF 10" in may_auto_pay(mandate(max_chf=50), USER, TUTTIE, gold, authorities, 11, now=NOW)
    for untrusted, tier in [("ch.basel.budget-rooms", "grey"), ("ch.basel.cheap-hotels", "broken")]:
        record = REGISTRY[untrusted]
        reason = may_auto_pay(mandate(payee=untrusted), USER, TUTTIE, record, authorities, 4, now=NOW)
        assert reason == f"the payee is {tier}; only gold or blue businesses are paid without asking"


# --- pay through the gate ---------------------------------------------------------------


def test_pay_with_a_mandate_passes_and_counts_what_was_paid():
    gate = make_gate()
    first = check(gate, pay_call({"amount_chf": 4, "purpose": "city tax", "mandate": mandate()}), PAY)
    assert first.ok, first.reason
    assert first.checks == ["caller", "signature", "delegation", "mandate"] and first.amount_chf == 4
    gate.commit(first)
    second = check(gate, pay_call({"mandate": mandate()}), PAY)
    assert second.ok
    gate.commit(second)  # 8 of 10 paid
    third = check(gate, pay_call({"mandate": mandate()}), PAY)
    assert third.reason == "the mandate's amount is used up"


def test_a_checked_but_not_committed_payment_uses_nothing():
    gate = make_gate()
    for _ in range(3):  # 3 × 4 > 10, but nothing was paid
        assert check(gate, pay_call({"mandate": mandate()}), PAY).ok


def test_pay_above_the_limit_needs_the_users_approval():
    big = Needs("pay", scope=None, approval=True, mandate=True, amount_chf=40, purpose="city tax")
    refused = check(make_gate(), pay_call({"mandate": mandate(max_chf=100)}), big)
    assert "the user must approve it" in refused.reason
    approved = check(make_gate(), pay_call({"approval": approval(40, action="pay")}), big)
    assert approved.ok and approved.checks[-1] == "approval"


def test_pay_without_approval_or_mandate_is_refused():
    assert check(make_gate(), pay_call({}), PAY).reason == "the approval is not signed by the user"


def test_a_mandate_is_not_accepted_where_the_action_does_not_allow_one():
    book = Needs("book", scope="book", approval=True, amount_chf=4)
    verdict = check(make_gate(), sign_call("book", {"mandate": mandate()}, TUTTIE, load_signing_key(TUTTIE),
                                           REGISTRY[TUTTIE]["delegation"]), book)
    assert verdict.reason == "the approval is not signed by the user"


def test_a_mandate_from_another_payee_or_purpose_is_refused_by_the_gate():
    other = check(make_gate(), pay_call({"mandate": mandate(payee="ch.basel.hotel-rheinblick")}), PAY)
    assert other.reason == "the mandate is for another payee"
    minibar = check(make_gate(), pay_call({"mandate": mandate(purpose="minibar")}), PAY)
    assert minibar.reason == "the mandate is for minibar, not city tax"


def test_pay_needs_a_valid_delegation_but_no_pay_scope():
    call = pay_call({"mandate": mandate()})
    call["delegation"] = {}
    undelegated = {TUTTIE: {**REGISTRY[TUTTIE], "delegation": {}}}
    assert check(make_gate(undelegated), call, PAY).reason.startswith("the user has not delegated anything to this agent")


def test_a_mandate_payment_needs_an_amount_from_the_business():
    no_amount = Needs("pay", scope=None, approval=True, mandate=True, purpose="city tax")
    assert check(make_gate(), pay_call({"mandate": mandate()}), no_amount).reason == "there is no amount to pay"


def test_the_auto_pay_limit_is_ten_francs():
    assert AUTO_PAY_LIMIT_CHF == 10  # agreed in status.md (C3); change it there and in formats.md too
