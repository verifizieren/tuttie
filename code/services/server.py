"""A public information service on the agent web: weather or train connections, signed.

One generic server per config in data/services/ (`"service": "weather"` or `"trains"`). Like a
hotel node it is in the registry with its seals, serves its tools over MCP at /mcp/
(node/mcp_tools.py `mcp_app`) and signs every answer with its own key, so Tuttie checks a
forecast or a timetable exactly like a hotel's price: seals first, then the signature.

    weather  get_forecast(place, date)                                  → services/weather.py
    trains   get_connections(origin, destination, date, time, arrive_by) → services/trains.py

The data is live (Open-Meteo, transport.opendata.ch). When that source cannot be reached, the
service answers with a clearly marked sample (`source`), so a demo without internet still runs;
a request that cannot be answered (unknown place, date out of range) is a signed refusal.

Run: python -m services.server --config data/services/weather.json   (run_all.py starts them)
"""

import argparse
import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer

from aps import load_signing_key, sign_envelope
from node.mcp_tools import mcp_app
from services import trains, weather

TIMEOUT_S = 8  # a slow source falls back to the sample instead of keeping Tuttie waiting


def tool_functions(service: str, signed: Callable[[dict], dict], http: Callable[[], httpx.AsyncClient],
                   offline_sample: bool) -> dict[str, Callable[..., Awaitable[dict]]]:
    """The MCP tools of one service; each returns the service's signed envelope."""

    async def answer(tool: str, live: Callable[[], Awaitable[dict]], sample: Callable[[], dict],
                     unavailable: type[Exception]) -> dict:
        """Live data, else a marked sample when the source is down; refusals are signed too."""
        refuse = lambda reason: signed({"tool": tool, "status": "refused", "reason": reason})  # noqa: E731
        try:
            return signed({"tool": tool, **await live()})
        except unavailable as refusal:
            return refuse(str(refusal))
        except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError):  # source down or answered oddly
            pass
        if not offline_sample:
            return refuse("the data source cannot be reached")
        try:
            return signed({"tool": tool, **sample()})
        except unavailable as refusal:
            return refuse(str(refusal))

    if service == "weather":
        async def get_forecast(place: str, date: str) -> dict:
            """The weather for a place on a day: min/max temperature, chance of rain, wind, sky, and
            the evening and night hours. place: e.g. "Basel"; date: YYYY-MM-DD (up to 15 days ahead).
            Returns a signed envelope; `source` says where the data comes from."""
            def sample() -> dict:
                weather.check_request(place, date, weather.Date.today())  # a bad request stays a refusal
                return weather.sample_forecast(place, date)
            return await answer("get_forecast", lambda: weather.forecast(http(), place, date), sample,
                                weather.WeatherUnavailable)
        return {"get_forecast": get_forecast}

    if service == "trains":
        async def get_connections(origin: str, destination: str, date: str, time: str, arrive_by: bool = False) -> dict:
            """Train connections in Switzerland: departure, arrival, platforms, duration, changes and
            trains. origin / destination: stations, e.g. "Zürich HB", "Basel SBB"; date: YYYY-MM-DD;
            time: HH:MM, the earliest departure (or, with arrive_by, the latest arrival).
            Returns a signed envelope; `source` says where the data comes from."""
            def sample() -> dict:
                trains.check_request(origin, destination, date, time)
                return trains.sample_connections(origin, destination, date, time, arrive_by)
            return await answer("get_connections", lambda: trains.connections(http(), origin, destination, date, time, arrive_by),
                                sample, trains.TrainsUnavailable)
        return {"get_connections": get_connections}

    raise ValueError(f"unknown service {service!r}")


def create_app(config: dict, http: httpx.AsyncClient | None = None) -> FastAPI:
    """The app for one service config; `http` reaches the data source (tests pass a mocked one)."""
    node_id = config["node_id"]
    signing_key = load_signing_key(node_id)
    client: dict[str, httpx.AsyncClient | None] = {"http": http}

    def signed(payload: dict) -> dict:
        """Wrap an answer in this service's signed envelope."""
        return sign_envelope(node_id, {"service": config["name"], **payload}, signing_key)

    def get_http() -> httpx.AsyncClient:
        """One shared client for the data source (made on first use when none was passed in)."""
        if client["http"] is None:
            client["http"] = httpx.AsyncClient(timeout=TIMEOUT_S, headers={"User-Agent": "tuttie-agent-web/0.1"})
        return client["http"]

    tools = MCPServer(config["name"], instructions=f"{config['name']}: public information, every answer a "
                                                   "signed envelope; verify it against the registry record.")
    for name, function in tool_functions(config["service"], signed, get_http, config.get("offline_sample", True)).items():
        tools.add_tool(function, name=name)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Run the MCP session manager while the service runs; close the data source client after."""
        async with tools.session_manager.run():
            yield
        if http is None and client["http"] is not None:
            await client["http"].aclose()

    app = FastAPI(title=config["name"], lifespan=lifespan)
    app.state.mcp = tools  # in-process MCP clients (tests, headless demo) connect to this directly
    app.mount("/mcp", mcp_app(tools))
    return app


def main() -> None:
    """Start one service from its config file."""
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    uvicorn.run(create_app(config), host="0.0.0.0", port=args.port or config["port"])


if __name__ == "__main__":
    main()
