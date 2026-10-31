"""Tests that every request is its own turn and its events carry the turn id (assistant/conversations.py)."""

import asyncio
import os

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test")  # the app builds an LLM client; these tests never call it

from assistant.app import SESSION_COOKIE, app  # noqa: E402
from assistant.conversations import Conversation  # noqa: E402


def fake_chat(conv: Conversation, gate: asyncio.Event | None = None):
    """An assistant that uses one tool and answers, one request at a time like the real one."""
    async def chat(text, first_tool=None):
        async with conv.assistant.lock:
            conv.bus.emit("context", "info", f"reading for {text}")
            if gate is not None and text == "first":
                await gate.wait()
            conv.bus.emit("answer", "verified", f"answer to {text}")
    conv.assistant.chat = chat


def test_each_request_is_a_turn_and_its_events_carry_the_id():
    async def run():
        async with httpx.AsyncClient() as http:
            conv = Conversation(http, "http://registry", object())
            gate = asyncio.Event()
            fake_chat(conv, gate)
            first = conv.start("first")
            second = conv.start("second", said="Second, as shown", source="voice")
            await asyncio.sleep(0.01)  # the second request waits for the first one's answer
            gate.set()
            await asyncio.gather(*conv.chats)
            return conv.bus.history, first, second

    events, first, second = asyncio.run(run())
    assert first != second
    turns = [e for e in events if e["kind"] == "turn"]
    assert [(e["turn"], e["detail"]["said"], e["detail"]["source"]) for e in turns] == [
        (first, "first", "text"), (second, "Second, as shown", "voice")]
    answers = {e["turn"]: e["summary"] for e in events if e["kind"] == "answer"}
    assert answers == {first: "answer to first", second: "answer to second"}
    assert all(e["turn"] in (first, second) for e in events)


def test_events_outside_a_request_have_no_turn():
    async def run():
        async with httpx.AsyncClient() as http:
            conv = Conversation(http, "http://registry", object())
            return conv.bus.emit("answer", "verified", "hello")
    assert asyncio.run(run())["turn"] is None


def test_chat_returns_the_turn_id_and_shows_the_users_words():
    with TestClient(app) as client:
        client.post("/reset")
        fake_chat(app.state.conversations.get(client.cookies[SESSION_COOKIE]))
        response = client.post("/chat", json={"message": "Book Hotel X (ch.hotel-x).", "first_tool": "book",
                                              "said": "Book Hotel X"})
        assert response.status_code == 202
        turn_id = response.json()["turn_id"]
        opened = client.get("/history").json()[0]
        assert opened["kind"] == "turn" and opened["turn"] == turn_id
        assert opened["detail"] == {"turn_id": turn_id, "said": "Book Hotel X", "source": "text"}
        assert client.post("/chat", json={"message": "again"}).json()["turn_id"] != turn_id


def test_a_spoken_request_is_its_own_voice_turn(monkeypatch):
    from assistant import voice
    monkeypatch.setattr(voice, "API_KEY", "key")
    monkeypatch.setattr(voice, "API_SECRET", "secret-for-tests")
    with TestClient(app) as client:
        client.post("/reset")
        fake_chat(app.state.conversations.get(client.cookies[SESSION_COOKIE]))
        room = client.post("/voice/token").json()["room"]
        response = client.post("/voice/say", json={"room": room, "text": "Find me a quiet hotel"},
                               headers={"Authorization": "Bearer secret-for-tests"})
        assert response.status_code == 202
        opened = client.get("/history").json()[0]
        assert opened["turn"] == response.json()["turn_id"]
        assert opened["detail"]["source"] == "voice" and opened["detail"]["said"] == "Find me a quiet hotel"
