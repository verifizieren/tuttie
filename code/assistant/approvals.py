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
               offer_mandate: dict | None = None, terms: dict | None = None) -> dict:
        """Register an approval request and return it (shown on the phone page).

        `offer_mandate` ({agent_id, purpose, max_chf}) asks the user whether a small charge of
        this business may be paid later without asking. `terms` (aps/approval.py,
        booking_terms) are what a booking is for; the user's signature covers them.
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
        }
        self.pending[approval["id"]] = approval
        self.futures[approval["id"]] = asyncio.get_running_loop().create_future()
        return approval

    def decide(self, approval_id: str, decision: str, allow_mandate: bool = False) -> dict | None:
        """Sign the user's decision (and the offered mandate, if allowed) and wake up the assistant."""
        approval = self.pending.pop(approval_id, None)
        if approval is None:
            return None
        offer = approval.get("offer_mandate")
        if decision == "approved" and allow_mandate and offer:
            expires = (datetime.now(timezone.utc) + timedelta(days=MANDATE_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.mandates[(approval["payee_node_id"], offer["purpose"])] = sign_mandate(
                offer["agent_id"], approval["payee_node_id"], offer["max_chf"], offer["purpose"], expires, self.user_key)
        signed = sign_decision(approval, decision, self.user_key)
        self.futures.pop(approval_id).set_result(signed)
        return signed

    async def wait(self, approval_id: str) -> dict:
        """Wait for the user's signed decision; no answer within the timeout counts as declined."""
        try:
            return await asyncio.wait_for(asyncio.shield(self.futures[approval_id]), TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            return self.decide(approval_id, "declined")

    def clear(self) -> None:
        """Decline everything still pending (used when a new demo starts)."""
        for approval_id in list(self.pending):
            self.decide(approval_id, "declined")
