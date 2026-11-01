"""Red team round 4: saved and active chats, ids and the turn throttle under bot load (assistant/conversations.py, throttle.py, app.py)."""

import asyncio
import os
import time

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test")

from assistant import conversations as conv_module  # noqa: E402
from assistant.app import SESSION_COOKIE, app  # noqa: E402
from assistant.conversations import Conversations  # noqa: E402
from assistant.throttle import Throttle, address_key  # noqa: E402


def store():
    """A conversation store that never calls an LLM or the registry."""
    return Conversations(httpx.AsyncClient(), "http://registry", llm=object())


def chatted(s, sid, turns):
    """A session whose conversation has history and `turns` finished turns (no LLM)."""
    conv = s.get(sid)
    conv.turns = turns
    conv.bus.emit("answer", "verified", "x")
    return conv


def test_r4a_one_saved_chat_per_bot_does_not_wipe_a_real_users_saved_chat(monkeypatch):
    """N1: with every browser at one saved chat, the tie went to the first saver (the real user)."""
    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 3)
    s = store()
    chatted(s, "alice", 3)
    s.switch("alice")  # alice keeps her chat with the offers
    for n in range(4):
        chatted(s, f"bot{n}", 1)
        s.switch(f"bot{n}")  # each bot saves one chat with history
    assert any(key[0] == "alice" for key in s.saved), "alice's saved chat was dropped for bots' ones"
    assert len(s.saved) == 3


def test_r4a_saved_chats_with_agreements_outlast_those_without(monkeypatch):
    """N1: a saved chat with an agreement goes after every chat that has only offers."""
    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 2)
    s = store()
    for n in range(3):
        chatted(s, f"bot{n}", 1)
    alice = chatted(s, "alice", 1)  # saved last: on a plain tie she would go first
    alice.assistant.toolbox.agreements["hotel"] = {"payload": {}}
    for sid in ("bot0", "bot1", "alice", "bot2"):
        s.switch(sid)
    assert ("alice", alice.id) in s.saved


def test_r4a_empty_chats_are_not_saved():
    """N2: "new chat" on an empty chat keeps nothing that could push out someone else's chat."""
    s = store()
    s.get("bot")
    s.switch("bot")
    assert not s.saved


def test_r4a_new_chat_endpoint_is_throttled_and_cannot_push_out_a_saved_chat():
    """N2: cookieless POST /conversations from one address get 429 after their share and save nothing."""
    with TestClient(app) as alice:
        alice.get("/history")
        s = app.state.conversations
        s.get(alice.cookies[SESSION_COOKIE]).bus.emit("answer", "verified", "Rheinblick agreed at CHF 150")
        assert alice.post("/conversations").status_code == 200
        (key, _), = s.saved.items()
        codes = [TestClient(app).post("/conversations").status_code for _ in range(conv_module.MAX_CONVERSATIONS)]
        assert 429 in codes and set(codes) <= {200, 429}
        assert key in s.saved, "alice's saved chat with offers was pushed out by bot chats"


def test_r4a_new_chat_is_throttled_per_browser(monkeypatch):
    """N2: one browser pressing "new chat" again and again gets 429 with Retry-After."""
    monkeypatch.setattr("assistant.app.NEW_CHATS_PER_SESSION_PER_MIN", 2)
    with TestClient(app) as client:
        codes = [client.post("/conversations").status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        assert int(client.post("/conversations").headers["Retry-After"]) >= 1


def test_r4a_bots_with_as_many_turns_do_not_push_out_an_idle_real_user(monkeypatch):
    """N3: above 2*MAX the most recently started idle session goes, not the long-lived one."""
    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 2)
    s = store()
    chatted(s, "alice", 3)
    for n in range(5):
        chatted(s, f"bot{n}", 3)
    assert "alice" in s.by_session, "an idle real user with offers on screen was dropped for bot chats"


def test_r4a_a_chat_with_an_approval_outlasts_newer_offers_only_chats(monkeypatch):
    """N3: a decided approval (a booking) counts more than session age."""
    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 1)
    s = store()
    chatted(s, "early", 1)
    late = chatted(s, "booker", 1)
    late.bus.emit("approval", "approved", "Booked")
    chatted(s, "third", 1)
    assert "booker" in s.by_session and "early" not in s.by_session


def test_r4a_ipv6_addresses_of_one_prefix_share_one_limit(monkeypatch):
    """N4: the per-address key of an IPv6 client is its /64."""
    monkeypatch.setattr(conv_module.Conversation, "start", lambda self, *a, **k: "t1")  # no LLM
    monkeypatch.setattr("assistant.app.TURNS_PER_CLIENT_PER_MIN", 2)
    with TestClient(app):
        codes = [TestClient(app, client=(f"2001:db8:1:2::{n:x}", 50000)).post("/chat", json={"message": "hi"}).status_code
                 for n in range(1, 8)]
    assert codes.count(429) >= 5, f"7 turns from one /64 with limit 2: {codes}"


