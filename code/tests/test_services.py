"""Weather and train services (services/): live data parsed, refusals, the offline sample, MCP,
and Tuttie checking their signed answers through its trust gate.

The data sources are mocked with answers recorded from Open-Meteo and transport.opendata.ch
(no network); signatures use the real demo keys and registry.
"""

import asyncio
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from mcp import Client

from aps import verify_envelope
from aps.keys import load_public_key
from assistant.approvals import ApprovalBook
from assistant.events import EventBus
from assistant.tools import READ_TOOLS, Toolbox, Verified
from mcp_helpers import in_process_link
from registry.app import app as registry_app
from services import trains, weather
from services.server import create_app

DATA = Path(__file__).resolve().parent.parent / "data"
CONFIGS = {json.loads(p.read_text())["service"]: json.loads(p.read_text()) for p in (DATA / "services").glob("*.json")}
WEATHER, TRAINS = CONFIGS["weather"], CONFIGS["trains"]
TODAY = date.today()
DAY = TODAY.isoformat()

GEOCODE = {"results": [{"name": "Basel", "latitude": 47.558, "longitude": 7.573, "country_code": "CH"}]}
FORECAST = {
    "daily": {"time": [DAY], "temperature_2m_max": [12.1], "temperature_2m_min": [3.6],
              "precipitation_probability_max": [20], "weather_code": [61], "wind_speed_10m_max": [10.8]},
    "hourly": {"time": [f"{DAY}T{h:02d}:00" for h in range(24)] + ["9999-12-31T00:00", "9999-12-31T02:00"],
               "temperature_2m": [float(h) for h in range(24)] + [2.0, 1.5],
               "precipitation_probability": [h for h in range(24)] + [30, 40],
               "weather_code": [3] * 24 + [61, 63]},
}
CONNECTIONS = {
    "from": {"name": "Zürich HB"}, "to": {"name": "Basel SBB"},
    "connections": [{
        "from": {"departure": f"{DAY}T22:32:00+0100", "platform": "32"},
        "to": {"arrival": f"{DAY}T23:36:00+0100", "platform": "8"},
        "duration": "00d01:04:00", "transfers": 1,
        "sections": [{"journey": {"category": "IC", "number": "1"}}, {"walk": {"duration": 120}, "journey": None},
                     {"journey": {"category": "IC", "number": "6"}}],
    }],
}


def source(handler) -> httpx.AsyncClient:
    """A data-source client answered by `handler(request)`."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def live(request: httpx.Request) -> httpx.Response:
    """Recorded answers of both sources."""
    if "geocoding" in request.url.host:
        return httpx.Response(200, json=GEOCODE)
    if request.url.host == "api.open-meteo.com":
        return httpx.Response(200, json=FORECAST)
    if request.url.host == "transport.opendata.ch":
        return httpx.Response(200, json=CONNECTIONS)
    return httpx.Response(404)


def offline(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("no network", request=request)


async def call(config: dict, http: httpx.AsyncClient, tool: str, args: dict) -> dict:
    """Call a service's tool over MCP (in-process) and return its signed envelope, checked."""
    app = create_app(config, http=http)
    async with Client(app.state.mcp) as client:
        result = await client.call_tool(tool, args)
    envelope = json.loads(result.content[0].text)
    assert verify_envelope(envelope, load_public_key(config["node_id"]), config["node_id"])  # always signed
    return envelope["payload"]


# --- weather --------------------------------------------------------------------------


def test_forecast_for_a_day_with_its_evening_and_night():
    payload = asyncio.run(call(WEATHER, source(live), "get_forecast", {"place": "Basel", "date": DAY}))
    assert payload["tool"] == "get_forecast" and payload["service"] == WEATHER["name"]
    assert (payload["place"], payload["sky"], payload["rain_chance_pct"]) == ("Basel", "light rain", 20)
    assert (payload["temperature_min_c"], payload["temperature_max_c"]) == (3.6, 12.1)
    hours = [h["time"][11:16] for h in payload["evening_and_night"]]
    assert hours == ["18:00", "20:00", "22:00", "00:00", "02:00"]  # evening, then the night after
    assert payload["source"] == "open-meteo.com"


