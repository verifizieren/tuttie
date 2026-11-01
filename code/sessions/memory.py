"""Sessions: one isolated conversation between two agents, with its own memory.

A session is opened for one purpose (e.g. a negotiation about one posting) between its owner
(the agent that keeps it) and a peer (the agent on the other side). Its memory is the ordered
list of turns; `state` holds anything the owner tracks while it runs (e.g. the round or the
last offer). Every agent keeps its own sessions in a SessionStore, so many conversations run
in parallel without mixing: a hotel can bargain with five guests at once, and Tuttie can run
one subagent per hotel. Turns within one session are serialised with the session's lock.

Memory lives in the agent's process for now (lost on restart), and it is bounded: a session
takes at most MAX_TURNS turns, a store keeps at most `max_open` open sessions (when full, the
least recently used idle one is closed to make room) and only the `keep_closed` most recent
closed ones (older closed sessions are freed).
"""

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


MAX_TURNS = 100  # per session: a negotiation needs a handful, a flood is refused


@dataclass
class Turn:
    """One entry in a session's memory."""

    author: str   # "self" (the owner), "peer", or "system"
    kind: str     # e.g. "message", "reply", "note", later "offer" / "counter"
    content: dict
    at: str = field(default_factory=_now)


@dataclass
class Session:
    """One conversation with its memory. Create it through SessionStore.open()."""

    id: str
    owner: str
    peer: str
    purpose: str
    context: dict = field(default_factory=dict)  # what the peer shared when opening
    turns: list[Turn] = field(default_factory=list)
    state: dict = field(default_factory=dict)
    status: str = "open"
    created_at: str = field(default_factory=_now)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    token: str = field(default="", repr=False)  # the opener's secret for later calls (never in to_dict)
    used_at: float = field(default_factory=time.monotonic, repr=False)  # last turn, for eviction
    max_turns: int = MAX_TURNS

    def add(self, author: str, kind: str, content: dict) -> Turn:
        """Append a turn to the memory; a closed or full session takes no more turns."""
        if self.status != "open":
            raise SessionClosed(self.id)
        if len(self.turns) >= self.max_turns:
            raise SessionFull(self.id)
        turn = Turn(author, kind, content)
        self.turns.append(turn)
        self.used_at = time.monotonic()
        return turn

    def transcript(self, last: int = 20) -> list[dict]:
        """The most recent turns, compact enough to put into a prompt."""
        return [{"author": t.author, "kind": t.kind, **t.content} for t in self.turns[-last:]]

    def to_dict(self) -> dict:
        """The whole session as plain data, e.g. for an audit view or a signed export."""
        return {
            "session_id": self.id, "owner": self.owner, "peer": self.peer, "purpose": self.purpose,
            "status": self.status, "created_at": self.created_at, "context": self.context,
            "state": self.state, "turns": [t.__dict__ for t in self.turns],
        }


class SessionClosed(Exception):
    """A turn was added to a session that is already closed."""


class SessionFull(SessionClosed):
    """A turn was added to a session that already holds MAX_TURNS turns."""


class StoreFull(Exception):
    """Every open session is busy right now: no room for a new one (answer 429, try later)."""


class SessionStore:
    """All sessions of one agent, by id (insertion order = oldest first)."""

    def __init__(self, owner: str, max_open: int = 200, keep_closed: int = 50):
        self.owner = owner
        self.max_open = max_open
        self.keep_closed = keep_closed
        self.sessions: dict[str, Session] = {}

    def open(self, peer: str, purpose: str, context: dict | None = None) -> Session:
        """Start a new isolated session with `peer`.

        When `max_open` sessions are open, the least recently used one that is not answering
        right now is closed to make room; if all are busy, StoreFull is raised.
        """
        open_now = self.open_sessions()
        if len(open_now) >= self.max_open:
            idle = [s for s in open_now if not s.lock.locked()]
            if not idle:
                raise StoreFull(f"{self.owner} has too many busy sessions")
            self.close(min(idle, key=lambda s: s.used_at).id)
        session = Session(id="se-" + secrets.token_hex(16), owner=self.owner, peer=peer,
                          purpose=purpose, context=dict(context or {}), token=secrets.token_urlsafe(32))
        self.sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session:
        """The session with this id; raises KeyError if there is none."""
        return self.sessions[session_id]

    def close(self, session_id: str) -> Session:
        """Close a session; its memory stays readable while it is among the `keep_closed` most
        recently closed (older closed sessions are freed)."""
        session = self.sessions.pop(session_id)
        session.status = "closed"
        self.sessions[session_id] = session  # move to the end: most recently closed
        closed = [s.id for s in self.sessions.values() if s.status != "open"]
        for old in closed[:max(0, len(closed) - self.keep_closed)]:
            del self.sessions[old]
        return session

    def open_sessions(self) -> list[Session]:
        """Sessions that still take turns."""
        return [s for s in self.sessions.values() if s.status == "open"]
