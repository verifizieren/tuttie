"""Tests for the shared session, memory and context module (code/sessions)."""

import asyncio

import pytest

from sessions import Context, ContextItem, SessionClosed, SessionFull, SessionStore, StoreFull


def test_unclassified_context_is_private_and_never_shared():
    context = Context().add("budget_limit_chf", 200).add("date", "2026-11-14", "public")
    assert context.share("negotiation") == {"date": "2026-11-14"}
    assert context.private_keys() == {"budget_limit_chf"}
    with pytest.raises(ValueError):
        context.share("private")


def test_share_levels_include_everything_up_to_the_level():
    context = (Context().add("date", "2026-11-14", "public").add("dog", True, "negotiation")
               .add("max_price_chf", 200, "private"))
    assert context.share("public") == {"date": "2026-11-14"}
    assert context.share("negotiation") == {"date": "2026-11-14", "dog": True}
    with pytest.raises(ValueError):
        ContextItem("x", 1, "secret")


def test_session_memory_keeps_turns_in_order_and_stops_when_closed():
    store = SessionStore(owner="hotel")
    session = store.open(peer="tuttie/a", purpose="negotiation", context={"date": "2026-11-14"})
    session.add("peer", "message", {"text": "hi"})
    session.add("self", "reply", {"answer": "hello"})
    assert [t["kind"] for t in session.transcript()] == ["message", "reply"]
    store.close(session.id)
    with pytest.raises(SessionClosed):
        session.add("peer", "message", {"text": "still there?"})
    assert store.get(session.id).to_dict()["status"] == "closed"


def test_sessions_of_one_store_are_isolated():
    store = SessionStore(owner="hotel")
    a, b = store.open("tuttie/a", "negotiation"), store.open("tuttie/b", "negotiation")
    a.add("peer", "message", {"text": "for a"})
    assert a.id != b.id and b.turns == []
    assert {s.id for s in store.open_sessions()} == {a.id, b.id}
    with pytest.raises(KeyError):
        store.get("se-unknown")


def test_a_full_store_closes_its_least_recently_used_idle_session():
    store = SessionStore(owner="hotel", max_open=2)
    old, busy = store.open("a", "negotiation"), store.open("b", "negotiation")
    busy.add("peer", "message", {"text": "newer"})
    old.used_at = busy.used_at - 10
    new = store.open("c", "negotiation")
    assert old.status == "closed" and busy.status == "open" and new.status == "open"


def test_a_store_whose_sessions_are_all_busy_refuses_with_store_full():
    async def scenario():
        store = SessionStore(owner="hotel", max_open=1)
        session = store.open("a", "negotiation")
        async with session.lock:
            with pytest.raises(StoreFull):
                store.open("b", "negotiation")
    asyncio.run(scenario())


def test_closed_sessions_are_freed_beyond_keep_closed_and_turns_are_capped():
    store = SessionStore(owner="hotel", keep_closed=3)
    ids = [store.open(f"p{i}", "negotiation").id for i in range(10)]
    for sid in ids:
        store.close(sid)
    assert list(store.sessions) == ids[-3:]
    session = store.open("x", "negotiation")
    assert len(session.id) >= 3 + 32 and session.token and "token" not in session.to_dict()
    for _ in range(session.max_turns):
        session.add("peer", "message", {"text": "hi"})
    with pytest.raises(SessionFull):
        session.add("peer", "message", {"text": "one too many"})
