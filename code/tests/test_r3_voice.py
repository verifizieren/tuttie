"""Round 3 attacker: voice doors (assistant/voice.py) and the voice agent (voice/agent.py)."""

import asyncio
import inspect
import os

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test")

from assistant import voice  # noqa: E402
from assistant.app import app  # noqa: E402

AGENT = {"Authorization": "Bearer secret-for-tests"}


def configure(monkeypatch):
    monkeypatch.setattr(voice, "API_KEY", "key")
    monkeypatch.setattr(voice, "API_SECRET", "secret-for-tests")


def test_anonymous_token_requests_evict_a_live_users_voice_room(monkeypatch):
    """Any cookie-less client can ask for rooms (300/min per address); voice_rooms keeps only
    MAX_VOICE_ROOMS (1000), oldest first. So ~1000 anonymous /voice/token calls (3.5 min from one
    address, seconds from a few) unmap every live user's room: their speech gets 404 on
    /voice/say and /voice/events, and the voice agent goes mute. Scaled down to 20 rooms here."""
    configure(monkeypatch)
    monkeypatch.setattr(voice, "MAX_VOICE_ROOMS", 20)
    with TestClient(app) as victim:
        room = victim.post("/voice/token").json()["room"]
        assert room in app.state.voice_rooms
        for _ in range(20):
            assert TestClient(app).post("/voice/token").status_code == 200  # a fresh anonymous browser each time
        response = victim.get("/voice/events", params={"room": room}, headers=AGENT) if room not in app.state.voice_rooms else None
        assert response is None, f"the victim's live room was evicted: /voice/events {response.status_code}"


def test_agent_secret_is_compared_in_constant_time():
    """agent_only compares the bearer secret (the LiveKit API secret) with !=, not compare_digest."""
    source = inspect.getsource(voice.agent_only)
    assert "compare_digest" in source, source


def utter(text: str, handler) -> tuple[list[httpx.Request], list[str]]:
    """One finished user turn through the voice agent against a fake /voice/say: what was sent
    and what the agent said itself. The turn always ends in StopResponse (Tuttie answers)."""
    from livekit.agents import StopResponse
    from voice.agent import Tuttie

    seen, said = [], []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    class Msg:
        text_content = text

    async def run():
        async with httpx.AsyncClient(base_url="http://a", transport=httpx.MockTransport(recording)) as http:
            agent = Tuttie("tuttie-x", http)
            agent.speak = said.append
            try:
                await agent.on_user_turn_completed(None, Msg())
            except StopResponse:
                return
            raise AssertionError("the turn must end in StopResponse")
    asyncio.run(run())
    return seen, said


def test_a_long_utterance_is_not_silently_dropped():
    """/voice/say refuses text over MAX_MESSAGE_CHARS (2000) with 422; the voice agent ignored the
    status, so a long dictated request vanished without a word. Now it is cut to fit, and a
    refusal is spoken."""
    import json

    from assistant.inputs import MAX_MESSAGE_CHARS

    long = "please book the hotel " * 120  # ~2600 chars, a long dictated request
    seen, said = utter(long, lambda request: httpx.Response(202, json={"accepted": True}))
    sent = json.loads(seen[0].content)["text"]
    assert len(sent) <= MAX_MESSAGE_CHARS and long.startswith(sent) and long[len(sent)] == " " and said == []  # whole words
    seen, said = utter(long, lambda request: httpx.Response(422, json={"detail": "too long"}))
    assert seen and said == ["Sorry, that did not go through. Could you say it again?"]


def test_too_many_turns_and_a_dead_assistant_are_spoken():
    """429 (too many turns a minute) gets "One moment please."; a transport error does not raise
    out of the turn, the user hears a short line."""
    _, said = utter("book me a hotel please", lambda request: httpx.Response(429))
    assert said == ["One moment please."]

    def down(request):
        raise httpx.ConnectError("refused")
    _, said = utter("book me a hotel please", down)
    assert said == ["Sorry, that did not go through. Could you say it again?"]


def test_rooms_of_a_gone_conversation_go_first_and_the_grace_period_ends(monkeypatch):
    """Under the limit nothing goes; above it a room whose conversation is gone goes before an
    idle one, and a fresh room or one the voice agent follows never goes."""
    from assistant.voice import VoiceRooms

    monkeypatch.setattr(voice, "MAX_VOICE_ROOMS", 3)

    class Conv:
        def __init__(self, id):
            self.id = id

    class Store:
        by_session = {"a": Conv("ca"), "b": Conv("cb"), "c": Conv("cc")}

    rooms = VoiceRooms()
    rooms.add("old", ("a", "ca"), 0)
    rooms.add("gone", ("x", "cx"), 50)  # its conversation was dropped
    rooms.add("followed", ("b", "cb"), 0)
    rooms.live["followed"] += 1
    assert rooms.make_space(Store, 100) and list(rooms) == ["old", "followed"]  # "old" is still in its grace period
    rooms.add("fresh", ("c", "cc"), 100)
    assert rooms.make_space(Store, 200) and list(rooms) == ["followed", "fresh"]  # 200 s idle: "old" goes
