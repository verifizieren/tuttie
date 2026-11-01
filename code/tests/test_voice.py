"""Tests for Tuttie's voice: the room token and the voice agent's doors (assistant/voice.py), and
what the voice agent says (voice/agent.py). No LiveKit server or ElevenLabs call is needed."""

import asyncio
import base64
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test")  # the app builds an LLM client; these tests never call it

from assistant import voice  # noqa: E402
from assistant.app import SESSION_COOKIE, app  # noqa: E402
from assistant.events import EventBus  # noqa: E402
from voice.agent import UPDATES, filler_kind, meaningful, spoken, update_for, voice_on  # noqa: E402


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
        conv = app.state.conversations.get(client.cookies[SESSION_COOKIE])
        assert app.state.voice_rooms[token["room"]] == (client.cookies[SESSION_COOKIE], conv.id)
        grants = jwt_claims(token["token"])["video"]
        assert grants["canUpdateOwnMetadata"]  # the wallet sets voice=on|off: Tuttie speaks only in voice mode


def jwt_claims(token: str) -> dict:
    body = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


class Participant:
    def __init__(self, voice_attr):
        self.attributes = {"voice": voice_attr} if voice_attr else {}


class Room:
    def __init__(self, *attrs):
        self.remote_participants = {str(i): Participant(a) for i, a in enumerate(attrs)}


def test_tuttie_speaks_only_while_the_wallet_is_in_voice_mode():
    assert voice_on(Room("on")) and not voice_on(Room("off")) and not voice_on(Room(None)) and not voice_on(Room())


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
        rooms = voice.VoiceRooms()
        rooms.add("room", ("session", "conv"), 0)
        stream = voice.live_only(bus, rooms, "room")
        task = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0.05)
        bus.emit("answer", "verified", "new")
        frame = await asyncio.wait_for(task, 1)
        live = rooms.live["room"]
        await stream.aclose()
        return frame, live, rooms.live["room"]

    frame, live, after = asyncio.run(first_frame())
    assert '"summary": "new"' in frame
    assert (live, after) == (1, 0)  # live while the agent follows the room, not after


def test_answers_are_spoken_without_citations_markdown_or_emoji():
    assert spoken("Booked **BK-1** for CHF 128 [16]. 🐶\nIgnored: scam (broken seal)") == "Booked BK-1 for 128 francs."


def test_temperatures_and_percentages_are_said_in_words():
    assert spoken("Between 6.4 and 11.6 °C, around 8°C, a 25% chance.") == \
        "Between 6.4 and 11.6 degrees, around 8 degrees, a 25 percent chance."


def test_times_are_said_as_people_say_them():
    assert spoken("Around 9 °C at 18:00, 8 at 20:00, train at 00:52, back by 12:00, until 00:00, from 10:30.") == \
        "Around 9 degrees at 6 pm, 8 at 8 pm, train at 12:52 am, back by noon, until midnight, from 10:30 am."


def test_times_already_said_in_12_hours_are_kept():
    # Tuttie is asked to write "8:30 pm": the voice must not add a second (wrong) am or pm.
    assert spoken("At 8:30 pm, then 12:52 am, 6:00 PM, 1:00 to 2:00 am, or 7:05.") == \
        "At 8:30 pm, then 12:52 am, 6:00 PM, 1:00 to 2:00 am, or 7:05."


def test_citation_and_id_notes_in_brackets_are_not_read_out():
    assert spoken("The total is CHF 128 [confirmed]. Tax paid [receipt RC-A14786]. Fine [3, 4].") == \
        "The total is 128 francs. Tax paid. Fine."


def test_facts_in_brackets_are_kept_without_the_brackets():
    # A fee or a condition must never be hidden just because the model put it in brackets.
    assert spoken("Total CHF 128 [+ CHF 40 cleaning fee]. Booked [non-refundable, no cancellation].") == \
        "Total 128 francs + 40 francs cleaning fee. Booked non-refundable, no cancellation."