@pytest.mark.parametrize("args, reason", [
    ({"place": "Basel", "date": "14.11.2026"}, "date must be YYYY-MM-DD"),
    ({"place": "Basel", "date": "2001-01-01"}, "forecasts cover today until"),
    ({"place": "<script>", "date": DAY}, "place must be a place name"),
])
def test_forecast_requests_that_cannot_be_answered_are_signed_refusals(args, reason):
    payload = asyncio.run(call(WEATHER, source(live), "get_forecast", args))
    assert payload["status"] == "refused" and reason in payload["reason"]


def test_an_unknown_place_is_refused_not_guessed():
    empty = source(lambda r: httpx.Response(200, json={"results": []}))
    payload = asyncio.run(call(WEATHER, empty, "get_forecast", {"place": "Atlantis", "date": DAY}))
    assert payload["status"] == "refused" and "no place called 'Atlantis'" in payload["reason"]


def test_without_internet_the_forecast_is_a_marked_sample():
    payload = asyncio.run(call(WEATHER, source(offline), "get_forecast", {"place": "Basel", "date": DAY}))
    assert payload["source"] == weather.SAMPLE_SOURCE and payload["place"] == "Basel"
    bad = asyncio.run(call(WEATHER, source(offline), "get_forecast", {"place": "Basel", "date": "soon"}))
    assert bad["status"] == "refused"  # a bad request stays a refusal, sample or not
    strict = asyncio.run(call({**WEATHER, "offline_sample": False}, source(offline), "get_forecast",
                              {"place": "Basel", "date": DAY}))
    assert strict == {"service": WEATHER["name"], "tool": "get_forecast", "status": "refused",
                      "reason": "the data source cannot be reached"}


def test_a_garbled_answer_from_the_source_falls_back_too():
    garbled = source(lambda r: httpx.Response(200, json=GEOCODE if "geocoding" in r.url.host else {"daily": {}}))
    payload = asyncio.run(call(WEATHER, garbled, "get_forecast", {"place": "Basel", "date": DAY}))
    assert payload["source"] == weather.SAMPLE_SOURCE


# --- trains ---------------------------------------------------------------------------


def test_connections_with_times_platforms_and_trains():
    seen = []

    def recording(request):
        seen.append(dict(request.url.params))
        return live(request)

    args = {"origin": "Zürich HB", "destination": "Basel SBB", "date": DAY, "time": "23:59", "arrive_by": True}
    payload = asyncio.run(call(TRAINS, source(recording), "get_connections", args))
    assert seen[0]["isArrivalTime"] == "1" and seen[0]["time"] == "23:59"  # latest arrival, not departure
    first = payload["connections"][0]
    assert (first["departure"], first["departure_platform"], first["arrival"], first["arrival_platform"]) == \
        ("22:32", "32", "23:36", "8")
    assert (first["duration_min"], first["changes"], first["trains"]) == (64, 1, ["IC 1", "IC 6"])
    assert (payload["from"], payload["to"], payload["source"]) == ("Zürich HB", "Basel SBB", "transport.opendata.ch")


@pytest.mark.parametrize("args, reason", [
    ({"origin": "Zürich HB", "destination": "Basel SBB", "date": DAY, "time": "25:00"}, "time must be HH:MM"),
    ({"origin": "", "destination": "Basel SBB", "date": DAY, "time": "22:00"}, "from must be a station"),
    ({"origin": "Zürich HB", "destination": "Basel SBB", "date": "tomorrow", "time": "22:00"}, "date must be"),
    ({"origin": "Zürich HB", "destination": "Basel SBB", "date": "1990-01-01", "time": "22:00"}, "today or later"),
    ({"origin": "Basel SBB", "destination": " basel sbb", "date": DAY, "time": "22:00"}, "different stations"),
])
def test_connection_requests_that_cannot_be_answered_are_signed_refusals(args, reason):
    payload = asyncio.run(call(TRAINS, source(live), "get_connections", args))
    assert payload["status"] == "refused" and reason in payload["reason"]


def test_no_connection_found_is_a_refusal():
    none = source(lambda r: httpx.Response(200, json={"connections": []}))
    args = {"origin": "Basel SBB", "destination": "Nowhere", "date": DAY, "time": "22:00"}
    payload = asyncio.run(call(TRAINS, none, "get_connections", args))
    assert payload["status"] == "refused" and "no connection" in payload["reason"]


@pytest.mark.parametrize("handler", [
    lambda r: httpx.Response(400, json={"errors": [{"message": "bad request"}]}),
    lambda r: httpx.Response(404),
])
def test_a_request_the_timetable_refuses_is_a_refusal_not_a_sample(handler):
    args = {"origin": "Zürich HB", "destination": "Basel SBB", "date": DAY, "time": "22:00"}
    payload = asyncio.run(call(TRAINS, source(handler), "get_connections", args))
    assert payload["status"] == "refused" and "refused the request" in payload["reason"]
    assert "connections" not in payload


def timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("too slow", request=request)


@pytest.mark.parametrize("handler", [offline, timeout, lambda r: httpx.Response(503)])
def test_only_an_outage_of_the_timetable_gives_the_sample(handler):
    args = {"origin": "Zürich HB", "destination": "Basel SBB", "date": DAY, "time": "22:00"}
    payload = asyncio.run(call(TRAINS, source(handler), "get_connections", args))
    assert payload["source"] == trains.SAMPLE_SOURCE


def test_bad_requests_get_no_sample_even_offline():
    for args in ({"origin": "Basel SBB", "destination": "Basel SBB", "date": DAY, "time": "22:00"},
                 {"origin": "Milano Centrale", "destination": "Basel SBB", "date": "1990-01-01", "time": "22:00"}):
        payload = asyncio.run(call(TRAINS, source(offline), "get_connections", args))
        assert payload["status"] == "refused" and "connections" not in payload


def test_without_internet_the_timetable_is_a_marked_sample():
    args = {"origin": "Zürich HB", "destination": "Basel SBB", "date": DAY, "time": "23:59", "arrive_by": True}
    payload = asyncio.run(call(TRAINS, source(offline), "get_connections", args))
    assert payload["source"] == trains.SAMPLE_SOURCE and len(payload["connections"]) == 3
    assert all(c["arrival"] <= "23:59" or c["arrival_date"] > DAY for c in payload["connections"][:1])


def test_parsing_helpers():
    assert trains.minutes("01d00:05:00") == 1445 and trains.minutes(None) is None
    assert trains.clock(None) is None and weather.describe(999) == "unknown"


# --- Tuttie: registry, seals, signature -----------------------------------------------


def test_tuttie_finds_the_services_and_checks_their_signed_answers():
    """search_registry by tag finds each service as gold; call_tool's answer passes the trust gate."""
    assert {"get_forecast", "get_connections"} <= READ_TOOLS

    async def run():
        data_source = source(live)
        apps = {4000: registry_app, WEATHER["port"]: create_app(WEATHER, http=data_source),
                TRAINS["port"]: create_app(TRAINS, http=data_source)}
        transports = {port: httpx.ASGITransport(app=app) for port, app in apps.items()}

        class Router(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                return await transports[request.url.port].handle_async_request(request)

        async with httpx.AsyncClient(transport=Router()) as http:
            link = in_process_link({f"http://localhost:{port}": app for port, app in apps.items()})
            toolbox = Toolbox(http, "http://localhost:4000", EventBus(), ApprovalBook(), mcp=link)
            found = await toolbox.search_registry(tags=["weather"])
            weather_result = await toolbox.call_tool(WEATHER["node_id"], "get_forecast", {"place": "Basel", "date": DAY})
            train_result = await toolbox.call_tool(TRAINS["node_id"], "get_connections",
                                                   {"origin": "Zürich HB", "destination": "Basel SBB", "date": DAY,
                                                    "time": "22:30"})
            return found, weather_result, train_result

    found, weather_result, train_result = asyncio.run(run())
    nodes = {n["node_id"]: n for n in found["verified"]}
    assert nodes[WEATHER["node_id"]]["trust_tier"] == "gold"
    assert weather_result["data"]["sky"] == "light rain" and weather_result["trust_tier"] == "gold"
    assert train_result["data"]["connections"][0]["trains"] == ["IC 1", "IC 6"]


def test_timeline_lines_for_weather_and_trains():
    from assistant.tools import summarize
    forecast = {"place": "Basel", "date": DAY, "sky": "light rain", "temperature_min_c": 3.6, "temperature_max_c": 12.1,
                "rain_chance_pct": 20, "source": "open-meteo.com"}
    assert summarize("get_forecast", forecast) == f"Weather Basel {DAY}: light rain, 3.6–12.1 °C, rain 20 %"
    sample = trains.sample_connections("Zürich HB", "Basel SBB", DAY, "22:30")
    assert summarize("get_connections", sample).endswith("(IC) (sample data)")
    assert summarize("get_forecast", {"status": "refused", "reason": "date must be YYYY-MM-DD"}) == \
        "get_forecast: date must be YYYY-MM-DD"
