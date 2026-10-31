"""One conversation per person using the app: their own Tuttie, timeline and approvals.

A browser is recognised by a session cookie (set by assistant/app.py). The hotels, the
marketplace and the registry stay shared, as on the real agent web; only what Tuttie knows,
shows and waits for belongs to one person. Conversations live in memory: a restart starts
everyone fresh, and the least recently used one is dropped when there are too many.
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import secrets
from collections import OrderedDict

import httpx

from assistant.agent import Assistant
from assistant.approvals import ApprovalBook
from assistant.events import EventBus, current_turn
from assistant.tools import Toolbox
from llm import LLM

MAX_CONVERSATIONS = 200
log = logging.getLogger(__name__)


class Conversation:
    """Everything one person's Tuttie has: the assistant, its timeline, approvals and running chats."""

    def __init__(self, http: httpx.AsyncClient, registry_url: str, llm: LLM, conversation_id: str | None = None):
        self.id = conversation_id or secrets.token_urlsafe(16)
        self.bus = EventBus()
        self.approvals = ApprovalBook()
        self.assistant = Assistant(llm, Toolbox(http, registry_url, self.bus, self.approvals), self.bus)
        self.chats: set[asyncio.Task] = set()
        self.turns = 0  # user turns so far; their ids stay unique for the conversation's lifetime

    def start(self, message: str, first_tool: str | None = None, said: str | None = None,
              source: str = "text") -> str:
        """Answer a message in the background as a new turn; returns the turn's id.

        A "turn" event opens the turn at once (`detail`: turn_id, said, source text | voice),
        so the wallet shows it even while an earlier request is still running. Every event of
        this request's run carries the id, the answer included. `said` is what the user sees as
        their message (default: the message itself).
        """
        self.turns += 1
        turn_id = f"t{self.turns}"
        self.bus.emit("turn", "pending", said or message, turn=turn_id,
                      detail={"turn_id": turn_id, "said": said or message, "source": source})
        task = asyncio.create_task(self._run(message, first_tool, turn_id))
        self.chats.add(task)
        task.add_done_callback(self.chats.discard)
        return turn_id

    async def _run(self, message: str, first_tool: str | None, turn_id: str) -> None:
        current_turn.set(turn_id)  # this task's own context: every event it emits belongs to the turn
        try:
            await self.assistant.chat(message, first_tool)
        except asyncio.CancelledError:
            raise
        except Exception:  # surface any failure on screen instead of hanging the wallet; details only in the log
            log.exception("chat failed")
            self.bus.emit("answer", "broken", "I can't think right now, please try again in a moment.",
                          detail={"mood": "sorry"})

    def reset(self) -> None:
        """Start over: stop running chats, decline open approvals, clear the timeline."""
        for task in list(self.chats):
            task.cancel()
        self.approvals.clear()
        self.assistant.reset()
        self.bus.reset()


class Conversations:
    """The conversations by session id, creating one when its browser first acts.

    Reading (find, first_id) never creates anything, so requests that only look (a crawler,
    a link preview, a scanned QR code without cookies) cannot push out anyone's chat.
    """

    def __init__(self, http: httpx.AsyncClient, registry_url: str, llm: LLM | None = None):
        self.http = http
        self.registry_url = registry_url
        self.llm = llm or LLM()
        self.by_session: OrderedDict[str, Conversation] = OrderedDict()
        self.saved: OrderedDict[tuple[str, str], Conversation] = OrderedDict()
        self._secret = secrets.token_bytes(32)  # for first ids; conversations end with the process anyway
        self._identity: Toolbox | None = None

    def first_id(self, session_id: str) -> str:
        """The id this session's first conversation gets, known before the conversation exists.

        The wallet reads it from GET /history and sends it back when it acts, so a read
        does not have to create (and store) a conversation.
        """
        digest = hmac.new(self._secret, session_id.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest[:16]).decode().rstrip("=")

    def find(self, session_id: str) -> Conversation | None:
        """This session's conversation (marked as the most recently used), or None. Never creates."""
        if session_id not in self.by_session:
            return None
        self.by_session.move_to_end(session_id)
        return self.by_session[session_id]

    def identity_toolbox(self) -> Toolbox:
        """A toolbox for checks that need no conversation (Tuttie's identity); it emits nothing."""
        if self._identity is None:
            self._identity = Toolbox(self.http, self.registry_url, EventBus(), ApprovalBook())
        return self._identity

    def _save(self, session_id: str, conv: Conversation) -> None:
        self.saved[(session_id, conv.id)] = conv
        while len(self.saved) > MAX_CONVERSATIONS:
            _, oldest = self.saved.popitem(last=False)
            oldest.reset()

    def switch(self, session_id: str, conversation_id: str | None = None) -> Conversation:
        """Start or resume a chat without discarding its signed offers and agreements.

        Saved conversations are owned by the browser session, bounded, and in memory.
        A missing id must fail rather than silently booking from an unrelated chat.
        """
        current = self.get(session_id)
        if conversation_id == current.id:
            return current
        if current.chats or current.approvals.pending:
            raise RuntimeError("Finish the current request or approval before switching conversations")
        if conversation_id is None:
            target = Conversation(self.http, self.registry_url, self.llm)
        else:
            target = self.saved.pop((session_id, conversation_id))
        self._save(session_id, current)
        self.by_session[session_id] = target
        return target

    def active(self, session_id: str, conversation_id: str) -> Conversation:
        """A voice room must never send a late utterance into a different conversation."""
        conv = self.find(session_id)
        if conv is None or conv.id != conversation_id:
            raise KeyError(conversation_id)
        return conv

    def get(self, session_id: str) -> Conversation:
        """This session's conversation (new if unknown), marked as the most recently used."""
        if session_id not in self.by_session:
            self.by_session[session_id] = Conversation(self.http, self.registry_url, self.llm,
                                                       self.first_id(session_id))
            while len(self.by_session) > MAX_CONVERSATIONS and (owner := self._evictable(session_id)):
                self.by_session.pop(owner).reset()
                for key in [k for k in self.saved if k[0] == owner]:
                    self.saved.pop(key).reset()
        self.by_session.move_to_end(session_id)
        return self.by_session[session_id]

    def _evictable(self, keep: str) -> str | None:
        """The session to drop: the least recently used empty one, else the least recently used idle one.

        Every request without a cookie (a crawler, a link preview, curl) makes a new, empty
        conversation; dropping those first keeps people's chats, and a running chat or a pending
        approval is never dropped (the store may then exceed MAX_CONVERSATIONS for a while).
        """
        idle = [sid for sid, conv in self.by_session.items()
                if sid != keep and not conv.chats and not conv.approvals.pending]
        return next((sid for sid in idle if not self.by_session[sid].bus.history), idle[0] if idle else None)
