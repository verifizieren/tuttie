"""Tests for the owner endpoints of a node: token protected, validated, versioned, live.

The owner reads the business, deploys new settings and the node's tools, agent and bargaining
limits use them from the next request on. Deployments go to a temporary folder.
"""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from negotiation.hotel import CounterOfferTool
from node.deployments import DeploymentStore
from node.server import create_app
from node.settings import apply, canonical, snapshot, validate
from tests.mcp_helpers import call_tool

NODES = Path(__file__).resolve().parent.parent / "data" / "nodes"
CONFIG = json.loads((NODES / "guesthouse-am-rhein.json").read_text())
AUTH = {"Authorization": "Bearer owner-secret"}


@pytest.fixture(autouse=True)
def owner_token(monkeypatch):
    monkeypatch.setenv("OWNER_TOKEN", "owner-secret")


@pytest.fixture
def folder(tmp_path):
    return tmp_path / "deployments"


def start(folder, config=CONFIG):
    """A node app and a client for it (the app works on its own copy of the config)."""
    app = create_app(config, deployments_dir=folder)
    return app, TestClient(app)


def current(client) -> dict:
    return client.get("/owner/overview", headers=AUTH).json()


def deploy(client, settings, base_version=0, note=None, token="owner-secret"):
    return client.post("/owner/deploy", headers={"Authorization": f"Bearer {token}"},
                       json={"base_version": base_version, "settings": settings, "note": note})


def edited(client, change) -> dict:
    """The live settings, changed by `change(settings)`."""
    settings = copy.deepcopy(current(client)["settings"])
    change(settings)
    return settings


# --- reading ----------------------------------------------------------------------------


def test_the_owner_sees_the_whole_business_including_private_limits(folder):
    _, client = start(folder)
    body = current(client)
    assert body["name"] == "Gästehaus am Rhein"
    assert body["facts"]["negotiation"] == {"floor_chf": 125, "max_rounds": 3}
    assert body["private"] == ["negotiation"]
    assert body["persona"]["name"] == "Anna"
    assert "counter_offer" in body["tools"]
    assert body["version"] == 0 and body["deployed_at"] is None
    assert body["settings"]["facts"]["rooms"][0]["price_chf"] == 135


