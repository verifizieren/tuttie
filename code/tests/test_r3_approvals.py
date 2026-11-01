"""Round 3 attacker: approvals and mandates (assistant/approvals.py, node/settings.py)."""

import asyncio

import pytest

from assistant import approvals as approvals_mod
from assistant.approvals import ApprovalBook
from node.settings import validate

RECORD = {"node_id": "ch.basel.gaestehaus-am-rhein", "name": "Gästehaus"}


def test_owner_cannot_deploy_a_zero_franc_charge():
    """A CHF 0 charge is refused by the owner's settings check (it would offer a CHF 0 mandate)."""
    settings, errors = validate({"facts": {"charges": [{"purpose": "city tax", "price_chf": 0}]}})
    assert settings is None and errors


def test_zero_franc_mandate_offer_breaks_the_approval():
    """Tuttie's mandate_offer offers max_chf = charge price (0 <= AUTO_PAY_LIMIT), and the owner may
    deploy a CHF 0 charge. Approving with allow_mandate then raises in sign_mandate AFTER the
    approval was popped from pending, so the future is never resolved: the HTTP decide answers
    500, the approval is gone, and wait() returns None after the timeout, which crashes
    _approve_and_book on decision["decision"]. Expected: the booking approval still resolves."""
    async def run():
        book = ApprovalBook()
        offer = {"agent_id": "ch.tuttie.alex-muster", "purpose": "city tax", "max_chf": 0, "price_chf": 0}
        approval = book.create("book", RECORD, 95, "Book", [], offer)
        try:
            book.decide(approval["id"], "approved", allow_mandate=True)
        except ValueError:
            pass
        approvals_mod.TIMEOUT_SECONDS = 0.05
        try:
            return await book.wait(approval["id"])
        finally:
            approvals_mod.TIMEOUT_SECONDS = 300
    decision = asyncio.run(run())
    assert decision is not None and decision["decision"] == "approved"


def test_wait_returns_none_when_decide_lands_at_the_timeout():
    """decide() during wait_for's cancel step: wait_for raises TimeoutError although the user
    decided; wait() then calls decide('declined'), which finds nothing and returns None."""
    async def once():
        book = ApprovalBook()
        approval = book.create("pay", RECORD, 4, "Pay", [])
        approvals_mod.TIMEOUT_SECONDS = 0.01
        loop = asyncio.get_running_loop()
        # Run decide on the iteration right after the timeout fires (inside _cancel_and_wait).
        def timer():
            loop.call_soon(book.decide, approval["id"], "approved")
        loop.call_later(0.01, timer)
        return await book.wait(approval["id"])
    results = []
    for _ in range(50):
        results.append(asyncio.run(once()))
    approvals_mod.TIMEOUT_SECONDS = 300
    assert None not in results, f"{results.count(None)}/50 waits returned None"
