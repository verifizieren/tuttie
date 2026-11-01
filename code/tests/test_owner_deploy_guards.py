"""Tests for owner deploys that would take the hotel out of the pitch (red team round 11).

An empty or partial deploy must not wipe the rooms or silently end the bargaining, owner
settings must not bloat every hotel prompt, and a stored version a stricter check rejects must
not stop the node (and with it the whole service).
"""

import json

from fastapi.testclient import TestClient

from node.agent import public_facts
from node.deployments import DeploymentStore
from node.settings import MAX_PUBLIC_FACTS, validate
from tests.test_node_owner import NODES as CONFIG_DIR
from tests.test_node_owner import AUTH, CONFIG, current, deploy, edited, folder, owner_token, start  # noqa: F401


def test_an_empty_settings_deploy_is_refused(folder):
    """POST {"settings": {}} would remove every room: the hotel would offer nothing."""
    _, client = start(folder)
    reply = deploy(client, {})
    assert reply.status_code == 422
    assert any(error["path"] == "facts.rooms" for error in reply.json()["detail"]["errors"])
    assert current(client)["facts"]["rooms"] == CONFIG["facts"]["rooms"]


def test_a_deploy_with_every_room_unavailable_is_refused(folder):
    _, client = start(folder)
    settings = edited(client, lambda s: [room.update(available=False) for room in s["facts"]["rooms"]])
    assert deploy(client, settings).status_code == 422


def test_a_node_without_rooms_can_still_deploy(folder):
    """An agent node (the legal advisor) has no rooms; the room rule is for businesses."""
    config = json.loads((CONFIG_DIR / "legal-consumer-ch.json").read_text())
    _, client = start(folder, config)
    settings = edited(client, lambda s: s.update(respond_to_postings=not s["respond_to_postings"]))
    assert deploy(client, settings).status_code == 200


def test_leaving_out_negotiation_keeps_the_live_floor(folder):
    """A partial draft without facts.negotiation must not silently end the bargaining."""
    _, client = start(folder)
    settings = edited(client, lambda s: (s["facts"].pop("negotiation"), s["facts"]["rooms"][0].update(price_chf=140)))
    assert deploy(client, settings).status_code == 200
    assert current(client)["facts"]["negotiation"] == CONFIG["facts"]["negotiation"]
    assert current(client)["settings"]["facts"]["negotiation"] == CONFIG["facts"]["negotiation"]


def test_an_explicit_null_ends_the_bargaining(folder):
    _, client = start(folder)
    settings = edited(client, lambda s: s["facts"].update(negotiation=None))
    assert deploy(client, settings).status_code == 200
    assert "negotiation" not in current(client)["facts"]


def test_largest_valid_settings_keep_the_hotel_prompt_small():
    """Max lists (50 add-ons x 10 conditions x 200 chars, ...) would go into every hotel prompt."""
    s, x = "x" * 200, "y" * 600
    settings = {"facts": {
        "profile": {"size": "small", "rooms_total": 7, "about": x},
        "address": s, "how_to_get_there": x, "quiet_note": x,
        "facilities": [s] * 30,
        "rooms": [{"room_type": f"r{i}", "price_chf": 100, "rate": s, "note": s} for i in range(30)],
        "policies": {f"p{i}": s for i in range(30)},
        "charges": [{"purpose": f"{i}{s}"[:200], "price_chf": 1, "note": s} for i in range(20)],
        "add_ons": [{"id": f"a{i}", "item": s, "price_chf": 0, "conditions": [s] * 10} for i in range(50)],
        "negotiation": {"floor_chf": 90, "max_rounds": 10}},
        "persona": {"name": s, "role": s, "tone": s, "priorities": [s] * 10}}
    clean, errors = validate(settings)
    assert clean is None and any(error["path"] == "facts" for error in errors)


def test_every_committed_config_fits_the_prompt_cap():
    for path in CONFIG_DIR.glob("*.json"):
        facts = json.loads(path.read_text()).get("facts", {})
        assert len(json.dumps(public_facts(facts), indent=2, ensure_ascii=False)) < MAX_PUBLIC_FACTS // 2, path.name


def test_an_invalid_stored_version_is_skipped_not_fatal(folder):
    """A version a newer, stricter check rejects falls back to the newest valid one."""
    _, client = start(folder)
    deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=150)))
    deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=160)), base_version=1)
    path = folder / f"{CONFIG['node_id']}.json"
    data = json.loads(path.read_text())
    data["versions"][1]["settings"]["facts"]["rooms"][0]["price_chf"] = -1  # a check added after the deploy
    path.write_text(json.dumps(data))
    store = DeploymentStore(CONFIG["node_id"], CONFIG, folder)
    assert store.current["version"] == 1
    _, client = start(folder)
    assert current(client)["facts"]["rooms"][0]["price_chf"] == 150
    # The next deploy gets a fresh number and keeps the skipped version on disk.
    assert deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=170)), base_version=1).status_code == 200
    stored = json.loads(path.read_text())["versions"]
    assert [record["version"] for record in stored] == [1, 2, 3]
    assert current(client)["version"] == 3


def test_a_store_with_only_invalid_versions_uses_the_config(folder):
    _, client = start(folder)
    deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=150)))
    path = folder / f"{CONFIG['node_id']}.json"
    data = json.loads(path.read_text())
    data["versions"][0]["settings"]["facts"]["rooms"][0]["price_chf"] = -1
    path.write_text(json.dumps(data))
    _, client = start(folder)
    assert current(client)["facts"]["rooms"][0]["price_chf"] == CONFIG["facts"]["rooms"][0]["price_chf"]



