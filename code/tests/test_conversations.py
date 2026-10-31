"""Tests that every browser gets its own conversation (assistant/app.py, assistant/conversations.py)."""

import httpx
from fastapi.testclient import TestClient

from assistant import conversations as conv_module
from assistant.app import SESSION_COOKIE, app
from assistant.conversations import Conversations


def test_each_browser_gets_its_own_session_and_approvals():
    with TestClient(app) as alice, TestClient(app) as bob:
        alice.post("/reset")
        bob.post("/reset")
        alice_id, bob_id = alice.cookies[SESSION_COOKIE], bob.cookies[SESSION_COOKIE]
        assert alice_id != bob_id
        store = app.state.conversations
        store.get(alice_id).approvals.pending["ap-1"] = {"id": "ap-1", "amount_chf": 128}
        assert [a["id"] for a in alice.get("/approvals/pending").json()] == ["ap-1"]
        assert bob.get("/approvals/pending").json() == []
        assert bob.post("/approvals/ap-1", json={"decision": "approved"}).status_code == 404


def test_a_known_cookie_keeps_its_conversation():
    with TestClient(app) as client:
        client.post("/reset")
        first = client.cookies[SESSION_COOKIE]
        response = client.post("/reset")
        assert SESSION_COOKIE not in response.cookies  # not reissued
        assert client.cookies[SESSION_COOKIE] == first


def test_least_recently_used_conversation_is_dropped(monkeypatch):
    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 2)
    store = Conversations(httpx.AsyncClient(), "http://registry", llm=object())
    a = store.get("a")
    store.get("b")
    assert store.get("a") is a  # a is now the most recently used
    store.get("c")
    assert list(store.by_session) == ["a", "c"]
