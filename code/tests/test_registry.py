"""The registry service (registry/app.py): search by tags and capability, records by id."""

import json

import pytest
from fastapi.testclient import TestClient

import registry.app
from registry.app import app

CLIENT = TestClient(app)


def ids(response) -> set[str]:
    return {r["node_id"] for r in response.json()}


def test_search_needs_every_tag():
    hotels_at_sbb = ids(CLIENT.get("/search", params={"tags": "hotel,basel-sbb"}))
    assert "ch.basel.hotel-rheinblick" in hotels_at_sbb
    assert not any(node_id.startswith("ch.legal.") for node_id in hotels_at_sbb)
    dog_friendly = ids(CLIENT.get("/search", params={"tags": "hotel, basel-sbb ,dog-friendly"}))  # spaces are fine
    assert dog_friendly and dog_friendly < hotels_at_sbb


def test_search_by_capability_and_without_filters():
    licensed = ids(CLIENT.get("/search", params={"capability": "licensed_legal_ch"}))
    assert licensed == {"ch.legal.consumer-law", "ch.legal.advisor"}  # claims only; trust is checked by the caller
    everything = CLIENT.get("/search").json()
    assert len(everything) == len(json.loads(registry.app.REGISTRY_PATH.read_text()))


def test_unknown_tag_finds_nothing():
    assert CLIENT.get("/search", params={"tags": "castle"}).json() == []


def test_node_by_id():
    record = CLIENT.get("/nodes/ch.tuttie.alex-muster").json()
    assert record["kind"] == "user-agent" and "delegation" in record
    response = CLIENT.get("/nodes/ch.nobody.here")
    assert response.status_code == 404 and "unknown node" in response.json()["detail"]


def test_a_reissued_registry_is_served_without_restart(tmp_path, monkeypatch):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps([{"node_id": "ch.test.one", "tags": ["a"], "capabilities": []}]))
    monkeypatch.setattr(registry.app, "REGISTRY_PATH", path)
    assert ids(CLIENT.get("/search", params={"tags": "a"})) == {"ch.test.one"}
    path.write_text(json.dumps([{"node_id": "ch.test.two", "tags": ["a"], "capabilities": []}]))
    assert ids(CLIENT.get("/search", params={"tags": "a"})) == {"ch.test.two"}


@pytest.mark.parametrize("path", ["/nodes/../registry.json", "/nodes/%2e%2e"])
def test_odd_node_ids_are_just_unknown(path):
    assert CLIENT.get(path).status_code == 404
