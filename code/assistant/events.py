"""Event bus feeding the "behind the scenes" timeline over Server-Sent Events.

Every event follows the UI event contract in documentation/formats.md. New
subscribers first get the history, so a reloaded page shows the whole run.

Events carry the id of the user turn they belong to (`turn`): the request that started the run
that emitted them (see `current_turn`), so the wallet attaches them to the right message.
"""

import asyncio
import json
import math
from contextvars import ContextVar

# The user turn being answered in this task. Set by the conversation for each request's run;
# tasks started inside it (tools, subagents) inherit it, so their events carry it too.
current_turn: ContextVar[str | None] = ContextVar("current_turn", default=None)


class EventBus:
    """Timeline events: kept as history and pushed to every connected browser."""

    def __init__(self):
        self.history: list[dict] = []
        self.subscribers: set[asyncio.Queue] = set()

    def emit(self, kind: str, status: str, summary: str, record: dict | None = None,
             seals: list[dict] | None = None, detail: dict | None = None, turn: str | None = None) -> dict:
        """Add a timeline step and send it to all subscribers; returns the event.

        `turn` defaults to the turn being answered in this task (`current_turn`), else None.
        """
        event = {
            "step": len(self.history) + 1,
            "turn": turn or current_turn.get(),
            "kind": kind,
            "node_id": record["node_id"] if record else None,
            "node_name": record["name"] if record else None,
            # Covered by the commercial register's seal; the UI only shows it inside a valid gold seal.
            "uid": record.get("uid") if record else None,
            "seals": seals or [],
            "status": status,
            "summary": summary,
            "detail": detail or {},
        }
        event = finite(event)  # NaN/Infinity are not JSON: the wallet would drop the frame, /history fail
        self.history.append(event)
        self._publish(("message", event))
        return event

    def reset(self) -> None:
        """Clear the history and tell the browsers to clear their timeline."""
        self.history.clear()
        self._publish(("reset", {}))

    def _publish(self, item: tuple[str, dict]) -> None:
        for queue in self.subscribers:
            queue.put_nowait(item)

    async def stream(self):
        """Yield SSE frames: the history, then live events. A "reset" event clears the UI."""
        queue: asyncio.Queue = asyncio.Queue()
        self.subscribers.add(queue)
        try:
            for event in list(self.history):
                yield sse("message", event)
            while True:
                try:
                    name, data = await asyncio.wait_for(queue.get(), timeout=15)
                    yield sse(name, data)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            self.subscribers.discard(queue)


def finite(value):
    """value with every NaN or Infinity (at any depth) replaced by None, so it is valid JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite(item) for item in value]
    return value


def sse(name: str, data: dict) -> str:
    """One Server-Sent Events frame (always valid JSON: NaN/Infinity become null)."""
    try:
        text = json.dumps(data, ensure_ascii=False, allow_nan=False)
    except ValueError:
        text = json.dumps(finite(data), ensure_ascii=False, allow_nan=False)
    return f"event: {name}\ndata: {text}\n\n"