def test_durations_and_links_are_not_mangled():
    assert spoken("The trip takes 1:30 hours, 18:00:30 sharp. [Rheinblick](https://x.y) is good.") == \
        "The trip takes 1:30 hours, 18:00:30 sharp. Rheinblick is good."


def test_long_runs_of_spaces_are_fast():
    import time
    start = time.perf_counter()
    spoken(" " * 50000 + "x")
    assert time.perf_counter() - start < 0.2


def test_amounts_are_said_in_francs():
    assert spoken("CHF 1 tax, 70 CHF over, CHF 12.50 left, in CHF.") == "1 franc tax, 70 francs over, 12.50 francs left, in francs."


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


def test_fillers_match_the_request():
    assert filler_kind("I want to book something") == "task"
    assert filler_kind("What's the weather like tomorrow?") == "question"
    assert filler_kind("Tell me a joke") == "other"


def test_a_wallets_voice_report_is_logged_and_cut(capsys):
    with TestClient(app) as client:
        assert client.post("/voice/diag", content=b'{"state": "failed"}' + b"x" * 5000).status_code == 204
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith('voice diag: {"state": "failed"}') and len(line) < voice.DIAG_MAX_BYTES + 20


def test_old_voice_room_cannot_send_into_a_new_chat(monkeypatch):
    configure(monkeypatch)
    with TestClient(app) as client:
        old_id = client.get('/history').headers['X-Conversation-ID']
        room = client.post('/voice/token').json()['room']
        client.post('/conversations')
        response = client.post('/voice/say', json={'room': room, 'text': 'Book it'},
                               headers={'Authorization': 'Bearer secret-for-tests'})
        assert response.status_code == 409
        assert client.get('/history').json() == []
        assert client.post(f'/conversations/{old_id}/resume').status_code == 200


def test_short_card_commands_are_not_discarded_as_noise():
    for command in ("Like.", "Pass!", "Next", "Weiter", "Überspringen", "Gefällt mir"):
        assert meaningful(command)
    assert not meaningful("um") and not meaningful("(laughs)")


def test_reject_skip_and_similar_short_choices_survive_speech_filter():
    for command in ("Reject", "Skip", "Dislike", "Ablehnen", "Behalten", "No thanks"):
        assert meaningful(command)


def test_a_token_loop_gets_429_after_its_share_of_rooms(monkeypatch):
    """Each new room starts a voice agent job: one conversation gets a few a minute, then 429."""
    configure(monkeypatch)
    monkeypatch.setattr(voice, "ROOMS_PER_CONVERSATION_PER_MIN", 3)
    with TestClient(app) as client:
        responses = [client.post("/voice/token") for _ in range(5)]
        assert [r.status_code for r in responses] == [200] * 3 + [429] * 2
        assert len({r.json()["room"] for r in responses[:3]}) == 3  # never a room twice
        assert responses[-1].headers["retry-after"] == "60"


def test_one_client_address_cannot_open_rooms_without_end(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(voice, "ROOMS_PER_CLIENT_PER_MIN", 4)
    with TestClient(app):  # the service starts with a fresh counter
        # Cookie-less: every call is a new browser and conversation, from the same address.
        statuses = [TestClient(app).post("/voice/token").status_code for _ in range(6)]
    assert statuses == [200] * 4 + [429] * 2


def test_the_room_counter_forgets_after_a_minute():
    counter, owner = voice.RoomThrottle(), ("s", "c")
    for _ in range(voice.ROOMS_PER_CONVERSATION_PER_MIN):
        assert counter.allow(owner, "1.2.3.4", now=0)
    assert not counter.allow(owner, "1.2.3.4", now=1)
    assert counter.allow(owner, "1.2.3.4", now=61)


def test_answer_notes_shared_with_the_wallet():
    """The same cases as the wallet's cleanAnswer (tests/fixtures/answer_notes.json): screen and voice agree."""
    cases = json.loads((Path(__file__).parent / "fixtures" / "answer_notes.json").read_text())
    for case in cases:
        assert spoken(case["in"]) == case["spoken"], case["in"]
