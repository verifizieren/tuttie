"""Event bus feeding the "behind the scenes" timeline over Server-Sent Events.

Every event follows the UI event contract in documentation/formats.md. New
subscribers first get the history, so a reloaded page shows the whole run.
"""

import asyncio
import json


class EventBus:
    """Timeline events: kept as history and pushed to every connected browser."""

    def __init__(self):
        self.history: list[dict] = []
        self.subscribers: set[asyncio.Queue] = set()

    def emit(self, kind: str, status: str, summary: str, record: dict | None = None,
             seals: list[dict] | None = None, detail: dict | None = None) -> dict:
        """Add a timeline step and send it to all subscribers; returns the event."""
        event = {
            "step": len(self.history) + 1,
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


def sse(name: str, data: dict) -> str:
    """One Server-Sent Events frame."""
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
