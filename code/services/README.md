# Public information services: weather and trains

Services on the agent web that Tuttie asks for facts, not businesses it books with. Each is a
sealed node in the registry (`data/services/*.json`, `"kind": "service"`) with its own key; its
tools run over MCP at `/mcp/` and every answer is a signed envelope, so Tuttie checks a forecast
or a timetable exactly like a hotel's price (seals, signature, freshness).

| File | What |
| --- | --- |
| `server.py` | One generic server per config: the service's MCP tools, signing, live data or marked sample. |
| `weather.py` | `get_forecast(place, date)` from Open-Meteo (free, no key): day min/max, rain chance, wind, sky, evening and night hours. |
| `trains.py` | `get_connections(origin, destination, date, time, arrive_by)` from transport.opendata.ch (free, no key): times, platforms, duration, changes, trains. |

- Ports: weather 4011, trains 4012; `run.sh` starts both.
- No internet (a venue's Wi-Fi): the answer is a sample marked in `source`, so the demo runs;
  set `"offline_sample": false` to refuse instead.
- A request that cannot be answered is a signed refusal with the reason.
- Tuttie: `search_registry` (tags `weather` / `train`), then `call_tool` (`get_forecast`,
  `get_connections` are in `READ_TOOLS`); rule 6 of its prompt.
- Formats: `documentation/formats.md`, "Public information services". Tests: `tests/test_services.py`.

Try it: `python -m services.server --config data/services/trains.json`, then ask Tuttie
"Which train from Zürich gets me to Basel before midnight on 14 November?".
