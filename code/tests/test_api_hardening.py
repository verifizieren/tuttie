"""Tests that the assistant's HTTP API stays consistent under odd or concurrent requests (assistant/app.py)."""

import inspect
import os

os.environ.setdefault("OPENAI_API_KEY", "test")  # the app builds an LLM client; these tests never call it

from assistant import app as app_module  # noqa: E402
from assistant import voice  # noqa: E402


def test_routes_touching_conversations_run_on_the_event_loop():
    # A plain `def` runs in a worker thread: two first requests of one browser then each created
    # a conversation (seen live: 4 ids for 6 parallel /history calls), and decisions or resets
    # woke the event loop from a foreign thread.
    handlers = [app_module.conversation, app_module.chat, app_module.reset, app_module.pending_approvals,
                app_module.decide, app_module.history, app_module.events,
                voice.voice_token, voice.voice_say, voice.voice_events]
    assert [h.__name__ for h in handlers if not inspect.iscoroutinefunction(h)] == []


def test_chat_refuses_blank_huge_or_broken_text_before_it_reaches_the_conversation():
    from fastapi.testclient import TestClient

    from assistant.app import SESSION_COOKIE, app
    from assistant.inputs import MAX_MESSAGE_CHARS

    with TestClient(app) as client:
        client.get("/history")
        conv = app.state.conversations.get(client.cookies[SESSION_COOKIE])
        bad = [{"message": ""}, {"message": "   "}, {"message": "x" * (MAX_MESSAGE_CHARS + 1)},
               {"message": "hi", "said": "y" * (MAX_MESSAGE_CHARS + 1)}]
        for body in bad:
            assert client.post("/chat", json=body).status_code == 422
        # A lone surrogate is valid JSON but not UTF-8: stored, it made every /history fail with 500.
        response = client.post("/chat", content=b'{"message": "hi \\ud800"}',
                               headers={"content-type": "application/json"})
        assert response.status_code == 422
        assert conv.bus.history == [] and conv.turns == 0
        assert client.get("/history").status_code == 200


def test_spoken_text_is_checked_like_typed_text():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        voice.Said(room="r", text="")
    assert voice.Said(room="r", text="  Find a hotel ").text == "Find a hotel"


def test_cookieless_requests_cannot_push_out_peoples_chats(monkeypatch):
    import httpx

    from assistant import conversations as conv_module
    from assistant.conversations import Conversations

    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 3)
    store = Conversations(httpx.AsyncClient(), "http://registry", llm=object())
    chatting = store.get("chatting")
    chatting.bus.emit("answer", "verified", "Here are three hotels")
    waiting = store.get("waiting")
    waiting.approvals.pending["ap-1"] = {"id": "ap-1"}
    for n in range(10):  # e.g. link previews or curl, each without a cookie
        store.get(f"anonymous-{n}")
    assert store.by_session["chatting"] is chatting and store.by_session["waiting"] is waiting
    assert len(store.by_session) == 3
    store.by_session["anonymous-9"].bus.emit("answer", "verified", "Hi")  # now all three are used
    store.get("someone-new")  # the least recently used idle chat goes; a pending approval stays
    assert "chatting" not in store.by_session and store.by_session["waiting"] is waiting
