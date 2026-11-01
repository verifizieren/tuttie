"""atk10: one verified hotel whose signed session reply lacks a field ("agent") makes
negotiate_all raise (asyncio.gather without isolation), so EVERY hotel's negotiation is lost,
including a good hotel's agreement. Expected: the bad hotel ends as refused, the others go on."""

import asyncio

from aps import load_signing_key
from assistant.subagents import Subagent
from assistant.tools import Verified
from negotiation.tuttie import TuttieNegotiator
from negotiation_helpers import REGISTRY, RHEINBLICK, TUTTIE, signed_offer
from sessions import Context, SessionStore

SPALENHOF = "ch.basel.hotel-spalenhof"


class Toolbox:
    """Trust gate stand-in: Spalenhof's signed session reply has no "agent" key; Rheinblick agrees."""

    async def verified_post(self, node_id, path, body, kind, label, headers=None):
        record = REGISTRY[node_id]
        if path == "/agent/sessions":
            payload = {"session_id": f"se-{node_id[-4:]}"}
            if node_id == RHEINBLICK:
                payload["agent"] = "Rheinblick agent"
            return Verified(record, {"tier": "gold", "seals": []}, {"payload": payload, "timestamp": "x"})
        if path.endswith("/close"):
            return Verified(record, {"tier": "gold", "seals": []}, {"payload": {}, "timestamp": "x"})
        offer = body["offer"]["payload"]
        reply = {"tool": "counter_offer", "type": "agreement", **{k: offer[k] for k in (
            "request_id", "offer_id", "item", "room_type", "date", "rate", "includes", "conditions")},
            "price_chf": body["counter"]["payload"]["price_chf"]}
        return Verified(record, {"tier": "gold", "seals": []}, {"payload": reply, "timestamp": "x"})

    def emit_verified(self, kind, summary, result):
        return 0


class Pool:
    def __init__(self):
        self.toolbox = Toolbox()
        self.memories = SessionStore("tuttie")

    def spawn(self, node_id, task, context):
        return Subagent(self.toolbox, self.memories.open(node_id, task, context.share("negotiation")), node_id)

    async def close(self, subagent):
        await subagent.close()


def test_one_malformed_hotel_does_not_sink_the_others():
    negotiator = TuttieNegotiator(Pool(), TUTTIE, load_signing_key(TUTTIE))
    offers = [{"node_id": SPALENHOF, "envelope": signed_offer(SPALENHOF)},
              {"node_id": RHEINBLICK, "envelope": signed_offer(RHEINBLICK)}]
    context = Context().add("max_price_chf", 500, "private")
    outcomes = asyncio.run(negotiator.negotiate_all(offers, context))  # raised KeyError: 'agent'
    alone = asyncio.run(TuttieNegotiator(Pool(), TUTTIE, load_signing_key(TUTTIE)).negotiate_all(offers[1:], context))
    # The good hotel ends exactly as when it bargains alone (the stub's agreement is unsigned,
    # so "refused: not a valid agreement" there); one bad hotel never changes it.
    assert (outcomes[1].status, outcomes[1].reason) == (alone[0].status, alone[0].reason)
