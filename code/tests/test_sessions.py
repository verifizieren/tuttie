"""Tests for the shared session, memory and context module (code/sessions)."""

import pytest

from sessions import Context, ContextItem, SessionClosed, SessionStore


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