def test_no_token_or_a_wrong_one_is_refused(folder):
    _, client = start(folder)
    for path in ("/owner/overview", "/owner/versions"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer guess"}).status_code == 401
    assert deploy(client, {}, token="guess").status_code == 401


def test_without_a_configured_token_nobody_gets_in(folder, monkeypatch):
    monkeypatch.delenv("OWNER_TOKEN", raising=False)
    _, client = start(folder)
    assert client.get("/owner/overview", headers={"Authorization": "Bearer anything"}).status_code == 503
    assert deploy(client, {}, token="").status_code == 503


def test_the_browser_may_read_and_deploy_from_another_port_but_only_on_owner_routes(folder):
    _, client = start(folder)
    ask = {"Origin": "http://localhost:4040", "Access-Control-Request-Headers": "authorization,content-type"}
    reply = client.options("/owner/deploy", headers={**ask, "Access-Control-Request-Method": "POST"})
    assert reply.headers["access-control-allow-origin"] == "*"
    other = client.options("/agent", headers={**ask, "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in other.headers


# --- checking settings -----------------------------------------------------------------


def test_every_committed_business_has_valid_settings():
    for path in NODES.glob("*.json"):
        config = json.loads(path.read_text())
        assert canonical(snapshot(config)), path.name  # raises if the committed config is not acceptable


@pytest.mark.parametrize("change, path", [
    (lambda s: s["facts"]["rooms"][0].update(price_chf=-5), "facts.rooms.0.price_chf"),
    (lambda s: s["facts"]["rooms"][0].update(price_chf=99.5), "facts.rooms.0.price_chf"),
    (lambda s: s["facts"]["rooms"][0].update(price_chf="cheap"), "facts.rooms.0.price_chf"),
    (lambda s: s["facts"]["rooms"][0].update(rate=""), "facts.rooms.0.rate"),
    (lambda s: s["facts"]["rooms"][0].update(room_type="Double!"), "facts.rooms.0.room_type"),
    (lambda s: s["facts"]["rooms"][0].update(secret="x"), "facts.rooms.0.secret"),
    (lambda s: s["facts"]["rooms"].append(dict(s["facts"]["rooms"][0])), "facts.rooms.2"),
    (lambda s: s["facts"]["add_ons"][0].update(id="Bad Id"), "facts.add_ons.0.id"),
    (lambda s: s["facts"]["negotiation"].update(floor_chf=200), "facts.negotiation.floor_chf"),
    (lambda s: s["facts"]["negotiation"].update(max_rounds=0), "facts.negotiation.max_rounds"),
    (lambda s: s["facts"]["profile"].update(size="huge"), "facts.profile.size"),
    (lambda s: s["persona"].update(name=""), "persona.name"),
    (lambda s: s.update(unknown=1), "unknown"),
])
def test_unacceptable_settings_are_refused_with_the_field_that_is_wrong(folder, change, path):
    _, client = start(folder)
    reply = deploy(client, edited(client, change))
    assert reply.status_code == 422
    assert path in [e["path"] for e in reply.json()["detail"]["errors"]]
    assert current(client)["version"] == 0  # nothing was deployed


def test_the_negotiation_floor_is_compared_with_the_standard_double_room(folder):
    _, client = start(folder)
    errors = validate(edited(client, lambda s: s["facts"]["negotiation"].update(floor_chf=136)))[1]
    assert "CHF 135" in errors[0]["message"]
    assert validate(edited(client, lambda s: s["facts"]["negotiation"].update(floor_chf=135)))[1] == []


def test_blank_optional_texts_mean_not_set_and_text_is_trimmed(folder):
    _, client = start(folder)
    settings = edited(client, lambda s: s["facts"].update(how_to_get_there="  ", address="  Rheinweg 1  "))
    clean, errors = validate(settings)
    assert errors == [] and clean.facts.how_to_get_there is None and clean.facts.address == "Rheinweg 1"


# --- deploying -------------------------------------------------------------------------


def test_a_deploy_goes_live_at_once_in_every_tool(folder):
    app, client = start(folder)

    def change(settings):
        settings["facts"]["rooms"][0]["price_chf"] = 150
        settings["facts"]["negotiation"] = {"floor_chf": 140, "max_rounds": 2}
        settings["facts"]["add_ons"].append({"id": "bike", "item": "bike rental", "price_chf": 20, "conditions": ["per day"]})
        settings["persona"]["name"] = "Anni"

    reply = deploy(client, edited(client, change), base_version=0, note="Autumn prices")
    assert reply.status_code == 200
    body = reply.json()
    assert body["version"] == 1 and body["deployed_at"] and body["facts"]["rooms"][0]["price_chf"] == 150

    rooms = call_tool(app, "get_availability", {"date": "2026-11-14"})["payload"]["rooms"]
    assert {r["room_type"]: r["price_chf"] for r in rooms}["double"] == 150
    assert client.get("/agent/card").json()["payload"]["persona"]["name"] == "Anni"
    assert current(client)["facts"]["negotiation"] == {"floor_chf": 140, "max_rounds": 2}
    assert "floor_chf" not in json.dumps(call_tool(app, "get_policies")["payload"])  # still private


def test_the_bargaining_limits_follow_a_deploy():
    config = copy.deepcopy(CONFIG)
    tool = CounterOfferTool(config)
    assert tool.limits.max_rounds == 3
    settings, _ = validate(canonical(snapshot(config)) | {"facts": canonical(snapshot(config))["facts"] | {
        "negotiation": {"floor_chf": 130, "max_rounds": 1}}})
    apply(config, settings)
    assert tool.limits.max_rounds == 1 and round(tool.limits.min_share, 3) == round(130 / 135, 3)


def test_a_deployed_version_is_still_there_after_a_restart(folder):
    _, client = start(folder)
    assert deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=150))).status_code == 200
    _, restarted = start(folder)
    assert current(restarted)["version"] == 1
    assert current(restarted)["settings"]["facts"]["rooms"][0]["price_chf"] == 150


