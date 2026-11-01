"""A sliding one-minute rate limit per key (a session, a client address), kept in memory.

Every chat turn wakes the LLM and the hotels' agents, and a busy conversation is never
pushed out of the store; so turns are limited per session and per client address.
"""

from collections import deque

TURNS_PER_SESSION_PER_MIN = 10  # a person types or speaks a few requests a minute at most
TURNS_PER_CLIENT_PER_MIN = 600  # the venue Wi-Fi shares one address with the presenter: generous
MAX_KEYS = 5000  # above this, keys with nothing in the last minute are forgotten


class Throttle:
    """Counts events per key over the last minute and refuses one that would exceed a key's limit."""

    def __init__(self):
        self.recent: dict[object, deque] = {}  # key -> times of its events in the last minute

    def _count(self, key, now: float) -> int:
        """Events for `key` in the last minute; a key with none is forgotten."""
        times = self.recent.get(key)
        if times is None:
            return 0
        while times and now - times[0] > 60:
            times.popleft()
        if not times:
            del self.recent[key]
        return len(times)

    def wait(self, limits: dict[object, int], now: float) -> int:
        """0 after counting one event for every key; else, counting nothing, the seconds until the
        keys at their limit have room again (for a Retry-After header)."""
        full = [key for key, limit in limits.items() if self._count(key, now) >= limit]
        if full:
            frees_at = max(self.recent[key][-limits[key]] for key in full) + 60
            return max(1, int(frees_at - now) + 1)
        for key in limits:
            self.recent.setdefault(key, deque()).append(now)
        if len(self.recent) > MAX_KEYS:
            for key in list(self.recent):
                self._count(key, now)
        return 0
