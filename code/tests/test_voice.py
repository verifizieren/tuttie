"""Tests for Tuttie's voice: the room token and the voice agent's doors (assistant/voice.py), and
what the voice agent says (voice/agent.py). No LiveKit server or ElevenLabs call is needed."""

import asyncio
import os

from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test")  # the app builds an LLM client; these tests never call it

from assistant import voice  # noqa: E402
from assistant.app import SESSION_COOKIE, app  # noqa: E402
from assistant.events import EventBus  # noqa: E402
from voice.agent import UPDATES, meaningful, spoken, update_for  # noqa: E402


def configure(monkeypatch):
    monkeypatch.setattr(voice, "API_KEY", "key")
    monkeypatch.setattr(voice, "API_SECRET", "secret-for-tests")


def test_without_livekit_keys_voice_is_off(monkeypatch):
    monkeypatch.setattr(voice, "API_KEY", "")
    with TestClient(app) as client:
        assert client.post("/voice/token").status_code == 503


def test_a_token_opens_a_room_tied_to_this_browsers_conversation(monkeypatch):
    configure(monkeypatch)
    with TestClient(app) as client:
        token = client.post("/voice/token", headers={"x-forwarded-proto": "https", "x-forwarded-host": "web4.example"}).json()
        assert token["url"] == "wss://web4.example" and token["token"].count(".") == 2
        assert app.state.voice_rooms[token["room"]] == client.cookies[SESSION_COOKIE]


def test_only_the_voice_agent_may_speak_into_a_room(monkeypatch):
    configure(monkeypatch)
    with TestClient(app) as client:
        room = client.post("/voice/token").json()["room"]
        assert client.post("/voice/say", json={"room": room, "text": "hi"}).status_code == 401
        agent = {"Authorization": "Bearer secret-for-tests"}
        assert client.post("/voice/say", json={"room": "tuttie-unknown", "text": "hi"}, headers=agent).status_code == 404


def test_the_agent_only_gets_new_events():
    bus = EventBus()
    bus.emit("answer", "verified", "old")

    async def first_frame():
        stream = voice.live_only(bus)
        task = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0.05)
        bus.emit("answer", "verified", "new")
        return await asyncio.wait_for(task, 1)

    assert '"summary": "new"' in asyncio.run(first_frame())


def test_answers_are_spoken_without_citations_markdown_or_emoji():
    assert spoken("Booked **BK-1** for CHF 128 [16]. 🐶\nIgnored: scam (broken seal)") == "Booked BK-1 for CHF 128."


def test_it_keeps_quiet_except_when_the_user_must_approve():
    said = set()
    assert update_for({"kind": "context", "status": "info", "detail": {"phase": "reading"}}, said) is None
    assert update_for({"kind": "marketplace", "status": "verified", "detail": {"phase": "cards"}}, said) is None
    approval = {"kind": "approval", "status": "pending", "detail": {}}
    assert update_for(approval, said) == UPDATES["approval"]
    assert update_for(approval, said) is None  # once per turn


def test_noise_and_stray_words_are_not_requests():
    assert meaningful("I want to book something")
    assert not meaningful("Okay.") and not meaningful("(laughs)") and not meaningful("[music] hm")
