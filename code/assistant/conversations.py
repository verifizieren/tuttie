"""One conversation per person using the app: their own Tuttie, timeline and approvals.

A browser is recognised by a session cookie (set by assistant/app.py). The hotels, the
marketplace and the registry stay shared, as on the real agent web; only what Tuttie knows,
shows and waits for belongs to one person. Conversations live in memory: a restart starts
everyone fresh. When there are too many, empty ones go first (a request without a cookie
makes one); chats with history go only above twice the limit, those with the fewest turns first.
Saved chats are bounded per browser, and globally the browser with the most gives one up.
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import secrets
from collections import Counter, OrderedDict

import httpx

from assistant.agent import Assistant
from assistant.approvals import ApprovalBook
from assistant.events import EventBus, current_turn
from assistant.tools import Toolbox
from llm import LLM

MAX_CONVERSATIONS = 200  # active ones; chats with history are dropped only above twice this
SAVED_PER_SESSION = 20  # "new chat" keeps the previous one; a browser keeps at most this many
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
        # Sessions whose conversation was dropped: their next one needs a new first id (bounded).
        self._generations: OrderedDict[str, int] = OrderedDict()
        self._dropped = 0
        self._identity: Toolbox | None = None

    def first_id(self, session_id: str) -> str:
        """The id this session's first conversation gets, known before the conversation exists.

        The wallet reads it from GET /history and sends it back when it acts, so a read
        does not have to create (and store) a conversation. After this session's conversation was
        dropped, the next one gets a different id, so a late message for the old one is refused.
        """
        generation = self._generations.get(session_id, 0)
        message = f"{session_id}#{generation}" if generation else session_id
        digest = hmac.new(self._secret, message.encode(), hashlib.sha256).digest()
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
        """Keep a chat for resuming: at most SAVED_PER_SESSION per browser (its own oldest goes),
        and MAX_CONVERSATIONS in all (the oldest of the browser that saved the most goes), so one
        browser pressing "new chat" again and again can never push out anyone else's saved chats."""
        self.saved[(session_id, conv.id)] = conv
        mine = [key for key in self.saved if key[0] == session_id]
        for key in mine[:max(0, len(mine) - SAVED_PER_SESSION)]:
            self.saved.pop(key).reset()
        while len(self.saved) > MAX_CONVERSATIONS:
            greediest = Counter(key[0] for key in self.saved).most_common(1)[0][0]
            self.saved.pop(next(key for key in self.saved if key[0] == greediest)).reset()

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
                self._drop(owner)
        self.by_session.move_to_end(session_id)
        return self.by_session[session_id]

    def _drop(self, session_id: str) -> None:
        """Forget a session's conversation and saved chats; its next conversation gets a new id."""
        conv = self.by_session.pop(session_id)
        saved = [key for key in self.saved if key[0] == session_id]
        if conv.bus.history or conv.turns or saved or conv.id != self.first_id(session_id):
            self._dropped += 1
            self._generations[session_id] = self._dropped
            self._generations.move_to_end(session_id)
            while len(self._generations) > 10 * MAX_CONVERSATIONS:
                self._generations.popitem(last=False)
        conv.reset()
        for key in saved:
            self.saved.pop(key).reset()

    def _evictable(self, keep: str) -> str | None:
        """The session to drop, or None: never a running chat or a pending approval.

        Every request without a cookie (a crawler, a link preview, curl) makes a new, empty
        conversation; the least recently used empty one goes first. A chat with history goes
        only above twice MAX_CONVERSATIONS (so a burst of new chats cannot push out a person
        who is reading their offers): the one with the fewest turns, then the least recently used.
        The store may exceed the limits for a while.
        """
        idle = [sid for sid, conv in self.by_session.items()
                if sid != keep and not conv.chats and not conv.approvals.pending]
        empty = [sid for sid in idle if not self.by_session[sid].bus.history]
        if empty:
            return empty[0]
        if len(self.by_session) <= 2 * MAX_CONVERSATIONS or not idle:
            return None
        order = {sid: n for n, sid in enumerate(self.by_session)}
        return min(idle, key=lambda sid: (self.by_session[sid].turns, order[sid]))
