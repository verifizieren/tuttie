"""Tests for signed tool calls (aps/call.py): signature over tool + args, freshness, nonces."""

import copy
from datetime import datetime, timedelta, timezone

from nacl.signing import SigningKey

from aps import load_signing_key, public_key_b64
from aps.call import CALL_MAX_AGE_S, NonceBook, call_body, sign_call, verify_call

NOW = datetime(2026, 11, 14, 0, 12, tzinfo=timezone.utc)
STAMP = "2026-11-14T00:12:00Z"
AGENT = "ch.tuttie.test"


def make_call(key, tool="book", args=None, **kwargs):
    return sign_call(tool, args if args is not None else {"room_type": "double"}, AGENT, key,
                     timestamp=STAMP, **kwargs)


def test_signed_call_verifies_for_its_tool():
    key = SigningKey.generate()
    call = make_call(key, delegation={"agent_id": AGENT})
    assert verify_call(call, public_key_b64(key), now=NOW)
    assert verify_call(call, public_key_b64(key), tool="book", now=NOW)
    assert not verify_call(call, public_key_b64(key), tool="pay", now=NOW)
    assert call["delegation"] == {"agent_id": AGENT}  # attached, outside the signed body
    assert set(call_body(call)) == {"tool", "args", "agent_id", "nonce", "timestamp"}


def test_every_call_gets_its_own_nonce():
    key = SigningKey.generate()
    first, second = (sign_call("book", {}, AGENT, key) for _ in range(2))
    assert first["nonce"] != second["nonce"] and len(first["nonce"]) == 32


def test_tampered_tool_args_or_caller_do_not_verify():
    key = SigningKey.generate()
    call = make_call(key, args={"room_type": "double", "approval": {"amount_chf": 128}})
    for field, value in [("tool", "pay"), ("agent_id", "ch.someone.else"), ("nonce", "0" * 32),
                         ("timestamp", "2026-11-14T00:11:00Z")]:
        assert not verify_call({**call, field: value}, public_key_b64(key), now=NOW), field
    swapped = copy.deepcopy(call)
    swapped["args"]["approval"]["amount_chf"] = 1
    assert not verify_call(swapped, public_key_b64(key), now=NOW)


def test_other_key_or_malformed_calls_do_not_verify():
    key = SigningKey.generate()
    call = make_call(key)
    assert not verify_call(call, public_key_b64(SigningKey.generate()), now=NOW)
    assert not verify_call({k: v for k, v in call.items() if k != "nonce"}, public_key_b64(key), now=NOW)
    assert not verify_call({**call, "args": ["not", "an", "object"]}, public_key_b64(key), now=NOW)
    assert not verify_call({**call, "signature": "not base64"}, public_key_b64(key), now=NOW)
    assert not verify_call("not a call", public_key_b64(key), now=NOW)
    assert call_body(None) is None


def test_calls_outside_the_time_window_are_refused():
    key = SigningKey.generate()
    call = make_call(key)
    later = NOW + timedelta(seconds=CALL_MAX_AGE_S + 1)
    assert verify_call(call, public_key_b64(key), now=NOW + timedelta(seconds=CALL_MAX_AGE_S))
    assert not verify_call(call, public_key_b64(key), now=later)
    assert not verify_call(call, public_key_b64(key), now=NOW - timedelta(minutes=5))  # stamped in the future


def test_nonce_book_accepts_each_nonce_once_per_agent():
    book = NonceBook()
    assert book.use(AGENT, "n1", NOW)
    assert not book.use(AGENT, "n1", NOW + timedelta(seconds=10))
    assert book.use("ch.other.agent", "n1", NOW)  # nonces belong to their agent
    assert book.use(AGENT, "n2", NOW)


def test_nonce_book_forgets_nonces_once_their_calls_are_too_old_anyway():
    book = NonceBook(max_age_s=60)
    book.use(AGENT, "n1", NOW)
    book.use(AGENT, "n2", NOW + timedelta(seconds=200))  # past 60 s + twice the skew
    assert ("ch.tuttie.test", "n1") not in book.seen and len(book.seen) == 1  # n1 dropped, n2 kept
    assert not book.use(AGENT, "n2", NOW + timedelta(seconds=210))


def test_tuttie_signs_calls_the_registry_key_verifies():
    from aps.keys import load_public_key
    tuttie = "ch.tuttie.alex-muster"
    call = sign_call("book", {"room_type": "double"}, tuttie, load_signing_key(tuttie))
    assert verify_call(call, load_public_key(tuttie), tool="book")
