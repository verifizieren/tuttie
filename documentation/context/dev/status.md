# Status: done, pending, conventions

The shared state of the project, for teammates and for AI coding agents working with us.
**Read this first, and update it in the same change** whenever you finish something, start
something big, or make a decision others need to know. Goals and build order:
[goals.md](goals.md); concept: `documentation/concept.md`; work areas:
`documentation/architecture.md`; formats: `documentation/formats.md`.

Last updated: 2026-10-31 (company agents).

## Done

| Area | What works | Where |
| --- | --- | --- |
| APS signing | Canonical JSON, Ed25519 keys, signed envelopes, seals with gold / blue / grey / broken tiers, signed user approvals. 25 tests. | `code/aps/`, `code/tests/` |
| Registry | Search by tags and capability, sealed records. | `code/registry/` |
| Business nodes | Signed tools (`get_availability`, `get_policies`), `book` (only with the user's signed approval for exactly the right total, no replays). | `code/node/`, `code/data/nodes/` |
| Company agents | The same agent object for every company: persona, a shared tool catalog with `available` / `planned` tools, a signed agent card (`GET /agent/card`), A2A answers in persona with priced add-ons from the config (`POST /agent`), and wake-ups from the marketplace (`POST /agent/invoke`: interested?, which tool next). Three hotel agents: Alpina Grand Basel (large chain branch, Lena), Hotel Rheinblick (medium, Marco), Gästehaus am Rhein (small independent, Anna). Private negotiation limits never leave the node. | `code/node/agent.py`, `code/node/catalog.py`, `code/node/README.md` |
| Demo data | Hotels Alpina Grand (gold + blue), Rheinblick (gold + blue), Gästehaus am Rhein (gold), Spalenhof (blue), Gundeli (gold only, family rooms), Basel Budget Rooms (unsigned → untrusted), basel-cheap-hotels (forged seal → broken); a licensed lawyer (gold) and a self-signed fake lawyer (untrusted). | `code/data/nodes/` |
| User's agent | LLM tool loop with the trust gate: search, signed facts, A2A commitments, booking with phone approval, cited answers, reasoning summaries as "thinking". | `code/assistant/` |
| End-to-end run | The whole signed flow in one process with a simulated phone. | `code/scripts/demo_headless.py` |
| Wallet app | React + Vite PWA, phone-first: card stack, the Tuttie card is the agent's face (pycozmo eyes), asleep → tap to voice mode, text behind a keyboard icon, iOS-sheet swipe to close, keyboard-safe, installable. **Not connected to the backend yet.** | `code/apps/wallet/` |
| Hosting | Live at <https://web4.mendes.dev> on the team server, kept running by a systemd user service. | `code/deploy/tuttie.service` |
| Repo structure | BaselHack template, work-area folders with scope READMEs, team context folders, concept and architecture docs, draft marketplace formats. | `documentation/`, `code/*/README.md` |

## Pending

Build order from [goals.md](goals.md):

1. **Agents** — company agents done (three hotels, same agent object). Next: **Tuttie**, our
   main agent, as its own agent identity.
2. **Agent layer of the marketplace** — not started (`code/marketplace/`, draft formats in
   `documentation/formats.md`). The agents are ready to be woken: the marketplace calls
   `POST /agent/invoke` on every agent subscribed to an event (`wakes_on`). Tools still to
   build: `make_offer`, `counter_offer`, `pay` (outlined in `code/node/catalog.py`).
3. **Human layer in the wallet** — not started: postings, offers and approvals in the wallet;
   connect the wallet to `POST /chat`, `GET /events` and the approvals API.
4. **Negotiation and subagents** — not started.
5. **MCP services** — not started.

Other open items: voice agent (`code/voice/`), the demo runner (`code/demo/`), owner view
(`code/apps/owner/`), presentation site and QR code (`code/apps/presentation/`), a
behind-the-scenes view of the signed timeline, team names in `license.txt` and the team
profiles in the readme.

## Conventions

- **One app.** The wallet is the real product; the demo is a run through it. Never build
  separate demo screens. In repo files say "demo", not "scripted demo".
- **APS (agent protocol and signing) is its own work area with its own owner.** Other work
  only uses `code/aps/`; changes to it go through that owner.
- **Signing only through `code/aps/`.** No signature, no action: untrusted (grey) and broken
  (red) nodes can be shown but never transact.
- **Prices never come from an LLM**: only from node configs and signed messages.
- **Contracts:** change `documentation/formats.md` only after telling the whole team.
- **Code quality:** a docstring per module and public function, comments for the *why*,
  tests with every feature, docs and this file updated in the same change.
- **Commits:** small, one concern each, clear messages; no AI co-author lines. Pull and
  rebase before pushing (teammates push too); never force-push `main`.
- **Layout (BaselHack template):** code in `code/`, docs in `documentation/`, presentation
  files in `assets/`.
- **Wallet look:** calm and minimal. Seal tiers shown only by colour (no gold/blue/broken
  words); no glow borders; the eyes have only a faint halo; text input is always a
  deliberate choice and never opens the keyboard by itself.
- **Secrets:** the OpenAI key lives in `code/.env` (ignored); ask the team for it.

## Decisions and lessons

Why things are the way they are, so nobody has to rediscover them:

- **LLM:** `gpt-6-luna` through the OpenAI **Responses API** with reasoning on
  (`code/llm.py`). Reasoning models only allow tools together with reasoning there;
  `gpt-5.6-luna` did no reasoning at its default and gave no summaries; `gpt-4.1-mini`
  dropped rules in the full flow. Only `llm.py` would change for another provider.
- **Structure beats prompting.** When the model misbehaved, fixing the tool contract worked
  better than longer prompts: search results split into `verified` / `rejected`, an enum for
  `capability` (the model invented values like "hotel_booking"), booking totals computed only
  from signed facts, commitments built from fixed `add_ons` in the node config.
- **The assistant always asks the hotel's agent before booking**; otherwise it skipped A2A
  and booked without the dog fee.
- **Broken vs untrusted:** a forged or invalid seal is broken (red); self-signed or unsigned
  is untrusted (grey). Booking needs `can_take_payment`, which grey nodes never get.
- **iOS PWA:** status bar style `black` (not `black-translucent`), plus extra top margin in
  the installed app; full-bleed under the Dynamic Island was tried and rejected. The agent
  card must not be a GPU layer (`will-change`), or it renders blurry after expanding. The
  layout follows `visualViewport`, so the keyboard shrinks the app instead of pushing it away.
- **Gestures:** release decisions use the speed of the last 100 ms; the card keeps its
  shape while dragged. Headless browsers send pointer events too slowly to test flicks;
  dispatch `PointerEvent`s in the page instead.

## Environment

- **Team server:** only ports 4000-4049 are open. Registry 4000, nodes 4001-4007,
  assistant and apps 4040, wallet dev server 4041, marketplace 4010 (planned).
- **Service:** `systemctl --user restart tuttie` deploys Python changes (`run.sh` also
  rebuilds the wallet); logs: `journalctl --user -u tuttie -f`. Do not start `./run.sh` by
  hand on the server, the ports would clash.
- **Testing on the shared instance:** it has one shared conversation, and `POST /reset`
  clears everyone's screen; test with `scripts/demo_headless.py` instead.
