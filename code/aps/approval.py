"""Signed approval decisions: the user's key over what exactly they approved.

A node that receives a decision checks it against the user's public key, so it
knows the user agreed to this action, this payee and this amount. A booking approval also
carries the `terms` the user saw (room type, night, rate, what is included); they are signed
with the rest, so the node can refuse to book anything else under this approval. A payment
approval carries the `charge` it is for ({purpose, booking_id}), signed the same way, so it
cannot pay another charge or another booking of the same amount.
"""

from nacl.signing import SigningKey

from aps.envelope import sign_bytes, utc_now, verify_bytes

DECISIONS = {"approved", "declined"}
FIELDS = ("approval_id", "action", "payee_node_id", "amount_chf", "decision", "decided_at")


def sign_decision(approval: dict, decision: str, signing_key: SigningKey) -> dict:
    """Sign the user's decision on an approval request with the user's key."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")
    body = {
        "approval_id": approval["id"],
        "action": approval["action"],
        "payee_node_id": approval["payee_node_id"],
        "amount_chf": approval["amount_chf"],
        "decision": decision,
        "decided_at": utc_now(),
    }
    if approval.get("terms") is not None:
        body["terms"] = approval["terms"]
    if approval.get("charge") is not None:
        body["charge"] = approval["charge"]
    return {**body, "signature": sign_bytes(signing_key, body)}


def verify_decision(decision: dict, public_key: str) -> bool:
    """True if the decision is complete and signed by `public_key`."""
    try:
        body = {k: decision[k] for k in FIELDS}
    except (KeyError, TypeError):
        return False
    for optional in ("terms", "charge"):  # optional, but signed whenever present
        if optional in decision:
            body[optional] = decision[optional]
    return verify_bytes(public_key, body, decision.get("signature", ""))


def booking_terms(room_type: str, date: str, rate: str | None, includes: list[str],
                  offer_id: str | None = None) -> dict:
    """The terms a booking approval is for, built the same way by the user's agent (before
    asking) and by the hotel (before booking), so both can compare them field by field.

    `offer_id` is set when the booking redeems a negotiated Agreement for that offer.
    """
    terms = {"room_type": room_type, "date": date, "rate": rate, "includes": list(includes)}
    if offer_id is not None:
        terms["offer_id"] = offer_id
    return terms


def payment_charge(purpose: str, booking_id: str) -> dict:
    """The charge a payment approval is for, built the same way by the user's agent (before
    asking) and by the business (before collecting), so both compare it as a whole."""
    return {"purpose": purpose, "booking_id": booking_id}
