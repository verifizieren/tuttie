"""Payment mandates: the user's signed permission for small payments without asking each time.

Paying is never a delegation scope: every payment needs the user's own signature. Usually
that is an approval on the phone for exactly this amount (aps/approval.py). For small,
expected payments (the city tax, a late-arrival fee, a coffee) asking every time is
annoying, so the user can sign a mandate in advance:

    {
      "mandate_id": "md-3f9a2c1b",
      "agent_id": "ch.tuttie.alex-muster",      # only this agent may use it
      "payee_node_id": "ch.basel.gaestehaus-am-rhein",   # only to this business
      "max_chf": 20,                             # in total, over all payments with it
      "purpose": "city tax",                     # only for this
      "issued_at": "...", "expires_at": "...",
      "signature": "<user key over canonical {mandate_id, agent_id, payee_node_id, max_chf, purpose, issued_at, expires_at}>"
    }

Two rules on top of the mandate, so a mandate cannot be turned into a blank cheque:

    - one payment with a mandate is at most AUTO_PAY_LIMIT_CHF (CHF 10); above that the
      user approves the payment on the phone, mandate or not;
    - Tuttie pays with a mandate only to a payee whose seals verify as gold or blue
      (`may_auto_pay`, Tuttie's side). The business's side (aps/gate.py) checks the mandate
      itself: signed by the user, for this agent, this payee and this purpose, not expired,
      and still enough left of max_chf (the business counts what was paid with it).
"""

import secrets
from datetime import datetime, timezone

from nacl.signing import SigningKey

from aps.envelope import parse_timestamp, sign_bytes, utc_now, verify_bytes
from aps.seals import evaluate_record

AUTO_PAY_LIMIT_CHF = 10  # per payment; above this the user approves on the phone
AUTO_PAY_TIERS = {"gold", "blue"}
FIELDS = ("mandate_id", "agent_id", "payee_node_id", "max_chf", "purpose", "issued_at", "expires_at")


def sign_mandate(agent_id: str, payee_node_id: str, max_chf: float, purpose: str, expires_at: str,
                 user_key: SigningKey, mandate_id: str | None = None, issued_at: str | None = None) -> dict:
    """The user's key signs that `agent_id` may pay `payee_node_id` up to `max_chf` in total for `purpose`."""
    if not max_chf > 0:
        raise ValueError("max_chf must be positive")
    if not purpose.strip():
        raise ValueError("a mandate needs a purpose")
    if parse_timestamp(expires_at) is None:
        raise ValueError("expires_at must be an APS timestamp (YYYY-MM-DDTHH:MM:SSZ)")
    body = {
        "mandate_id": mandate_id or f"md-{secrets.token_hex(4)}",
        "agent_id": agent_id,
        "payee_node_id": payee_node_id,
        "max_chf": max_chf,
        "purpose": purpose,
        "issued_at": issued_at or utc_now(),
        "expires_at": expires_at,
    }
    return {**body, "signature": sign_bytes(user_key, body)}


def mandate_refusal(mandate: dict, user_public_key: str, agent_id: str, payee_node_id: str, purpose: str | None,
                    amount_chf: float, already_paid_chf: float = 0, now: datetime | None = None) -> str | None:
    """Why this mandate does not cover this payment, or None if it does.

    `purpose` is what the business charges for (None: any purpose); `already_paid_chf` is
    what was paid with this mandate before (the business keeps count).
    """
    try:
        body = {k: mandate[k] for k in FIELDS}
    except (KeyError, TypeError):
        return "the mandate is not a signed mandate"
    if not verify_bytes(user_public_key, body, mandate.get("signature", "")):
        return "the mandate is not signed by the user"
    if body["agent_id"] != agent_id:
        return "the mandate is for another agent"
    if body["payee_node_id"] != payee_node_id:
        return "the mandate is for another payee"
    if purpose is not None and body["purpose"] != purpose:
        return f"the mandate is for {body['purpose']}, not {purpose}"
    expires = parse_timestamp(body["expires_at"])
    if expires is None or expires <= (now or datetime.now(timezone.utc)):
        return "the mandate has expired"
    if amount_chf > AUTO_PAY_LIMIT_CHF:
        return f"CHF {amount_chf:g} is above the CHF {AUTO_PAY_LIMIT_CHF} a mandate covers; the user must approve it"
    if already_paid_chf + amount_chf > body["max_chf"]:
        return "the mandate's amount is used up"
    return None


def may_auto_pay(mandate: dict, user_public_key: str, agent_id: str, payee_record: dict, authorities: dict,
                 amount_chf: float, purpose: str | None = None, now: datetime | None = None) -> str | None:
    """Tuttie's side: why it must ask the user instead of paying with the mandate, or None.

    On top of the mandate itself, the payee's registry record must verify as gold or blue:
    an untrusted or forged business never gets money without the user looking at it.
    """
    tier = evaluate_record(payee_record, authorities)["tier"]
    if tier not in AUTO_PAY_TIERS:
        return f"the payee is {tier}; only gold or blue businesses are paid without asking"
    return mandate_refusal(mandate, user_public_key, agent_id, payee_record["node_id"], purpose, amount_chf, now=now)
