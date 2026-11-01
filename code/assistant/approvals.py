"""Pending approvals between the assistant and the user's phone.

The assistant creates an approval and waits; the phone page decides it. The
decision is signed with the user's key (keys/user.json) and handed to the node,
which checks it. In a real deployment the key would live on the phone itself.

An approval can also offer a mandate for a small charge that will follow (e.g. the city
tax after a booking). If the user allows it while approving, the same key signs the mandate
(aps/mandate.py), and Tuttie pays that charge later without asking again.
"""

import asyncio
import secrets
from datetime import datetime, timedelta, timezone

from aps import load_signing_key
from aps.approval import sign_decision
from aps.mandate import sign_mandate

TIMEOUT_SECONDS = 300
MANDATE_DAYS = 3  # a mandate for a stay's charges ends soon after the stay


class ApprovalBook:
    """Approvals waiting for the phone, and the futures the assistant waits on."""

    def __init__(self):
        self.user_key = load_signing_key("user")
        self.pending: dict[str, dict] = {}
        self.futures: dict[str, asyncio.Future] = {}
        self.mandates: dict[tuple[str, str], dict] = {}  # (payee node_id, purpose) -> signed mandate

    def create(self, action: str, record: dict, amount_chf: float, summary: str, seals: list[dict],
               offer_mandate: dict | None = None, terms: dict | None = None, charge: dict | None = None) -> dict:
        """Register an approval request and return it (shown on the phone page).

        `offer_mandate` ({agent_id, purpose, max_chf}) asks the user whether a small charge of
        this business may be paid later without asking. `terms` (aps/approval.py,
        booking_terms) are what a booking is for, `charge` (payment_charge) what a payment is
        for; the user's signature covers them.
        """
        approval = {
            "id": "ap-" + secrets.token_hex(4),
            "action": action,
            "payee_node_id": record["node_id"],
            "payee_name": record["name"],
            "amount_chf": amount_chf,
            "summary": summary,
            "seals": seals,
            "offer_mandate": offer_mandate,
            "terms": terms,
            "charge": charge,
        }
        self.pending[approval["id"]] = approval
        self.futures[approval["id"]] = asyncio.get_running_loop().create_future()
        return approval

    def decide(self, approval_id: str, decision: str, allow_mandate: bool = False) -> dict | None:
        """Sign the user's decision (and the offered mandate, if allowed) and wake up the assistant.

        Everything is signed before the approval leaves `pending`, so a failure changes nothing
        (the phone can decide again). An offered mandate that cannot be signed (e.g. CHF 0) is
        left out: the decision still counts, and Tuttie asks for that charge on the phone later.
        """
        approval = self.pending.get(approval_id)
        if approval is None:
            return None
        signed = sign_decision(approval, decision, self.user_key)  # a bad decision raises here, nothing lost
        mandate = None
        offer = approval.get("offer_mandate")
        if decision == "approved" and allow_mandate and offer:
            expires = (datetime.now(timezone.utc) + timedelta(days=MANDATE_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                mandate = sign_mandate(offer["agent_id"], approval["payee_node_id"], offer["max_chf"],
                                       offer["purpose"], expires, self.user_key)
            except (ValueError, KeyError, TypeError, AttributeError):
                mandate = None
        del self.pending[approval_id]
        if mandate is not None:
            self.mandates[(approval["payee_node_id"], offer["purpose"])] = mandate
        future = self.futures.get(approval_id)  # wait() removes it once it has the result
        if future is not None and not future.done():
            future.set_result(signed)
        return signed

    async def wait(self, approval_id: str) -> dict:
        """Wait for the user's signed decision; no answer within the timeout counts as declined.

        A decision that lands while the timeout fires still counts (the future is done then).
        """
        future = self.futures[approval_id]
        try:
            return await asyncio.wait_for(asyncio.shield(future), TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            if future.done():
                return future.result()
            declined = self.decide(approval_id, "declined")
            return future.result() if future.done() else declined
        finally:
            self.futures.pop(approval_id, None)

    def clear(self) -> None:
        """Decline everything still pending (used when a new demo starts)."""
        for approval_id in list(self.pending):
            self.decide(approval_id, "declined")
