"""Signed approval decisions: the user's key over what exactly they approved.

A node that receives a decision checks it against the user's public key, so it
knows the user agreed to this action, this payee and this amount.
"""

from nacl.signing import SigningKey

from aps.envelope import sign_bytes, utc_now, verify_bytes

DECISIONS = {"approved", "declined"}
FIELDS = ("approval_id", "action", "payee_node_id", "amount_chf", "decision", "decided_at")


def sign_decision(approval: dict, decision: str, signing_key: SigningKey) -> dict:
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
    return {**body, "signature": sign_bytes(signing_key, body)}


def verify_decision(decision: dict, public_key: str) -> bool:
    try:
        body = {k: decision[k] for k in FIELDS}
    except (KeyError, TypeError):
        return False
    return verify_bytes(public_key, body, decision.get("signature", ""))
