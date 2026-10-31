# Business nodes and company agents (issue #10)

One FastAPI app (`server.py`), started once per config in `../data/nodes/`. Every node is a
company on the agent web: its tools answer from the config's `facts`, and every company has
the **same agent object** (`agent.py`) with its own persona.

| File | What it does |
| --- | --- |
| `server.py` | endpoints: signed tools (`/tools/*`), the agent (`/agent`, `/agent/card`, `/agent/invoke`) and its sessions (`/agent/sessions/...`) |
| `agent.py` | `BusinessAgent`: persona, tools, A2A answers with priced add-ons, wake-ups from the marketplace |
| `catalog.py` | the shared tool catalog with status `available` or `planned` |

Formats: `documentation/formats.md`, "Business agent" and "Sessions and context passing".
Every session is an isolated conversation with its own memory (`code/sessions/`), so a hotel
can talk to many guests' agents in parallel. Signing and seals come from
`code/aps/` (APS is owned by its own work area; nodes only use it).

## The three hotel agents

| Size | Hotel | Agent | Rooms | Seals | Port |
| --- | --- | --- | --- | --- | --- |
| large (chain branch) | Alpina Grand Basel | Lena | 220 | gold + blue | 4008 |
| medium (family-owned) | Hotel Rheinblick | Marco | 42 | gold + blue | 4001 |
| small (independent) | Gästehaus am Rhein | Anna | 7 | gold | 4009 |

The other nodes (Spalenhof, Gundeli, Basel Budget Rooms, the scam hotel, the two lawyers) use
the default agent until they get an `agent` section.

## Add a company agent

1. Copy a hotel config in `../data/nodes/`, give it a new `node_id`, `name` and a free port
   (team server: 4000-4049).
2. Fill in `facts` (rooms, policies, `add_ons` with fixed prices, private `negotiation`
   limits) and the `agent` section (persona, tools from `catalog.py`, `wakes_on`).
3. From `code/`: `.venv/bin/python scripts/gen_keys.py && .venv/bin/python scripts/issue_seals.py`
   to create its key and sealed registry record; commit both.
4. Restart (`./run.sh`, or `systemctl --user restart tuttie` on the server) and check
   `GET http://localhost:<port>/agent/card`.

Planned tools (`make_offer`, `counter_offer`, `pay`) are only described in `catalog.py`; agents
already know them and say when they would use one.
