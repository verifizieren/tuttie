"""Redeeming a signed Agreement at booking: the end of a negotiation.

An Agreement (marketplace/messages.py) is the price both sides accepted, signed by the
business. When the guest books, the hotel takes the agreed price instead of the room's list
price plus commitments, but only if:

    - the Agreement carries this hotel's own signature (nobody else can grant its discount),
    - it is a valid Agreement and still before its valid_until,
    - it has not been redeemed before (one negotiated price, one booking).

The user's signed approval must then be for exactly the agreed price; `book` already checks
that against the total it computes, so the total is `agreement.price_chf`.

Hook for node/server.py (owner: dev member 1), inside `book`, instead of room + extras when
the request carries an agreement:

    agreements = AgreementRedeemer(node_id, own_public_key)        # once, in create_app
    ...
    if req.agreement is not None:                                  # BookRequest.agreement: dict | None
        try:
            agreement = agreements.check(req.agreement)
        except AgreementInvalid as error:
            return refuse(str(error))
        total, items = agreement.price_chf, agreement.includes
    ...
    agreements.mark_used(agreement)                                # next to used_approvals.add(...)
"""

from datetime import datetime, timezone

from pydantic import ValidationError

from aps import verify_envelope
from aps.envelope import parse_timestamp
from marketplace.messages import Agreement
from negotiation.hotel import message


class AgreementInvalid(Exception):
    """The agreement cannot be redeemed; the message says why (safe to send back)."""


class AgreementRedeemer:
    """Checks a hotel's own signed agreements and remembers which ones were booked."""

    def __init__(self, node_id: str, own_public_key: str):
        self.node_id = node_id
        self.own_public_key = own_public_key
        self.redeemed: set[str] = set()  # offer ids; in memory like the node's used approvals

    def check(self, envelope: dict, now: datetime | None = None) -> Agreement:
        """The agreement, if it can be redeemed now; raises AgreementInvalid otherwise."""
        if not isinstance(envelope, dict) or not verify_envelope(envelope, self.own_public_key, self.node_id):
            raise AgreementInvalid("the agreement is not signed by this hotel")
        try:
            agreement = Agreement.model_validate(message(envelope["payload"]))
        except (ValidationError, TypeError):
            raise AgreementInvalid("not a valid agreement") from None
        if parse_timestamp(agreement.valid_until) <= (now or datetime.now(timezone.utc)):
            raise AgreementInvalid("the agreement has expired")
        if agreement.offer_id in self.redeemed:
            raise AgreementInvalid("the agreement was already booked")
        return agreement

    def mark_used(self, agreement: Agreement) -> None:
        """Remember that this agreement was booked; call it only once the booking is confirmed."""
        self.redeemed.add(agreement.offer_id)
