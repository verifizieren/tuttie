"""Tests for the node's pay tool over MCP: charges from the config, mandate or approval, once per booking."""

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from mcp import Client

from aps import load_signing_key
from aps.approval import sign_decision
from aps.call import sign_call
from aps.mandate import sign_mandate
from assistant.mcp_client import McpLink
from node.server import create_app
from tests.mcp_helpers import TUTTIE, call_tool, registry_record, signed_book

CONFIG = json.loads((Path(__file__).resolve().parent.parent / "data" / "nodes" / "guesthouse-am-rhein.json").read_text())
NODE_ID = CONFIG["node_id"]


def booked() -> tuple[FastAPI, str]:
    """A node with one confirmed booking (single room, CHF 95) and its booking id."""
    app = create_app(CONFIG, lookup=registry_record)
    decision = sign_decision({"id": "ap-room", "action": "book", "payee_node_id": NODE_ID, "amount_chf": 95},
                             "approved", load_signing_key("user"))
    confirmation = signed_book(app, {"date": "2026-11-14", "room_type": "single", "guest_name": "Alex Muster",
                                     "approval": decision})
    return app, confirmation["booking_id"]


def pay(app: FastAPI, args: dict) -> dict:
    call = sign_call("pay", args, TUTTIE, load_signing_key(TUTTIE))
    return call_tool(app, "pay", {"call": call})["payload"]


def mandate(max_chf: float = 20, purpose: str = "city tax") -> dict:
    return sign_mandate(TUTTIE, NODE_ID, max_chf, purpose, "2099-01-01T00:00:00Z", load_signing_key("user"))


def test_the_policies_list_the_charges():
    policies = call_tool(create_app(CONFIG, lookup=registry_record), "get_policies")["payload"]
    assert policies["charges"][0]["purpose"] == "city tax" and policies["charges"][0]["price_chf"] == 4


def test_city_tax_is_paid_once_with_the_users_mandate():
    app, booking_id = booked()
    receipt = pay(app, {"purpose": "city tax", "booking_id": booking_id, "mandate": mandate()})
    assert receipt["status"] == "paid" and receipt["amount_chf"] == 4 and receipt["paid_with"] == "mandate"
    assert receipt["checked"] == ["caller", "signature", "delegation", "mandate"]
    again = pay(app, {"purpose": "city tax", "booking_id": booking_id, "mandate": mandate()})
    assert "already paid" in again["reason"]


def test_a_charge_can_be_paid_with_an_approval_for_exactly_its_amount():
    app, booking_id = booked()
    def approval(amount):
        return sign_decision({"id": f"ap-{amount}", "action": "pay", "payee_node_id": NODE_ID, "amount_chf": amount,
                              "charge": {"purpose": "city tax", "booking_id": booking_id}},
                             "approved", load_signing_key("user"))
    assert "does not match" in pay(app, {"purpose": "city tax", "booking_id": booking_id, "approval": approval(1)})["reason"]
    receipt = pay(app, {"purpose": "city tax", "booking_id": booking_id, "approval": approval(4)})
    assert receipt["status"] == "paid" and receipt["paid_with"] == "approval"


def test_pay_refuses_unknown_charges_bookings_and_other_purposes():
    app, booking_id = booked()
    assert "no charge" in pay(app, {"purpose": "minibar", "booking_id": booking_id, "mandate": mandate()})["reason"]
    assert "no such booking" in pay(app, {"purpose": "city tax", "booking_id": "BK-NOPE", "mandate": mandate()})["reason"]
    wrong = mandate(purpose="parking")
    assert pay(app, {"purpose": "city tax", "booking_id": booking_id, "mandate": wrong})["status"] == "refused"


def test_two_simultaneous_payments_with_one_mandate_charge_only_once():
    """The gate awaits the registry, so two calls can be inside it at once: only one may pay."""
    async def slow_lookup(node_id: str) -> dict | None:
        await asyncio.sleep(0.01)  # like the registry over HTTP: lets the other call run meanwhile
        return await registry_record(node_id)

    app = create_app(CONFIG, lookup=slow_lookup)
    decision = sign_decision({"id": "ap-race", "action": "book", "payee_node_id": NODE_ID, "amount_chf": 95},
                             "approved", load_signing_key("user"))
    booking_id = signed_book(app, {"date": "2026-11-14", "room_type": "single", "guest_name": "Alex Muster",
                                   "approval": decision})["booking_id"]
    link = McpLink(lambda _: Client(app.state.mcp))
    args = {"purpose": "city tax", "booking_id": booking_id, "mandate": mandate()}

    async def both():
        calls = [sign_call("pay", args, TUTTIE, load_signing_key(TUTTIE)) for _ in range(2)]
        return await asyncio.gather(*(link.call("in-process", "pay", {"call": c}) for c in calls))

    statuses = sorted(r["payload"]["status"] for r in asyncio.run(both()))
    assert statuses == ["paid", "refused"]


def test_a_pay_approval_pays_only_the_charge_and_booking_it_names():
    app, booking_id = booked()
    def approval(charge):
        return sign_decision({"id": "ap-x", "action": "pay", "payee_node_id": NODE_ID, "amount_chf": 4, "charge": charge},
                             "approved", load_signing_key("user"))
    other = pay(app, {"purpose": "city tax", "booking_id": booking_id,
                      "approval": approval({"purpose": "city tax", "booking_id": "BK-OTHER"})})
    assert other["reason"] == "the approval is not for the city tax of this booking"
    unbound = pay(app, {"purpose": "city tax", "booking_id": booking_id, "approval": approval(None)})
    assert unbound["status"] == "refused"
