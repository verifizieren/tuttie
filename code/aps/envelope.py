"""Signed envelopes: every tool and agent response is wrapped in one of these."""

from datetime import datetime, timezone

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey

from aps.canonical import b64decode, b64encode, canonical
from aps.keys import verify_key_from_b64


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sign_bytes(signing_key: SigningKey, obj) -> str:
    """Sign the canonical JSON of obj and return the base64 signature."""
    return b64encode(signing_key.sign(canonical(obj)).signature)


def verify_bytes(public_key: str, obj, signature: str) -> bool:
    """Check a base64 signature over the canonical JSON of obj."""
    try:
        verify_key_from_b64(public_key).verify(canonical(obj), b64decode(signature))
        return True
    except (BadSignatureError, ValueError, TypeError):
        return False


def sign_envelope(node_id: str, payload: dict, signing_key: SigningKey, timestamp: str | None = None) -> dict:
    body = {"node_id": node_id, "timestamp": timestamp or utc_now(), "payload": payload}
    return {**body, "signature": sign_bytes(signing_key, body)}


def verify_envelope(envelope: dict, public_key: str, expected_node_id: str | None = None) -> bool:
    """True if the envelope is well formed, from the expected node, and signed by public_key."""
    try:
        body = {k: envelope[k] for k in ("node_id", "timestamp", "payload")}
        signature = envelope["signature"]
    except (KeyError, TypeError):
        return False
    if expected_node_id is not None and body["node_id"] != expected_node_id:
        return False
    return verify_bytes(public_key, body, signature)
