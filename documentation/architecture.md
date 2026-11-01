# Tuttie: architecture and work areas

Each work area has its own folder, its own issue and a contract with the others, so people
can work in parallel without stepping on each other. Contracts live in
`documentation/formats.md`; change them only after telling the team.

## Components

```
            presentation QR page (apps/presentation)     owner view (apps/owner)
                         | links to the wallet                   | edits agent presence
                         v                                       v
  phone: wallet (apps/wallet) + voice (code/voice)        business nodes (code/node)
                         |                                  ^  signed offers, A2A,
                         v                                  |  negotiation, booking
         user's agent (code/assistant) <--> marketplace (code/marketplace) <--> registry
                         |                                        (code/registry)
                         v
              timeline: every signed step, live over SSE (GET /events)
                                   all signing: code/aps
             demo (code/demo) drives the same real components
```

## Work areas

| Area | Folder | Issue | Status | Talks to others through |
| --- | --- | --- | --- | --- |
| Protocol and signing | `code/aps/` | #10 | done, tested (100 %): envelopes, seals, UIDs, approvals, delegations, signed calls, the action gate for `book`/`pay`, payment mandates | Python API; formats: envelope, seals, approval, delegation, signed call, action gate, payment mandate |
| Registry | `code/registry/` | #9 | done | `GET /search`, `GET /nodes/{id}` |
| Public information services (weather, trains) | `code/services/`, `code/data/services/` | #10 | done: sealed services with signed MCP tools `get_forecast` (Open-Meteo) and `get_connections` (transport.opendata.ch), marked sample data offline | MCP tools, signed envelopes; formats: public information services |
| Business nodes and company agents | `code/node/`, `code/data/nodes/` | #10 | tools served over MCP at `/mcp/` (`node/mcp_tools.py`; `book` needs a signed call); same agent object for every company (persona, tool catalog, wake-ups, sessions); three hotel agents large / medium / small with public profiles and private negotiation limits; `make_offer` (signed offers to the market), `counter_offer`, `book` and `pay` available; owner API (`node/owner.py`) for the owner view | MCP tools, signed envelopes; formats: business tools over MCP, signed call, business agent, offer, counter-offer |
| Marketplace (requests, offers) | `code/marketplace/` (:4010) | #8, #9, #10 | done: signed postings, wake-up of verified, subscribed businesses via `/agent/invoke`, signed offers; it decides nothing (Tuttie builds its own shortlist, bargaining is in `code/negotiation/`) | formats: request, offer, counter-offer, agreement |
| Bargaining (step 4) | `code/negotiation/` | #10 | done, tested (100 %): hotel `counter_offer` tool within private limits (HTTP and MCP), Tuttie's parallel negotiating subagents, agreements redeemed once at booking; mounted in every node | signed Counter / Agreement / Rejection, `POST /tools/counter_offer`, MCP `counter_offer` |
| User's agent (Tuttie) | `code/assistant/`, `code/data/agents/` | #10 | done: own identity (key, seal, user delegation); reads the user's context (`recall_context`), posts a signed request (budget stays private), bargains through parallel subagents (`negotiate`), shows the hotels as cards, books the liked deal after the user's approval, pays the city tax with a mandate; tools over MCP behind its trust gate | UI events over SSE, approvals API, `GET /identity` |
| Sessions, memory, context passing | `code/sessions/` | #8, #10 | done: isolated sessions with memory, used by company agents and Tuttie's subagents; context classed public / negotiation / private | Python API; node session endpoints |
| Wallet app (phone) | `code/apps/wallet/` (React + Vite, PWA) | #2 | done, connected: card stack, Tuttie's face (eyes driven by its presence), voice mode, text fallback, the run under the eyes (posting, offers, bargaining), swipe deck of hotel cards, approval sheet with Face ID-style confirmation, booking card, history of conversations | `POST /chat`, `GET /events` (SSE), approvals API, conversations API, voice token |
| Voice agent | `code/voice/` | #2, #3 | done, live: self-hosted LiveKit (signaling proxied by the assistant at `/rtc`, media TCP 4042 / UDP 4043, TURN relay coturn on TCP 4044 for phones), ElevenLabs speech-to-text and voice, `voice/agent.py` passes what the user says to Tuttie and speaks the answers | `POST /voice/say`, `GET /voice/events`, `POST /voice/token` |
| Owner view | `code/apps/owner/` (React + Vite) | #5 | done: one page per business (rooms, extras, private negotiation limits, agent); edits are a draft, reviewed and deployed as a new numbered version the node uses at once | `GET /owner/overview`, `GET /owner/versions`, `POST /owner/deploy` on the node (`node/owner.py`), behind `OWNER_TOKEN` |
| Presentation site and QR | `code/apps/presentation/` | #1, #6 | QR page done: static, phone-first, no build, served at `/presentation/` by the assistant's static mount; numbers, idea, business case, a self-playing demo of the wallet | links into the live wallet and the repo |
| Keynote (pitch deck) | `code/apps/keynote/` | #1, #3 | done: static deck served at `/keynote/` (no build), black stage with at most three words; the clicker drives the real wallet in a phone frame through `demo.js` (input and timing only, the same backend and verification); fallback recording `media/fallback.webm` + `.mp4` (V); presenter view (N); the owner beat is a screenshot of the real owner view; spoken lines in `SPEAKER-NOTES.md` | `POST /chat`, `POST /reset`, the wallet at `/wallet/` |
| Demo | `code/demo/` | #3, #2 | the stage demo is driven by `code/apps/keynote/demo.js` (see Keynote); `code/demo/` itself has only its README; `scripts/demo_headless.py` runs the full flow in one process | drives the user's agent and the apps |
| Shared UI pieces | `code/apps/shared/` | — | brand stylesheet, seal badges | — |
| Pitch, storyline, tech check, numbers | `assets/`, `documentation/` | #1, #3, #4, #7 | team | — |

## Rules that keep the areas independent

- **The demo runs the real app.** `code/demo/` never has its own UI. It drives the real
  wallet by feeding the storyline's input into the same backend the user would use
  (e.g. the user's lines instead of live speech) and lets the real flow run. Any feature
  the demo shows must exist in the app for real use; demo-only switches are limited to
  input and timing (e.g. `?demo=<script>` on the wallet), never to separate screens.

- **Signing stays in `code/aps/`.** No other folder creates or checks signatures by hand.
- **Prices never come from an LLM.** They come from node configs and signed messages.
- **The demo calls the real components**; it never fakes verification
  (`documentation/concept.md`).
- **Apps:** the wallet is a React app (Vite) in `code/apps/wallet/`; its build (`dist/`) is
  served by the assistant at `/wallet/` and `run.sh` builds it. The other apps are static
  pages (HTML + vanilla JS) served at `/<app>/`. Brand and seal badges are shared in
  `apps/shared/`.
- **Ports** (team server allows 4000-4049): registry 4000, nodes 4001-4009, marketplace 4010,
  weather and trains services 4011-4012, assistant and apps 4040, wallet dev server 4041,
  LiveKit media TCP 4042 / UDP 4043, TURN relay 4044 (LiveKit signaling stays local on 7880).
