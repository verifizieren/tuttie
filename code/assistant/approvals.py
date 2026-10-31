"""Pending approvals between the assistant and the user's phone.

The assistant creates an approval and waits; the phone page decides it. The
decision is signed with the user's key (keys/user.json) and handed to the node,
which checks it. In a real deployment the key would live on the phone itself.
"""

import asyncio
import secrets

from aps import load_signing_key
from aps.approval import sign_decision

TIMEOUT_SECONDS = 300


class ApprovalBook:
    """Approvals waiting for the phone, and the futures the assistant waits on."""

    def __init__(self):
        self.user_key = load_signing_key("user")
        self.pending: dict[str, dict] = {}
        self.futures: dict[str, asyncio.Future] = {}

    def create(self, action: str, record: dict, amount_chf: float, summary: str, seals: list[dict]) -> dict:
        """Register an approval request and return it (shown on the phone page)."""
        approval = {
            "id": "ap-" + secrets.token_hex(4),
            "action": action,
            "payee_node_id": record["node_id"],
            "payee_name": record["name"],
            "amount_chf": amount_chf,
            "summary": summary,
            "seals": seals,
        }
        self.pending[approval["id"]] = approval
        self.futures[approval["id"]] = asyncio.get_running_loop().create_future()
        return approval

    def decide(self, approval_id: str, decision: str) -> dict | None:
        """Sign the user's decision and wake up the waiting assistant."""
        approval = self.pending.pop(approval_id, None)
        if approval is None:
            return None
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
