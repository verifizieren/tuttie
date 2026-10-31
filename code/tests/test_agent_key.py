"""The deployment's agent key (aps/agent_key.py): only its own services make a business's agent think."""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import node.agent
import test_market_agents
from aps import agent_key
from node.server import create_app

CONFIG = json.loads((Path(__file__).resolve().parent.parent / "data" / "nodes" / "hotel-rheinblick.json").read_text())
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import run_all  # noqa: E402

AGENT_DOORS = [("post", "/agent", {"question": "Dogs?"}),
               ("post", "/agent/invoke", {"type": "posting.created"}),
               ("post", "/agent/sessions", {"peer": "x"}),
               ("post", "/agent/sessions/s-1/messages", {"message": "hi"}),
               ("get", "/agent/sessions/s-1", None),
               ("post", "/agent/sessions/s-1/close", None)]


class NoLLM:
    def __init__(self, *args, **kwargs):
        raise AssertionError("the LLM must not run for an unknown caller")


@pytest.mark.parametrize("method, path, body", AGENT_DOORS)
def test_with_a_key_set_the_agent_refuses_callers_without_it(monkeypatch, method, path, body):
    monkeypatch.setenv(agent_key.ENV, "deployment-key")
    monkeypatch.setattr(node.agent, "LLM", NoLLM)
    client = TestClient(create_app(CONFIG))
    for headers in ({}, {agent_key.HEADER: "wrong"}):
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 401
    assert client.get("/agent/card").status_code == 200  # the public card stays readable


def test_with_the_key_a_caller_gets_through(monkeypatch):
    monkeypatch.setenv(agent_key.ENV, "deployment-key")
    client = TestClient(create_app(CONFIG))
    response = client.post("/agent/sessions", json={"peer": "tuttie-sub-1"}, headers=agent_key.headers())
    assert response.status_code == 200


def test_market_wakes_and_offers_flow_with_the_key(monkeypatch):
    """The marketplace sends the key on every wake-up, so hotels still offer."""
    monkeypatch.setenv(agent_key.ENV, "deployment-key")
    monkeypatch.setattr(node.agent, "LLM", test_market_agents.StubLLM)
    test_market_agents.test_woken_agents_send_signed_offers_back_to_the_market()


def test_without_a_key_the_doors_stay_open(monkeypatch):
    monkeypatch.delenv(agent_key.ENV, raising=False)
    assert agent_key.allowed(None) and agent_key.headers() == {}


def test_run_all_shares_one_key_per_run_or_the_configured_one():
    first, second = run_all.service_env({}, {}), run_all.service_env({}, {})
    assert len(first[agent_key.ENV]) >= 32 and first[agent_key.ENV] != second[agent_key.ENV]
    assert run_all.service_env({agent_key.ENV: "set-in-env"}, {})[agent_key.ENV] == "set-in-env"
