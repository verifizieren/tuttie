"""Tests that every browser gets its own conversation (assistant/app.py, assistant/conversations.py)."""

import os

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test")  # the app builds an LLM client; these tests never call it

from assistant import conversations as conv_module  # noqa: E402
from assistant.app import SESSION_COOKIE, app  # noqa: E402
from assistant.conversations import Conversations  # noqa: E402


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


def test_history_is_this_browsers_timeline_only():
    with TestClient(app) as alice, TestClient(app) as bob:
        alice.post("/reset")
        bob.post("/reset")
        app.state.conversations.get(alice.cookies[SESSION_COOKIE]).bus.emit("answer", "verified", "Hi Alice")
        assert [e["summary"] for e in alice.get("/history").json()] == ["Hi Alice"]
        assert bob.get("/history").json() == []


def test_new_chat_then_resume_keeps_signed_booking_context():
    with TestClient(app) as client:
        original_id = client.get('/history').headers['X-Conversation-ID']
        store = app.state.conversations
        original = store.get(client.cookies[SESSION_COOKIE])
        agreement = {'payload': {'type': 'agreement', 'price_chf': 128}, 'signature': 'hotel-signature'}
        original.assistant.toolbox.agreements['hotel'] = agreement
        original.assistant.messages.append({'role': 'user', 'content': 'Find a quiet hotel'})
        original.bus.emit('answer', 'verified', 'Book this hotel for CHF 128?')
        fresh = client.post('/conversations').json()
        assert fresh['id'] != original_id and fresh['events'] == []
        assert store.get(client.cookies[SESSION_COOKIE]).assistant.toolbox.agreements == {}
        resumed = client.post(f'/conversations/{original_id}/resume').json()
        assert resumed['id'] == original_id
        assert resumed['events'][0]['summary'] == 'Book this hotel for CHF 128?'
        assert store.get(client.cookies[SESSION_COOKIE]) is original
        assert original.assistant.toolbox.agreements['hotel'] is agreement
        assert original.assistant.messages[-1]['content'] == 'Find a quiet hotel'
        assert client.post(f"/conversations/{fresh['id']}/resume").status_code == 410  # it was empty: not kept


def test_resume_cannot_access_another_browsers_conversation():
    with TestClient(app) as alice, TestClient(app) as bob:
        old_id = alice.get('/history').headers['X-Conversation-ID']
        alice.post('/conversations')
        bob_id = bob.get('/history').headers['X-Conversation-ID']
        assert bob.post(f'/conversations/{old_id}/resume').status_code == 410
        assert bob.get('/history').headers['X-Conversation-ID'] == bob_id


def test_expired_history_does_not_replace_the_active_chat():
    with TestClient(app) as client:
        current = client.get('/history').headers['X-Conversation-ID']
        assert client.post('/conversations/legacy-local-id/resume').status_code == 410
        assert client.get('/history').headers['X-Conversation-ID'] == current


def test_switch_refuses_while_an_approval_or_chat_is_pending():
    with TestClient(app) as client:
        current = client.get('/history').headers['X-Conversation-ID']
        conv = app.state.conversations.get(client.cookies[SESSION_COOKIE])
        conv.approvals.pending['approval'] = {'id': 'approval'}
        assert client.post('/conversations').status_code == 409
        conv.approvals.pending.clear()
        conv.chats.add('running-task')
        assert client.post('/conversations').status_code == 409
        conv.chats.clear()
        assert client.get('/history').headers['X-Conversation-ID'] == current


def test_saved_conversations_have_a_bounded_lifetime(monkeypatch):
    monkeypatch.setattr(conv_module, 'MAX_CONVERSATIONS', 2)
    store = Conversations(httpx.AsyncClient(), 'http://registry', llm=object())
    oldest = store.get('alice')
    for _ in range(3):
        store.get('alice').bus.emit('answer', 'verified', 'x')  # empty chats are not kept
        store.switch('alice')
    assert len(store.saved) == 2
    import pytest
    with pytest.raises(KeyError):
        store.switch('alice', oldest.id)


def test_a_late_booking_message_cannot_run_in_a_different_chat():
    with TestClient(app) as client:
        old_id = client.get('/history').headers['X-Conversation-ID']
        client.post('/conversations')
        response = client.post('/chat', json={'message': 'Book it', 'first_tool': 'book',
                                              'conversation_id': old_id})
        assert response.status_code == 409
        assert client.get(f'/events?conversation_id={old_id}').status_code == 409
        assert client.get('/history').json() == []


def test_reading_without_a_cookie_creates_no_conversation(monkeypatch):
    """Crawlers and QR scanners (no cookie, many requests) must not create or push out chats."""
    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 3)
    monkeypatch.setattr(conv_module.Conversation, "start", lambda self, *a, **k: "t1")  # no LLM call
    with TestClient(app) as presenter:
        assert presenter.post("/chat", json={"message": "hi"}).status_code == 202  # acting creates it
        store = app.state.conversations
        before = set(store.by_session)
        mine = store.find(presenter.cookies[SESSION_COOKIE])
        for _ in range(20):
            with TestClient(app) as bot:
                for path in ("/history", "/approvals/pending", "/events?conversation_id=nope"):
                    bot.get(path)
                bot.post("/reset")
                bot.post("/approvals/ap-1", json={"decision": "approved"})
        assert set(store.by_session) == before
        assert store.find(presenter.cookies[SESSION_COOKIE]) is mine


def test_history_names_the_first_conversation_before_it_exists(monkeypatch):
    monkeypatch.setattr(conv_module.Conversation, "start", lambda self, *a, **k: "t1")  # no LLM call
    with TestClient(app) as client:
        promised = client.get("/history").headers["X-Conversation-ID"]
        assert app.state.conversations.find(client.cookies[SESSION_COOKIE]) is None
        assert client.post("/chat", json={"message": "hi", "conversation_id": promised}).status_code == 202
        assert app.state.conversations.find(client.cookies[SESSION_COOKIE]).id == promised
        assert client.get("/history").headers["X-Conversation-ID"] == promised


def test_following_the_promised_id_starts_the_conversation():
    store = Conversations(httpx.AsyncClient(), "http://registry", llm=object())
    assert store.find("s") is None
    promised = store.first_id("s")
    assert store.get("s").id == promised and store.first_id("other") != promised
