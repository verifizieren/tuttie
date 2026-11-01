"""Delegations: the user's signed statement that an agent (Tuttie) acts on their behalf.

A seal says who an agent *is*; a delegation says *for whom it speaks and what it may do*.
The user's key signs the agent's id and public key, the scopes it gets and an expiry.
A business that receives a message from the agent can check the delegation against the
user's public key, so nobody can run an agent "for" a user without the user's key.

Scopes: "ask_agents", "post_requests", "negotiate", and "book" (the agent may run the book
action for the user; aps/gate.py checks it). A scope never replaces the user's approval:
every booking and payment still needs the user's own signed approval on the phone for its
exact amount (aps/approval.py). Paying is not a scope (yet; see the open payment mandate).
"""

from datetime import datetime

from nacl.signing import SigningKey

from aps.envelope import parse_timestamp, sign_bytes, utc_now, verify_bytes

SCOPES = {"post_requests", "ask_agents", "negotiate", "book"}  # "book" still needs a signed approval per booking
FIELDS = ("agent_id", "agent_public_key", "scopes", "issued_at", "expires_at")


def sign_delegation(agent_id: str, agent_public_key: str, scopes: list[str], expires_at: str,
                    user_key: SigningKey, issued_at: str | None = None) -> dict:
    """The user's key signs that `agent_id` (with this key) may act for them within `scopes`."""
    unknown = set(scopes) - SCOPES
    if unknown:
        raise ValueError(f"unknown scopes {sorted(unknown)}; allowed: {sorted(SCOPES)}")
    if parse_timestamp(expires_at) is None:
        raise ValueError("expires_at must be an APS timestamp (YYYY-MM-DDTHH:MM:SSZ)")
    body = {
        "agent_id": agent_id,
        "agent_public_key": agent_public_key,
        "scopes": sorted(scopes),
        "issued_at": issued_at or utc_now(),
        "expires_at": expires_at,
    }
    return {**body, "signature": sign_bytes(user_key, body)}


def verify_delegation(delegation: dict, user_public_key: str, agent_id: str, agent_public_key: str,
                      scope: str | None = None, now: datetime | None = None) -> bool:
    """True if the user signed this delegation for exactly this agent and key, it has not
    expired at `now`, and (if given) it grants `scope`.

    The agent id and key are passed in from the agent's verified registry record, so a
    delegation copied onto another agent does not verify.
    """
    try:
        body = {k: delegation[k] for k in FIELDS}
    except (KeyError, TypeError):
        return False
    if body["agent_id"] != agent_id or body["agent_public_key"] != agent_public_key:
        return False
    expires = parse_timestamp(body["expires_at"])
    if expires is None or expires <= (now or datetime.now(expires.tzinfo)):
        return False
    if not isinstance(body["scopes"], list):
        return False  # a string would turn `scope in scopes` into a substring test
    if scope is not None and scope not in body["scopes"]:
        return False
    return verify_bytes(user_public_key, body, delegation.get("signature", ""))
