"""Signed tool calls: how an agent (Tuttie) asks a business's MCP tool to *act*.

Reading tools (availability, policies) need no signature from the caller: their answers are
signed by the business. An action (book, pay) is different: the business must know *who*
asks, that the user stands behind it, and that the request is not a recording of an earlier
one. So the caller signs the call itself:

    {
      "tool": "book",
      "args": {...},                     # the tool's arguments, exactly as the tool gets them
      "agent_id": "ch.tuttie.alex-muster",
      "nonce": "<32 hex chars>",         # random per call: a call is accepted only once
      "timestamp": "2026-10-31T12:00:00Z",
      "signature": "<agent key over canonical {tool, args, agent_id, nonce, timestamp}>",
      "delegation": {...}                # the user's signed delegation for this agent (aps/delegation.py)
    }

The delegation is attached, not signed again: the user's own signature already binds it to
this agent's id and key. The signature covers the tool name and the arguments, so a signed
`get_availability` call cannot be turned into a `book`, and an approval in the args cannot
be swapped. Freshness (timestamp within max_age_s) plus the nonce stop replays: an old call
fails the time window, a recent one has its nonce remembered (NonceBook).

What the call does *not* prove is whether the action is allowed: that is the gate's job
(aps/gate.py: seals, delegation scope, approval, agreement).
"""

import secrets
from datetime import datetime, timedelta, timezone

from nacl.signing import SigningKey

from aps.envelope import CLOCK_SKEW, is_fresh, sign_bytes, utc_now, verify_bytes

FIELDS = ("tool", "args", "agent_id", "nonce", "timestamp")
# Same window as live counters (negotiation/hotel.py): long enough for a slow LLM turn,
# short enough that the nonces to remember stay few.
CALL_MAX_AGE_S = 300


def call_body(call: dict) -> dict | None:
    """The signed part of a call, or None if a field is missing or has the wrong type."""
    try:
        body = {k: call[k] for k in FIELDS}
    except (KeyError, TypeError):
        return None
    if not isinstance(body["args"], dict) or not all(isinstance(body[k], str) for k in ("tool", "agent_id", "nonce")):
        return None
    return body


def sign_call(tool: str, args: dict, agent_id: str, signing_key: SigningKey, delegation: dict | None = None,
              nonce: str | None = None, timestamp: str | None = None) -> dict:
    """A call of `tool` with `args`, signed by the agent's key, with the user's delegation attached.

    `nonce` and `timestamp` are only passed in by tests; normally every call gets new ones.
    """
    body = {
        "tool": tool,
        "args": args,
        "agent_id": agent_id,
        "nonce": nonce or secrets.token_hex(16),
        "timestamp": timestamp or utc_now(),
    }
    call = {**body, "signature": sign_bytes(signing_key, body)}
    if delegation is not None:
        call["delegation"] = delegation
    return call


def verify_call(call: dict, public_key: str, tool: str | None = None, max_age_s: float = CALL_MAX_AGE_S,
                now: datetime | None = None) -> bool:
    """True if the call is well formed, signed by `public_key`, fresh and (if given) for `tool`.

    `public_key` must come from the caller's checked registry record, never from the call.
    This does not check the nonce: a NonceBook does that, after the signature verified.
    """
    body = call_body(call)
    if body is None or (tool is not None and body["tool"] != tool):
        return False
    if not is_fresh(body["timestamp"], max_age_s, now):
        return False
    return verify_bytes(public_key, body, call.get("signature", ""))


class NonceBook:
    """The nonces a service has accepted, so a recorded call cannot be played again.

    A nonce only has to be remembered while its call is still fresh: once the timestamp is
    outside the time window, verify_call refuses the call anyway. So the book forgets
    entries after max_age_s plus the clock skew and stays small. In memory, like the node's
    used approvals: a restarted node forgets them, but also refuses every call older than
    the window.
    """

    def __init__(self, max_age_s: float = CALL_MAX_AGE_S):
        self.keep = timedelta(seconds=max_age_s) + 2 * CLOCK_SKEW  # a call may be stamped up to CLOCK_SKEW ahead
        self.seen: dict[tuple[str, str], datetime] = {}

    def use(self, agent_id: str, nonce: str, now: datetime | None = None) -> bool:
        """Accept a nonce once: True the first time, False if this agent already used it."""
        now = now or datetime.now(timezone.utc)
        self.seen = {key: at for key, at in self.seen.items() if now - at <= self.keep}
        if (agent_id, nonce) in self.seen:
            return False
        self.seen[(agent_id, nonce)] = now
        return True
