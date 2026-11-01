"""A sliding one-minute rate limit per key (a session, a client address), kept in memory.

Every chat turn wakes the LLM and the hotels' agents, and a busy conversation is never
pushed out of the store; so turns are limited per session and per client address.
"""

import ipaddress
from collections import deque

TURNS_PER_SESSION_PER_MIN = 10  # a person types or speaks a few requests a minute at most
TURNS_PER_CLIENT_PER_MIN = 600  # the venue Wi-Fi shares one address with the presenter: generous
NEW_CHATS_PER_SESSION_PER_MIN = 10  # "new chat" presses per browser
NEW_CHATS_PER_CLIENT_PER_MIN = 120  # and per address (the venue Wi-Fi shares one)
MAX_KEYS = 5000  # above this, keys with nothing in the last minute are forgotten (amortised)


def address_key(host: str) -> str:
    """The throttle key of a client address: an IPv4 address as is, an IPv6 address by its /64.

    Every IPv6 user gets a whole /64 (2^64 addresses), so a per-address limit keyed by the full
    address would give one machine as many budgets as it likes.
    """
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.version == 6 and address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


class Throttle:
    """Counts events per key over the last minute and refuses one that would exceed a key's limit."""

    def __init__(self):
        self.recent: dict[object, deque] = {}  # key -> times of its events in the last minute
        self._sweep_above = MAX_KEYS  # sweep when there are more keys; doubles with live keys

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
        if len(self.recent) > self._sweep_above:  # amortised: the next sweep waits for twice the live keys
            for key in list(self.recent):
                self._count(key, now)
            self._sweep_above = max(MAX_KEYS, 2 * len(self.recent))
        return 0
