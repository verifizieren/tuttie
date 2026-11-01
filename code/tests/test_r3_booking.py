"""Round 3 attacker: booking and paying at the node (node/server.py, aps/gate.py)."""

import asyncio
import json
from pathlib import Path

from mcp import Client

from aps import load_signing_key, sign_envelope
from aps.approval import booking_terms, sign_decision
from aps.call import sign_call
from aps.gate import ActionGate, Needs
from aps.keys import load_public_key
from negotiation.hotel import load_authorities
from node.server import create_app
from tests.mcp_helpers import TUTTIE, call_tool, registry_record, signed_book

ROOT = Path(__file__).resolve().parent.parent  # code/
CONFIG = json.loads((ROOT / "data" / "nodes" / "hotel-rheinblick.json").read_text())
NODE_ID = CONFIG["node_id"]


def approval(amount, approval_id="ap-1", terms=None, action="book"):
    return sign_decision({"id": approval_id, "action": action, "payee_node_id": NODE_ID, "amount_chf": amount,
                          "terms": terms}, "approved", load_signing_key("user"))


def test_an_expired_commitment_is_still_booked_as_an_extra():
    """book() checks only the extra's signature: its valid_until is never compared with now (nor
    with the booked night), so a promise that ran out years ago (or an old price the owner has
    since raised) is still redeemed."""
    stale = {"item": "late check-in with dog", "price_chf": 1, "conditions": [], "valid_until": "2020-01-01T00:00:00Z"}
    extra = sign_envelope(NODE_ID, {"answer": "ok", "commitment": stale}, load_signing_key(NODE_ID))
    room = next(r for r in CONFIG["facts"]["rooms"] if r["room_type"] == "double")
    total = room["price_chf"] + 1
    app = create_app(CONFIG, lookup=registry_record)
    result = signed_book(app, {"date": "2026-11-14", "room_type": "double", "guest_name": "A",
                               "extras": [extra], "approval": approval(total)})
    assert result["status"] == "refused", f"booked with a commitment that expired in 2020: {result.get('total_chf')}"


def test_a_pay_approval_does_not_bind_the_purpose_or_booking():
    """A signed 'pay' approval carries only action, payee and amount: the gate accepts it for any
    charge of the same amount (another purpose, another booking). Only Tuttie can sign the call,
    so this needs a confused or compromised Tuttie; the user's signature does not bind it."""
    async def run():
        gate = ActionGate(NODE_ID, "x", load_public_key("user"), load_authorities(), registry_record)
        decision = approval(4, "ap-tax", action="pay")  # the user saw "city tax for BK-1 = CHF 4"
        call = sign_call("pay", {"purpose": "minibar", "booking_id": "BK-OTHER", "approval": decision},
                         TUTTIE, load_signing_key(TUTTIE))
        return await gate.check_action(call, Needs("pay", scope=None, approval=True, mandate=True,
                                                   amount_chf=4, purpose="minibar"))
    verdict = asyncio.run(run())
    assert not verdict.ok, "a city-tax approval paid the minibar of another booking"


def test_tuttie_flags_a_confirmation_that_drops_the_approved_extras():
    """booked_other_terms compares room_type, date, rate and offer_id, but not the extras
    ('includes') the user approved: a sealed hotel that confirms without the approved breakfast
    (same total) is not flagged as a mismatch to the user."""
    from assistant.tools import booked_other_terms
    terms = booking_terms("double", "2026-11-14", "non-refundable", ["breakfast"])
    confirmation = {"status": "confirmed", "total_chf": 200, "room_type": "double", "date": "2026-11-14",
                    "rate": "non-refundable", "offer_id": None, "extras": []}
    assert booked_other_terms(confirmation, 200, terms) != []
