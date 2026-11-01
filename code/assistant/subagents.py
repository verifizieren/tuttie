"""Tuttie's subagents: one per business, each with its own memory and only limited context.

Tuttie (the main agent) holds the user's full context. For work with one business, e.g. a
negotiation, it spawns a Subagent that gets only what that business may learn
(`Context.share("negotiation")`, never private items), keeps its own memory (a Session from
code/sessions) and opens a session with the business's agent, which keeps its own memory on
the other side. A SubagentPool runs many subagents in parallel, so Tuttie can talk to every
shortlisted hotel at once.

Every call to a business goes through Tuttie's trust gate (Toolbox.verified_post): broken or
unknown nodes are refused and every reply's signature is checked. The bargaining logic itself
(offers and counter-offers) is build step 4; for now a subagent can open a session, send
messages and read the replies.
"""

import asyncio

from assistant.tools import Toolbox, Verified
from sessions import Context, Session, SessionStore

SHARE_LEVEL = "negotiation"  # the most a business may learn from a subagent


class Subagent:
    """Works with one business for one task, remembering only its own conversation."""

    def __init__(self, toolbox: Toolbox, memory: Session, node_id: str):
        self.toolbox = toolbox
        self.memory = memory          # the subagent's own memory (Tuttie side)
        self.node_id = node_id
        self.remote_session: str | None = None  # the business's session id (its side of the memory)
        self.session_token: str = ""  # the business's secret for this session; only the opener has it

    @property
    def id(self) -> str:
        return self.memory.id

    async def open(self) -> dict:
        """Open a session with the business's agent, sharing only the subagent's context."""
        body = {"peer": f"tuttie/{self.id}", "purpose": self.memory.purpose, "context": self.memory.context}
        result = await self.toolbox.verified_post(self.node_id, "/agent/sessions", body, "a2a", "open session")
        if not isinstance(result, Verified):
            self.memory.add("system", "refused", result)
            return result
        payload = result.payload if isinstance(result.payload, dict) else {}
        session_id, agent = payload.get("session_id"), payload.get("agent")
        if not isinstance(session_id, str) or not session_id:
            # A signed but malformed reply: this hotel is skipped, the others go on bargaining.
            refused = {"error": "the business's agent sent no usable session"}
            self.memory.add("system", "refused", refused)
            return refused
        self.remote_session = session_id
        self.session_token = str(payload.get("session_token", ""))
        self.memory.add("system", "opened", {"node_id": self.node_id, "remote_session": self.remote_session})
        name = agent if isinstance(agent, str) and agent else "the business's agent"
        self.toolbox.emit_verified("a2a", f"Subagent opened a session with {name[:60]}", result)
        return payload

    async def send(self, message: str) -> dict:
        """Send a message in the session and remember both sides of the turn."""
        if self.remote_session is None:
            return {"error": "session is not open"}
        path = f"/agent/sessions/{self.remote_session}/messages"
        result = await self.toolbox.verified_post(self.node_id, path, {"message": message}, "a2a", "session message",
                                                  headers=self.token_header())
        self.memory.add("self", "message", {"text": message})
        if not isinstance(result, Verified):
            self.memory.add("system", "refused", result)
            return result
        self.memory.add("peer", "reply", result.payload)
        self.toolbox.emit_verified("a2a", f"Q: {message}  A: {result.payload.get('answer', '')}", result)
        return result.payload

    def token_header(self) -> dict:
        """The header that proves to the business that this subagent opened the session."""
        return {"X-Session-Token": self.session_token}

    async def close(self) -> None:
        """Close the business's session (frees its slot there); see SubagentPool.close.

        Never raises: a business that does not answer the close frees the slot itself later.
        """
        if self.remote_session is not None:
            path = f"/agent/sessions/{self.remote_session}/close"
            try:
                await self.toolbox.verified_post(self.node_id, path, {}, "a2a", "close session",
                                                 headers=self.token_header())
            except Exception:  # noqa: BLE001 - closing is best effort
                pass
            self.remote_session = None


class SubagentPool:
    """Spawns Tuttie's subagents and runs them in parallel."""

    def __init__(self, toolbox: Toolbox, owner: str = "tuttie"):
        self.toolbox = toolbox
        self.memories = SessionStore(owner=owner)  # one memory per subagent
        self.subagents: dict[str, Subagent] = {}

    def spawn(self, node_id: str, task: str, context: Context) -> Subagent:
        """A new subagent for one business; it only receives the context that business may see."""
        memory = self.memories.open(peer=node_id, purpose=task, context=context.share(SHARE_LEVEL))
        subagent = Subagent(self.toolbox, memory, node_id)
        self.subagents = {sid: s for sid, s in self.subagents.items() if sid in self.memories.sessions}  # freed
        self.subagents[subagent.id] = subagent
        return subagent

    async def close(self, subagent: Subagent) -> None:
        """The subagent is done: close its session with the business and its own memory
        (which stays readable until newer closed memories push it out)."""
        await subagent.close()
        if subagent.id in self.memories.sessions and subagent.memory.status == "open":
            self.memories.close(subagent.id)

    async def open_all(self, subagents: list[Subagent]) -> list[dict]:
        """Open all their sessions at once."""
        return await asyncio.gather(*(s.open() for s in subagents))

    async def send_all(self, subagents: list[Subagent], message: str) -> list[dict]:
        """Send the same message through every subagent at once; replies in the same order."""
        return await asyncio.gather(*(s.send(message) for s in subagents))
