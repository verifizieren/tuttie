"""Round 3 attacker: voice doors (assistant/voice.py) and the voice agent (voice/agent.py)."""

import inspect
import os

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
