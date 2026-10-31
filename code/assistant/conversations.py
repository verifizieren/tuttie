"""One conversation per person using the app: their own Tuttie, timeline and approvals.

A browser is recognised by a session cookie (set by assistant/app.py). The hotels, the
marketplace and the registry stay shared, as on the real agent web; only what Tuttie knows,
shows and waits for belongs to one person. Conversations live in memory: a restart starts
everyone fresh, and the least recently used one is dropped when there are too many.
"""

import asyncio
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
        self.bus = EventBus()
        self.approvals = ApprovalBook()
        self.assistant = Assistant(llm, Toolbox(http, registry_url, self.bus, self.approvals), self.bus)
        self.chats: set[asyncio.Task] = set()

    def start(self, message: str) -> None:
        """Answer a message in the background; the answer arrives as an "answer" event."""
        task = asyncio.create_task(self._run(message))
        self.chats.add(task)
        task.add_done_callback(self.chats.discard)

    async def _run(self, message: str) -> None:
        try:
            await self.assistant.chat(message)
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

    def get(self, session_id: str) -> Conversation:
        """This session's conversation (new if unknown), marked as the most recently used."""
        if session_id not in self.by_session:
            self.by_session[session_id] = Conversation(self.http, self.registry_url, self.llm)
            while len(self.by_session) > MAX_CONVERSATIONS:
                _, oldest = self.by_session.popitem(last=False)
                oldest.reset()
        self.by_session.move_to_end(session_id)
        return self.by_session[session_id]
