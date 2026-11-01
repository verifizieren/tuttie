"""Red team round 2: the conversation store cannot be used to push out other people's chats (assistant/conversations.py, app.py)."""

import os

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test")

from assistant import conversations as conv_module  # noqa: E402
from assistant.app import SESSION_COOKIE, app  # noqa: E402
from assistant.conversations import Conversations  # noqa: E402


def test_r2_one_browser_wipes_every_other_users_saved_chats_with_new_chat_clicks(monkeypatch):
    """`saved` is one global LRU of MAX_CONVERSATIONS: one cookie pressing POST /conversations
    MAX times (no LLM, no rate limit) evicts and reset()s everybody else's saved chats."""
    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 5)
    with TestClient(app) as alice, TestClient(app) as mallory:
        old = alice.get("/history").headers["X-Conversation-ID"]
        app.state.conversations.get(alice.cookies[SESSION_COOKIE]).bus.emit("answer", "verified", "deals")
        alice.post("/conversations")  # alice starts a new chat; her first one (with its deals) is saved
        for _ in range(6):
            assert mallory.post("/conversations").status_code == 200
        assert alice.post(f"/conversations/{old}/resume").status_code == 200, "alice's saved chat was wiped by another browser"


def test_r2_busy_attacker_chats_push_out_an_idle_real_user(monkeypatch):
    """Busy conversations are never evicted, so N cookieless POST /chat (unthrottled) make the
    idle real user the only evictable one: her chat (with history and agreements) is reset."""
    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 3)
    store = Conversations(httpx.AsyncClient(), "http://registry", llm=object())
    alice = store.get("alice")
    alice.bus.emit("answer", "verified", "Book Rheinblick for CHF 128?")
    for i in range(3):
        conv = store.get(f"bot{i}")
        conv.bus.emit("turn", "pending", "hi")
        conv.chats.add(f"running-{i}")  # what conv.start() does while the LLM thinks
    assert "alice" in store.by_session, "an idle user with history was evicted by busy attacker chats"


def test_r2_an_evicted_session_gets_the_same_conversation_id_back(monkeypatch):
    """first_id is a pure HMAC of the session: after eviction the NEW empty conversation has the
    old id, so the wallet's conversation_id guard (409 'active chat changed') no longer fires and
    a late first_tool=book message runs in a conversation without the agreements."""
    monkeypatch.setattr(conv_module, "MAX_CONVERSATIONS", 1)
    store = Conversations(httpx.AsyncClient(), "http://registry", llm=object())
    store.get("bob").bus.emit("answer", "verified", "y")
    old = store.get("alice")
    old.bus.emit("answer", "verified", "x")
    store.get("carol")  # above twice the limit: alice (the most recently started idle chat) is dropped
    assert "alice" not in store.by_session
    assert store.get("alice").id != old.id, "a recreated conversation reuses the evicted one's id"


def test_a_browser_keeps_at_most_its_share_of_saved_chats(monkeypatch):
    monkeypatch.setattr(conv_module, "SAVED_PER_SESSION", 2)
    store = Conversations(httpx.AsyncClient(), "http://registry", llm=object())
    first = store.get("alice").id
    ids = []
    for _ in range(3):
        store.get("alice").bus.emit("answer", "verified", "x")  # empty chats are not kept
        ids.append(store.switch("alice").id)
    assert [key[1] for key in store.saved] == ids[:2]  # her own oldest (the first chat) went
    assert first not in {key[1] for key in store.saved}


def test_chat_turns_are_limited_per_browser_and_refused_turns_create_nothing(monkeypatch):
    from assistant import throttle

    monkeypatch.setattr(conv_module.Conversation, "start", lambda self, *a, **k: "t1")  # no LLM call
    monkeypatch.setattr("assistant.app.TURNS_PER_SESSION_PER_MIN", 2)
    monkeypatch.setattr("assistant.app.TURNS_PER_CLIENT_PER_MIN", 3)
    assert throttle.TURNS_PER_SESSION_PER_MIN >= 5
    with TestClient(app) as alice:
        assert [alice.post("/chat", json={"message": "hi"}).status_code for _ in range(3)] == [202, 202, 429]
        refused = alice.post("/chat", json={"message": "hi"})
        assert refused.status_code == 429 and 1 <= int(refused.headers["Retry-After"]) <= 61
        assert "wait" in refused.json()["detail"]
        store = app.state.conversations
        before = set(store.by_session)
        bot = TestClient(app)  # same address, new browser (no `with`: that would restart the service)
        assert bot.post("/chat", json={"message": "hi"}).status_code == 202  # the address's last turn
        assert TestClient(app).post("/chat", json={"message": "hi"}).status_code == 429
        assert len(store.by_session) == len(before) + 1


def test_a_refused_voice_token_creates_no_conversation(monkeypatch):
    from assistant import voice

    monkeypatch.setattr(voice, "API_KEY", "key")
    monkeypatch.setattr(voice, "API_SECRET", "secret-for-tests-secret-for-tests")
    monkeypatch.setattr(voice, "ROOMS_PER_CLIENT_PER_MIN", 1)
    with TestClient(app) as alice:
        assert alice.post("/voice/token").status_code == 200
        store = app.state.conversations
        before = set(store.by_session)
        assert TestClient(app).post("/voice/token").status_code == 429  # same address, new browser
        assert set(store.by_session) == before


def test_spoken_turns_count_towards_the_browsers_turn_limit(monkeypatch):
    from assistant import voice

    monkeypatch.setattr(voice, "API_KEY", "key")
    monkeypatch.setattr(voice, "API_SECRET", "secret-for-tests-secret-for-tests")
    monkeypatch.setattr(voice, "VOICE_TURNS_PER_SESSION_PER_MIN", 2)
    monkeypatch.setattr(conv_module.Conversation, "start", lambda self, *a, **k: "t1")  # no LLM call
    agent = {"Authorization": "Bearer secret-for-tests-secret-for-tests"}
    with TestClient(app) as client:
        room = client.post("/voice/token").json()["room"]
        codes = [client.post("/voice/say", json={"room": room, "text": "hi"}, headers=agent).status_code
                 for _ in range(3)]
        assert codes == [202, 202, 429]
