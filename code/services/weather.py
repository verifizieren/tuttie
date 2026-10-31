"""Weather for a place and day, from Open-Meteo (free, no key): what the weather service signs.

`forecast(http, place, date)` finds the place (Open-Meteo geocoding, Switzerland first) and
returns one day: min / max temperature, the chance of rain, wind, a short description and the
evening and night hours (what a late arrival needs). Open-Meteo forecasts 16 days ahead; a
date further out or in the past is refused with a reason instead of guessed.

Without the internet (a venue's Wi-Fi), `sample_forecast` gives a clearly marked sample, so
the demo still runs; `source` says which one it is, and Tuttie passes that on.
"""

import re
from datetime import date as Date, timedelta

import httpx

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "open-meteo.com"
SAMPLE_SOURCE = "sample data (weather service offline)"
MAX_DAYS_AHEAD = 15
EVENING_HOURS = (18, 20, 22)  # and 0, 2 of the next day: when a late guest is on the way
PLACE = re.compile(r"^[\w .,'()-]{2,60}$")

# WMO weather codes (Open-Meteo's "weather_code") in words.
WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
    82: "heavy showers", 85: "snow showers", 86: "heavy snow showers", 95: "thunderstorm",
    96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


class WeatherUnavailable(Exception):
    """The forecast cannot be given; the message says why (safe to send back)."""


def check_request(place: str, day: str, today: Date) -> Date:
    """The requested day, if the place and date can be forecast; raises WeatherUnavailable otherwise."""
    if not isinstance(place, str) or not PLACE.match(place.strip()):
        raise WeatherUnavailable("place must be a place name, e.g. Basel")
    try:
        wanted = Date.fromisoformat(day)
    except (TypeError, ValueError):
        raise WeatherUnavailable("date must be YYYY-MM-DD") from None
    if not today <= wanted <= today + timedelta(days=MAX_DAYS_AHEAD):
        raise WeatherUnavailable(f"forecasts cover today until {today + timedelta(days=MAX_DAYS_AHEAD)}")
    return wanted


def describe(code: int | None) -> str:
    """A WMO weather code in words."""
    return WMO.get(code, "unknown")


async def locate(http: httpx.AsyncClient, place: str) -> dict:
    """The place's coordinates: a Swiss match first, else the best match anywhere."""
    response = await http.get(GEOCODE_URL, params={"name": place.strip(), "count": 5, "language": "en"})
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        raise WeatherUnavailable(f"no place called {place!r} found")
    best = next((r for r in results if r.get("country_code") == "CH"), results[0])
    return {"name": best["name"], "country": best.get("country_code"), "latitude": best["latitude"],
            "longitude": best["longitude"]}


async def forecast(http: httpx.AsyncClient, place: str, day: str, today: Date | None = None) -> dict:
    """One day's forecast for `place` (raises WeatherUnavailable or httpx.HTTPError)."""
    wanted = check_request(place, day, today or Date.today())
    where = await locate(http, place)
    params = {
        "latitude": where["latitude"], "longitude": where["longitude"], "timezone": "Europe/Zurich",
        "start_date": wanted.isoformat(), "end_date": (wanted + timedelta(days=1)).isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code,wind_speed_10m_max",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
    }
    response = await http.get(FORECAST_URL, params=params)
    response.raise_for_status()
    data = response.json()
    daily, hourly = data["daily"], data["hourly"]
    night = []
    for index, stamp in enumerate(hourly["time"]):
        day_part, hour = stamp[:10], int(stamp[11:13])
        if (day_part == wanted.isoformat() and hour in EVENING_HOURS) or (day_part > wanted.isoformat() and hour in (0, 2)):
            night.append({"time": stamp, "temperature_c": hourly["temperature_2m"][index],
                          "rain_chance_pct": hourly["precipitation_probability"][index],
                          "sky": describe(hourly["weather_code"][index])})
    return {
        "place": where["name"], "country": where["country"], "date": wanted.isoformat(),
        "sky": describe(daily["weather_code"][0]),
        "temperature_min_c": daily["temperature_2m_min"][0], "temperature_max_c": daily["temperature_2m_max"][0],
        "rain_chance_pct": daily["precipitation_probability_max"][0], "wind_max_kmh": daily["wind_speed_10m_max"][0],
        "evening_and_night": night, "source": SOURCE,
    }


def sample_forecast(place: str, day: str) -> dict:
    """A marked sample when Open-Meteo cannot be reached: plausible November values for Basel."""
    hours = [(f"{day}T{h:02d}:00", t, r) for h, t, r in ((18, 7.5, 10), (20, 6.8, 10), (22, 6.1, 15))]
    return {
        "place": place.strip(), "country": "CH", "date": day, "sky": "partly cloudy",
        "temperature_min_c": 4.0, "temperature_max_c": 11.0, "rain_chance_pct": 15, "wind_max_kmh": 12.0,
        "evening_and_night": [{"time": t, "temperature_c": c, "rain_chance_pct": r, "sky": "partly cloudy"}
                              for t, c, r in hours],
        "source": SAMPLE_SOURCE,
    }
