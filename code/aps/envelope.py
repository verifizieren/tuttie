"""Signed envelopes: every tool and agent response is wrapped in one of these.

The signature covers the timestamp, so a receiver that wants a live answer can also
require the envelope to be recent (max_age_s). Without that check, an old but genuine
reply (e.g. yesterday's lower price) could be replayed and would still verify.
"""

from datetime import datetime, timedelta, timezone

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey

from aps.canonical import b64decode, b64encode, canonical
from aps.keys import verify_key_from_b64

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
# Tolerated clock difference between machines for envelopes stamped "in the future".
CLOCK_SKEW = timedelta(seconds=60)


def utc_now() -> str:
    """Current time as an ISO 8601 UTC timestamp, the format used in envelopes."""
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)


def parse_timestamp(text: str) -> datetime | None:
    """An envelope timestamp as an aware UTC datetime, or None if it is not in the APS format."""
    try:
        return datetime.strptime(text, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def is_fresh(timestamp: str, max_age_s: float, now: datetime | None = None) -> bool:
    """True if `timestamp` is at most max_age_s old and not ahead of `now` by more than CLOCK_SKEW."""
    stamped = parse_timestamp(timestamp)
    if stamped is None:
        return False
    now = now or datetime.now(timezone.utc)
    return now - timedelta(seconds=max_age_s) <= stamped <= now + CLOCK_SKEW


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
    """Wrap `payload` in an envelope signed by the node's key."""
    body = {"node_id": node_id, "timestamp": timestamp or utc_now(), "payload": payload}
    return {**body, "signature": sign_bytes(signing_key, body)}


def verify_envelope(envelope: dict, public_key: str, expected_node_id: str | None = None,
                    max_age_s: float | None = None, now: datetime | None = None) -> bool:
    """True if the envelope is well formed, from the expected node, and signed by public_key.

    With max_age_s, the envelope must also be fresh (see is_fresh). Leave it out for
    envelopes that are kept on purpose, like commitments redeemed later at booking;
    those carry their own "valid_until".
    """
    try:
        body = {k: envelope[k] for k in ("node_id", "timestamp", "payload")}
        signature = envelope["signature"]
    except (KeyError, TypeError):
        return False
    if expected_node_id is not None and body["node_id"] != expected_node_id:
        return False
    if max_age_s is not None and not is_fresh(body["timestamp"], max_age_s, now):
        return False
    return verify_bytes(public_key, body, signature)
