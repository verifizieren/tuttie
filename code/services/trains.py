"""Train connections in Switzerland, from transport.opendata.ch (free, no key): what the
timetable service signs.

`connections(http, origin, destination, date, time, arrive_by)` returns the next few
connections: departure and arrival time and platform, duration, changes and the trains
(e.g. IC 1, IR 36). With `arrive_by` the time is the latest arrival instead of the earliest
departure (for "I must be in Basel by midnight").

Without the internet, `sample_connections` gives a clearly marked sample (`source`), so the
demo still runs.
"""

import re
from datetime import date as Date, datetime, timedelta

import httpx

CONNECTIONS_URL = "https://transport.opendata.ch/v1/connections"
SOURCE = "transport.opendata.ch"
SAMPLE_SOURCE = "sample data (timetable service offline)"
MAX_CONNECTIONS = 4
STATION = re.compile(r"^[\w .,'()/-]{2,60}$")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class TrainsUnavailable(Exception):
    """No connections can be given; the message says why (safe to send back)."""


def check_request(origin: str, destination: str, day: str, time: str) -> None:
    """Raise TrainsUnavailable unless the stations, date and time are well formed."""
    for name, value in (("from", origin), ("to", destination)):
        if not isinstance(value, str) or not STATION.match(value.strip()):
            raise TrainsUnavailable(f"{name} must be a station or place name, e.g. Zürich HB")
    try:
        Date.fromisoformat(day)
    except (TypeError, ValueError):
        raise TrainsUnavailable("date must be YYYY-MM-DD") from None
    if not isinstance(time, str) or not TIME.match(time):
        raise TrainsUnavailable("time must be HH:MM (24 h)")


def clock(stamp: str | None) -> str | None:
    """"2026-11-13T22:32:00+0100" → "22:32" (the timetable's local time)."""
    return stamp[11:16] if stamp else None


def minutes(duration: str | None) -> int | None:
    """"00d01:04:00" → 64."""
    match = re.match(r"(\d+)d(\d+):(\d+)", duration or "")
    return int(match[1]) * 1440 + int(match[2]) * 60 + int(match[3]) if match else None


def trains(sections: list[dict]) -> list[str]:
    """The trains of a connection, e.g. ["IC 1", "IC 6"]; walks are left out."""
    names = []
    for section in sections:
        journey = section.get("journey") or {}
        if journey.get("category"):
            names.append(f"{journey['category']} {journey.get('number') or ''}".strip())
    return names


async def connections(http: httpx.AsyncClient, origin: str, destination: str, day: str, time: str,
                      arrive_by: bool = False) -> dict:
    """The next connections (raises TrainsUnavailable or httpx.HTTPError)."""
    check_request(origin, destination, day, time)
    params = {"from": origin.strip(), "to": destination.strip(), "date": day, "time": time,
              "isArrivalTime": int(arrive_by), "limit": MAX_CONNECTIONS}
    response = await http.get(CONNECTIONS_URL, params=params)
    response.raise_for_status()
    data = response.json()
    found = data.get("connections") or []
    if not found:
        raise TrainsUnavailable(f"no connection from {origin} to {destination} found")
    return {
        "from": data.get("from", {}).get("name") or origin, "to": data.get("to", {}).get("name") or destination,
        "date": day, "time": time, "arrive_by": arrive_by,
        "connections": [{
            "departure": clock(c["from"].get("departure")), "departure_platform": c["from"].get("platform"),
            "arrival": clock(c["to"].get("arrival")), "arrival_platform": c["to"].get("platform"),
            "arrival_date": (c["to"].get("arrival") or "")[:10] or None,
            "duration_min": minutes(c.get("duration")), "changes": c.get("transfers"),
            "trains": trains(c.get("sections") or []),
        } for c in found[:MAX_CONNECTIONS]],
        "source": SOURCE,
    }


def sample_connections(origin: str, destination: str, day: str, time: str, arrive_by: bool = False) -> dict:
    """A marked sample when the timetable cannot be reached: hourly trains, about an hour each."""
    start = datetime.fromisoformat(f"{day}T{time}") - (timedelta(hours=1, minutes=4) if arrive_by else timedelta())
    rows = []
    for n in range(3):
        leave = start + timedelta(minutes=2 + 30 * n)
        arrive = leave + timedelta(minutes=64)
        rows.append({"departure": leave.strftime("%H:%M"), "departure_platform": None, "arrival": arrive.strftime("%H:%M"),
                     "arrival_platform": None, "arrival_date": arrive.date().isoformat(), "duration_min": 64,
                     "changes": 0 if n % 2 == 0 else 1, "trains": ["IC"] if n % 2 == 0 else ["IR", "IC"]})
    return {"from": origin.strip(), "to": destination.strip(), "date": day, "time": time, "arrive_by": arrive_by,
            "connections": rows, "source": SAMPLE_SOURCE}
