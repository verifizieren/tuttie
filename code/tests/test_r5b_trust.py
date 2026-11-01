"""Round 5b red team: unsealed fields that still reach the user."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from aps import evaluate_record
from aps.envelope import sign_envelope
from aps.keys import load_signing_key
from assistant.cards import hotel_card
from assistant.events import EventBus
from assistant.marketplace import MarketDesk

ROOT = Path("data")
REGISTRY = {r["node_id"]: r for r in json.loads((ROOT / "registry.json").read_text())}
AUTH = {a["issuer"]: a for a in json.loads((ROOT / "authorities.json").read_text())}
SPALENHOF, RHEINBLICK = "ch.basel.hotel-spalenhof", "ch.basel.hotel-rheinblick"


def registry_client():
    def handler(request):
        node_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=REGISTRY[node_id]) if node_id in REGISTRY else httpx.Response(404)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_r5b_market_relayed_name_reaches_card():
    """The market relays offers unsigned around the envelope; Tuttie re-checks seals and
    signature but keeps the market's `name`. A genuine Spalenhof (blue) offer relayed with
    name "Hotel Rheinblick" becomes a card titled Hotel Rheinblick."""
    valid = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    offer = {"type": "offer", "request_id": "rq-x1", "offer_id": "of-1", "item": "Double room",
             "price_chf": 120.0, "includes": [], "conditions": [], "valid_until": valid,
             "room_type": None, "date": None, "rate": None}
    envelope = sign_envelope(SPALENHOF, offer, load_signing_key(SPALENHOF))
    item = {"node_id": SPALENHOF, "name": "Hotel Rheinblick", "trust_tier": "gold",
            "uid": "CHE-526.018.151", "offer": offer, "envelope": envelope}

    async def run():
        async with registry_client() as http:
            desk = MarketDesk(http, "http://registry", EventBus(), AUTH)
            return await desk.check(item, {}, "rq-x1")
    checked = asyncio.run(run())
    assert checked is not None  # accepted: seals and signature are fine
    card = hotel_card(checked, {}, [], None, shortlisted=True)
    sealed_name = REGISTRY[SPALENHOF]["name"]
    assert card["name"] == sealed_name, f"card shows {card['name']!r}, sealed name is {sealed_name!r}"
    assert checked["uid"] == REGISTRY[SPALENHOF]["uid"] or checked["uid"] is None
    assert MarketDesk.view(checked)["name"] == sealed_name


def test_r5b_hotel_photos_may_point_anywhere():
    """A hotel's signed get_policies may list any photo URL; the wallet loads it as <img src>,
    so a verified hotel learns the user's IP/when the card is shown (tracking pixel), or shows
    another hotel's photos."""
    item = {"node_id": SPALENHOF, "name": "Hotel Spalenhof", "trust_tier": "blue",
            "offer": {"offer_id": "of-1", "item": "x", "price_chf": 100, "includes": []}}
    own = f"hotels/{SPALENHOF}/1.jpg"
    facts = {"photos": ["https://tracker.example/p.gif?user=alex", "/hotels/rheinblick-1.jpg",
                        f"hotels/{RHEINBLICK}/1.jpg", f"hotels/{SPALENHOF}/../{RHEINBLICK}/1.jpg",
                        f"hotels/{SPALENHOF}/1.jpg?u=alex", f"//tracker.example/hotels/{SPALENHOF}/1.jpg", own]}
    card = hotel_card(item, facts, [], None, shortlisted=True)
    assert card["photos"] == [own], card["photos"]


def test_r5b_real_photos_pass():
    """Every demo hotel's own photos (data/nodes/*.json) still reach its card."""
    for path in ROOT.glob("nodes/*.json"):
        config = json.loads(path.read_text())
        photos = config.get("facts", {}).get("photos") or []
        if photos:
            item = {"node_id": config["node_id"], "name": config["name"], "trust_tier": "gold",
                    "offer": {"offer_id": "o", "item": "x", "price_chf": 1, "includes": []}}
            assert hotel_card(item, {"photos": photos}, [], None, True)["photos"] == photos, path


def test_r5b_registry_tiers_hold():
    """Expected demo tiers after the re-sign (passes: no node broke by mistake)."""
    tier = {n: evaluate_record(r, AUTH)["tier"] for n, r in REGISTRY.items()}
    assert tier[RHEINBLICK] == "gold" and tier[SPALENHOF] == "blue"
    assert tier["ch.basel.cheap-hotels"] == "broken" and tier["ch.basel.budget-rooms"] == "grey"
    assert tier["ch.legal.advisor"] == "grey"
    assert "licensed_legal_ch" not in evaluate_record(REGISTRY["ch.legal.advisor"], AUTH)["capabilities"]
    for n in ("ch.basel.gaestehaus-am-rhein", "ch.basel.alpina-grand", "ch.basel.hotel-gundeli"):
        assert tier[n] == "gold"
    assert tier["ch.tuttie.alex-muster"] == "blue"


def test_r5b_name_variants_break_seal():
    """Homoglyph, trailing space, trailing slash, localhost/127.0.0.1 all break the seal (passes)."""
    r = REGISTRY[RHEINBLICK]
    for field, value in (("name", r["name"].replace("l", "I")), ("name", r["name"] + " "),
                         ("endpoint", r["endpoint"] + "/"),
                         ("endpoint", r["endpoint"].replace("localhost", "127.0.0.1"))):
        assert evaluate_record({**r, field: value}, AUTH)["tier"] == "broken", (field, value)
