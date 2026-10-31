"""Context that agents pass to each other, classified by who may see it.

Every piece of information an agent holds has a visibility:

    public       may go into a marketplace posting, anyone may see it
    negotiation  may be shared with the one business an agent is talking to
    private      never leaves the agent that holds it (e.g. the real budget limit)

Unclassified information is private. When an agent hands context to another agent (Tuttie to
one of its subagents, a subagent to a hotel's agent), it calls `share()` with the highest
level the receiver may see; private items can never be shared.
"""

from dataclasses import dataclass

LEVELS = {"public": 0, "negotiation": 1, "private": 2}


@dataclass(frozen=True)
class ContextItem:
    """One piece of information and who may see it."""

    key: str
    value: object
    visibility: str = "private"

    def __post_init__(self):
        if self.visibility not in LEVELS:
            raise ValueError(f"visibility must be one of {list(LEVELS)}, not {self.visibility!r}")


class Context:
    """The information an agent holds, each item with its visibility."""

    def __init__(self, items: list[ContextItem] | None = None):
        self.items: dict[str, ContextItem] = {item.key: item for item in items or []}

    def add(self, key: str, value: object, visibility: str = "private") -> "Context":
        """Add or replace an item; returns self so calls can be chained."""
        self.items[key] = ContextItem(key, value, visibility)
        return self

    def share(self, up_to: str = "public") -> dict:
        """The items another agent may see, as {key: value}. Private items never leave."""
        if up_to == "private":
            raise ValueError("private context is never shared")
        limit = LEVELS[up_to]
        return {key: item.value for key, item in self.items.items() if LEVELS[item.visibility] <= limit}

    def private_keys(self) -> set[str]:
        """Keys that must never appear in anything this agent sends."""
        return {key for key, item in self.items.items() if item.visibility == "private"}