def test_address_key_groups_ipv6_by_64_and_keeps_ipv4():
    """N4: IPv4 (also IPv4-mapped IPv6) by full address, IPv6 by /64, anything else as is."""
    assert address_key("2001:db8:1:2::5") == address_key("2001:db8:1:2:ffff::1") == "2001:db8:1:2::/64"
    assert address_key("2001:db8:1:3::5") != address_key("2001:db8:1:2::5")
    assert address_key("192.0.2.7") == "192.0.2.7" != address_key("192.0.2.8")
    assert address_key("::ffff:192.0.2.7") == "192.0.2.7"
    assert address_key("unknown") == "unknown"


def test_r4a_a_refused_spoken_turn_is_answered_with_one_moment_please():
    """N5: a 429 on /voice/say is spoken ("One moment please."), never dropped silently."""
    from livekit.agents import StopResponse
    from voice.agent import BUSY, Tuttie

    async def refuse(request):
        return httpx.Response(429, json={"detail": "too many turns"}, headers={"Retry-After": "30"})

    async def run():
        http = httpx.AsyncClient(transport=httpx.MockTransport(refuse), base_url="http://a")
        agent = Tuttie("room", http)
        spoken = []
        agent.speak = spoken.append

        class Msg:
            text_content = "book the cheaper hotel please"

        try:
            await agent.on_user_turn_completed(None, Msg())
        except StopResponse:
            pass
        return spoken

    assert asyncio.run(run()) == [BUSY]


def test_r4a_a_dropped_sessions_old_id_never_comes_back(monkeypatch):
    """N6: once alice is forgotten from the bounded generation memory, she still gets a new id."""
    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 1)
    s = store()
    first = s.get("alice").id
    s.get("alice").bus.emit("answer", "verified", "x")
    s._drop("alice")
    for n in range(11):
        s.get(f"bot{n}").bus.emit("answer", "verified", "x")
        s._drop(f"bot{n}")
    assert "alice" not in s._generations
    second = s.get("alice").id
    assert second != first, "alice's dropped conversation id was handed out again"
    s.get("alice").bus.emit("answer", "verified", "x")
    s._drop("alice")
    for n in range(11):
        s.get(f"late{n}").bus.emit("answer", "verified", "x")
        s._drop(f"late{n}")
    assert s.get("alice").id not in (first, second)


def test_first_id_promised_by_history_is_the_one_created(monkeypatch):
    """N6: the first-conversation flow (GET /history id -> /events) still holds after drops."""
    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 1)
    s = store()
    for n in range(15):
        s.get(f"bot{n}").bus.emit("answer", "verified", "x")
        s._drop(f"bot{n}")
    promised = s.first_id("new")
    assert s.get("new").id == promised


def test_r4a_throttle_does_not_sweep_every_key_on_every_request():
    """N7: above MAX_KEYS live keys, a request does not walk all keys (amortised sweep)."""
    t, now = Throttle(), time.monotonic()
    for n in range(6000):
        t.wait({("session", n): 10}, now)
    start = time.perf_counter()
    for n in range(200):
        t.wait({("session", f"x{n}"): 10}, now)
    per_call_ms = (time.perf_counter() - start) * 1000 / 200
    assert per_call_ms < 0.5, f"{per_call_ms:.2f} ms per request once 5000 sessions are recent"


def test_throttle_still_forgets_idle_keys_above_max_keys():
    """N7: keys with nothing in the last minute are still forgotten once there are many."""
    t, now = Throttle(), time.monotonic()
    for n in range(6000):
        t.wait({("session", n): 10}, now)
    for n in range(6000):
        t.wait({("later", n): 10}, now + 120)
    assert len(t.recent) <= 6000 + 1


def test_refused_chat_requests_do_not_count_as_turns(monkeypatch):
    """A 422 (bad first_tool) or 409 (stale chat) is refused before the turn is counted."""
    monkeypatch.setattr(conv_module.Conversation, "start", lambda self, *a, **k: "t1")  # no LLM
    monkeypatch.setattr("assistant.app.TURNS_PER_SESSION_PER_MIN", 2)
    with TestClient(app) as client:
        for _ in range(3):
            assert client.post("/chat", json={"message": "hi", "first_tool": "pay"}).status_code == 422
            assert client.post("/chat", json={"message": "hi", "conversation_id": "old"}).status_code == 409
        assert client.cookies.get(SESSION_COOKIE) not in app.state.conversations.by_session
        assert [client.post("/chat", json={"message": "hi"}).status_code for _ in range(3)] == [202, 202, 429]


def test_a_browser_after_new_chat_is_not_dropped_as_empty(monkeypatch):
    """After "new chat" the active chat is empty, but the saved one makes the session worth keeping."""
    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 1)
    s = store()
    chatted(s, "alice", 1)
    s.switch("alice")
    for n in range(5):
        s.get(f"anonymous-{n}")
    assert "alice" in s.by_session and any(key[0] == "alice" for key in s.saved)