def test_the_committed_config_is_not_changed_by_a_deploy(folder):
    _, client = start(folder)
    deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=150)))
    assert CONFIG["facts"]["rooms"][0]["price_chf"] == 135
    assert json.loads((NODES / "guesthouse-am-rhein.json").read_text())["facts"]["rooms"][0]["price_chf"] == 135


def test_the_owner_cannot_change_what_is_sealed_or_the_agent_s_boundaries(folder):
    _, client = start(folder)
    deploy(client, edited(client, lambda s: s["persona"].update(tone="very formal")))
    body = current(client)
    assert body["persona"]["tone"] == "very formal"
    assert body["persona"]["boundaries"] == CONFIG["agent"]["persona"]["boundaries"]
    assert (body["uid"], body["seals"], body["capabilities"], body["tags"]) == (
        CONFIG["uid"], CONFIG["seals"], CONFIG["capabilities"], CONFIG["tags"])
    assert body["tools"].keys() == {"get_availability", "get_policies", "book", "make_offer", "counter_offer", "pay"}


def test_switching_off_postings_stops_the_wake_ups_and_back_on_restores_them(folder):
    _, client = start(folder)
    deploy(client, edited(client, lambda s: s.update(respond_to_postings=False)))
    assert client.get("/agent/card").json()["payload"]["wakes_on"] == []
    deploy(client, edited(client, lambda s: s.update(respond_to_postings=True)), base_version=1)
    assert client.get("/agent/card").json()["payload"]["wakes_on"] == ["posting.created", "posting.updated"]


def test_removing_the_negotiation_limits_means_the_hotel_does_not_negotiate(folder):
    _, client = start(folder)
    deploy(client, edited(client, lambda s: s["facts"].update(negotiation=None)))  # explicit null, as the owner view sends
    assert "negotiation" not in current(client)["facts"]


def test_a_deploy_from_a_stale_page_is_refused(folder):
    _, client = start(folder)
    deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=150)))
    stale = deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=160)), base_version=0)
    assert stale.status_code == 409 and "version 1 is live" in stale.json()["detail"]
    assert current(client)["facts"]["rooms"][0]["price_chf"] == 150


def test_deploying_without_a_change_is_refused(folder):
    _, client = start(folder)
    reply = deploy(client, current(client)["settings"])
    assert reply.status_code == 422 and "nothing changed" in reply.json()["detail"]["errors"][0]["message"]


def test_the_history_lists_every_version_newest_first_with_the_original_last(folder):
    _, client = start(folder)
    deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=150)), note="Autumn prices")
    deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=140)), base_version=1)
    history = client.get("/owner/versions", headers=AUTH).json()
    assert [v["version"] for v in history] == [2, 1, 0]
    assert history[1]["note"] == "Autumn prices" and history[2]["note"] == "Original configuration"
    assert history[2]["settings"]["facts"]["rooms"][0]["price_chf"] == 135


def test_rolling_back_is_deploying_an_old_version_again(folder):
    _, client = start(folder)
    original = current(client)["settings"]
    deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=150)))
    assert deploy(client, original, base_version=1, note="Back to the old prices").status_code == 200
    assert current(client)["version"] == 2 and current(client)["facts"]["rooms"][0]["price_chf"] == 135


def test_an_unreadable_deployment_file_stops_the_node_instead_of_changing_prices(folder):
    """Invalid single versions are skipped (tests/test_owner_deploy_guards.py); a file that is
    not JSON at all stops the node and is not overwritten."""
    _, client = start(folder)
    deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=150)))
    path = folder / f"{CONFIG['node_id']}.json"
    path.write_text("{not json")
    with pytest.raises(ValueError):
        DeploymentStore(CONFIG["node_id"], CONFIG, folder)


def test_apps_do_not_share_state_through_the_committed_config(folder):
    first, client = start(folder)
    deploy(client, edited(client, lambda s: s["facts"]["rooms"][0].update(price_chf=150)))
    other_folder = folder.parent / "other"
    second, other = start(other_folder)
    assert current(other)["facts"]["rooms"][0]["price_chf"] == 135
