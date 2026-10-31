"""Edge cases of the marketplace (marketplace/market.py) that the main tests do not reach:
unknown or broken requesters, agent cards that do not verify, and odd wake-up replies."""

import asyncio
import copy

import httpx
from nacl.signing import SigningKey

from aps import sign_envelope
from test_marketplace import (NOW, REGISTRY, RHEINBLICK, TUTTIE, World, load_signing_key, refused, request,
                              tuttie_envelope)

GUNDELI, SPALENHOF, ALPINA = "ch.basel.hotel-gundeli", "ch.basel.hotel-spalenhof", "ch.basel.alpina-grand"


class OddWorld(World):
    """A World where chosen hotels misbehave on /agent/card or /agent/invoke."""

    def __init__(self, cards=None, invokes=None, **kwargs):
        super().__init__(**kwargs)
        self.cards = cards or {}      # node_id -> "forged" | "garbage" | "error"
        self.invokes = invokes or {}  # node_id -> "signed" | "garbage" | "list" | "error"

    def node(self, request: httpx.Request) -> str:
        return next(r["node_id"] for r in self.registry if r["endpoint"].endswith(f":{request.url.port}"))

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in ("/agent/card", "/agent/invoke"):
            node_id = self.node(request)
            odd = (self.cards if path == "/agent/card" else self.invokes).get(node_id)
            if odd == "error":
                raise httpx.ConnectError("down", request=request)
            if odd == "garbage":
                return httpx.Response(200, content=b"not json")
            if odd == "forged":
                card = {"node_id": node_id, "wakes_on": ["posting.created"]}
                return httpx.Response(200, json=sign_envelope(node_id, card, SigningKey.generate()))
            if odd == "list":
                return httpx.Response(200, json=["interested"])
            if odd == "signed":
                reply = {"interested": True, "tool": "make_offer"}
                return httpx.Response(200, json=sign_envelope(node_id, reply, load_signing_key(node_id)))
        return super().handle(request)


def post(world: World) -> dict:
    return asyncio.run(world.market().post_request(tuttie_envelope(), now=NOW))


def test_unknown_or_broken_requester_is_refused():
    without_tuttie = [r for r in REGISTRY if r["node_id"] != TUTTIE]
    error = refused(World(registry=without_tuttie).market().post_request(tuttie_envelope(), now=NOW))
    assert error.status == 403 and "not in the registry" in error.reason
    broken = copy.deepcopy(REGISTRY)
    next(r for r in broken if r["node_id"] == TUTTIE)["seals"][0]["signature"] = "AAAA"
    error = refused(World(registry=broken).market().post_request(tuttie_envelope(), now=NOW))
    assert error.status == 403 and "seals do not verify" in error.reason


def test_cards_that_do_not_verify_mean_no_wake_up():
    view = post(OddWorld(cards={RHEINBLICK: "forged", GUNDELI: "garbage", ALPINA: "error"}))
    for node_id in (RHEINBLICK, GUNDELI, ALPINA):
        assert view["skipped"][node_id]["reason"] == "no verifiable agent card", node_id
        assert node_id not in view["invited"]


def test_odd_wake_up_replies_are_recorded_not_trusted():
    view = post(OddWorld(invokes={RHEINBLICK: "signed", GUNDELI: "garbage", SPALENHOF: "list", ALPINA: "error"}))
    invited = view["invited"]
    assert (invited[RHEINBLICK]["status"], invited[RHEINBLICK]["next_tool"]) == ("interested", "make_offer")
    assert invited[GUNDELI]["status"] == "invited" and invited[GUNDELI]["detail"] == "no JSON reply"
    assert invited[SPALENHOF]["status"] == "invited"
    assert invited[ALPINA]["status"] == "unreachable" and invited[ALPINA]["detail"] == "ConnectError"


def test_requests_for_other_kinds_of_nodes_wake_no_business():
    view = asyncio.run(World().market().post_request(
        tuttie_envelope(request(category="tuttie", tags=[])), now=NOW))
    assert view["invited"] == {}  # Tuttie itself matches the tag but is not a business
