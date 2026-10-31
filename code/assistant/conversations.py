"""One conversation per person using the app: their own Tuttie, timeline and approvals.

A browser is recognised by a session cookie (set by assistant/app.py). The hotels, the
marketplace and the registry stay shared, as on the real agent web; only what Tuttie knows,
shows and waits for belongs to one person. Conversations live in memory: a restart starts
everyone fresh, and the least recently used one is dropped when there are too many.
"""

import asyncio
import secrets
from collections import OrderedDict

import httpx

from assistant.agent import Assistant
from assistant.approvals import ApprovalBook
from assistant.events import EventBus
from assistant.tools import Toolbox
from llm import LLM

MAX_CONVERSATIONS = 200


class Conversation:
    """Everything one person's Tuttie has: the assistant, its timeline, approvals and running chats."""

    def __init__(self, http: httpx.AsyncClient, registry_url: str, llm: LLM):
        self.id = secrets.token_urlsafe(16)
        self.bus = EventBus()
        self.approvals = ApprovalBook()
        self.assistant = Assistant(llm, Toolbox(http, registry_url, self.bus, self.approvals), self.bus)
        self.chats: set[asyncio.Task] = set()

    def start(self, message: str, first_tool: str | None = None) -> None:
        """Answer a message in the background; the answer arrives as an "answer" event."""
        task = asyncio.create_task(self._run(message, first_tool))
        self.chats.add(task)
        task.add_done_callback(self.chats.discard)

    async def _run(self, message: str, first_tool: str | None) -> None:
        try:
            await self.assistant.chat(message, first_tool)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # surface any failure on screen instead of hanging the wallet
            self.bus.emit("answer", "broken", f"Sorry, something went wrong: {type(error).__name__}",
                          detail={"mood": "sorry"})

    def reset(self) -> None:
        """Start over: stop running chats, decline open approvals, clear the timeline."""
        for task in list(self.chats):
            task.cancel()
        self.approvals.clear()
        self.assistant.reset()
        self.bus.reset()


class Conversations:
    """The conversations by session id, creating one on first use."""

    def __init__(self, http: httpx.AsyncClient, registry_url: str, llm: LLM | None = None):
        self.http = http
        self.registry_url = registry_url
        self.llm = llm or LLM()
        self.by_session: OrderedDict[str, Conversation] = OrderedDict()
        self.saved: OrderedDict[tuple[str, str], Conversation] = OrderedDict()

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
        conv = self.get(session_id)
        if conv.id != conversation_id:
            raise KeyError(conversation_id)
        return conv

    def get(self, session_id: str) -> Conversation:
        """This session's conversation (new if unknown), marked as the most recently used."""
        if session_id not in self.by_session:
            self.by_session[session_id] = Conversation(self.http, self.registry_url, self.llm)
            while len(self.by_session) > MAX_CONVERSATIONS:
                owner, oldest = self.by_session.popitem(last=False)
                oldest.reset()
                for key in [k for k in self.saved if k[0] == owner]:
                    self.saved.pop(key).reset()
        self.by_session.move_to_end(session_id)
        return self.by_session[session_id]
