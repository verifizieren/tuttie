# Status: done, pending, conventions

The shared state of the project, for teammates and for AI coding agents working with us.
**Read this first, and update it in the same change** whenever you finish something, start
something big, or make a decision others need to know. Goals and build order:
[goals.md](goals.md); concept: `documentation/concept.md`; work areas:
`documentation/architecture.md`; formats: `documentation/formats.md`.

Last updated: 2026-10-31 (merged: company agents, sessions and subagents with APS UIDs and Tuttie's identity).

## Done

| Area | What works | Where |
| --- | --- | --- |
| APS signing | Canonical JSON, Ed25519 keys, signed envelopes with an optional freshness check (the assistant drops node replies older than 5 min as replays), seals with gold / blue / grey / broken tiers, Swiss UIDs (check digit) bound into every seal and verified only by the commercial register's seal, signed user approvals, user delegations (the user's key signs which scopes an agent may use for them; paying is never delegated). | `code/aps/`, `code/tests/` |
| Registry | Search by tags and capability, sealed records. | `code/registry/` |
| Business nodes | Signed tools (`get_availability`, `get_policies`, which includes the business profile), `book` (only with the user's signed approval for exactly the right total, no replays). | `code/node/`, `code/data/nodes/` |
| Company agents | The same agent object for every company: persona, a shared tool catalog with `available` / `planned` tools, a signed agent card (`GET /agent/card`), A2A answers in persona with priced add-ons from the config (`POST /agent`), wake-ups from the marketplace (`POST /agent/invoke`: interested?, which tool next), and sessions. The LLM never sets a price and never sees private facts (`PRIVATE_FACTS`: negotiation limits). Three hotel agents, each with a public profile and private negotiation limits: **Alpina Grand Basel** (large chain branch, 220 rooms, Lena, gold + blue), **Hotel Rheinblick** (medium, family-owned, 42 rooms, Marco, gold + blue), **Gästehaus am Rhein** (small independent, 7 rooms, Anna, gold). | `code/node/agent.py`, `code/node/catalog.py`, `code/node/README.md` |
| Demo data | The three hotel agents above; also Spalenhof (medium, 48 rooms, blue) and Gundeli (small, 11 rooms, gold, family rooms) as further hotels with profiles, Basel Budget Rooms (unsigned → untrusted), basel-cheap-hotels (forged seal → broken); a licensed lawyer (gold) and a self-signed fake lawyer (untrusted). | `code/data/nodes/` |
| Sessions and memory | Shared module for all agents: isolated sessions with their own memory (many in parallel), and context passing where every item is public, negotiation or private (private never leaves). Hotels keep one memory per session and answer with the history. | `code/sessions/`, node `/agent/sessions/...` |
| Tuttie's subagents | Tuttie spawns one subagent per business with its own memory and only the shareable context; a pool runs them in parallel; every call goes through the trust gate. Live-tested: three hotels in parallel over two rounds, each remembering its own offer, the private budget never shared. Bargaining logic is step 4. | `code/assistant/subagents.py` |
| User's agent | LLM tool loop with the trust gate: search, signed facts, A2A commitments, booking with phone approval, cited answers, reasoning summaries as "thinking". Own identity: Tuttie (`ch.tuttie.alex-muster`) has its own key, an Adobe (blue) seal and the user's signed delegation; `GET /identity` returns it checked. | `code/assistant/`, `code/data/agents/` |
| End-to-end run | The whole signed flow in one process with a simulated phone. | `code/scripts/demo_headless.py` |
| Wallet app | React + Vite PWA, phone-first: card stack, the Tuttie card is the agent's face (pycozmo eyes), asleep → tap to voice mode, text behind a keyboard icon, iOS-sheet swipe to close, keyboard-safe, installable. **Not connected to the backend yet.** | `code/apps/wallet/` |
| Hosting | Live at <https://web4.mendes.dev> on the team server, kept running by a systemd user service. | `code/deploy/tuttie.service` |
| Repo structure | BaselHack template, work-area folders with scope READMEs, team context folders, concept and architecture docs, draft marketplace formats. | `documentation/`, `code/*/README.md` |

## Pending

Build order from [goals.md](goals.md):

1. **Agents** — done: the three hotel agents (same agent object, personas, profiles, private
   limits), sessions with memory, Tuttie's identity and its parallel subagents. Next:
   **Tuttie** as the main agent that reads a posting and spawns the subagents. Tuttie does
   not sign its own outgoing messages yet; that comes with the marketplace.
2. **Agent layer of the marketplace** — not started (`code/marketplace/`, draft formats in
   `documentation/formats.md`). The agents are ready to be woken: the marketplace calls
   `POST /agent/invoke` on every agent subscribed to an event (`wakes_on`). Tools still to
   build: `make_offer`, `counter_offer`, `pay` (outlined in `code/node/catalog.py`).
3. **Human layer in the wallet** — not started: postings, offers and approvals in the wallet;
   connect the wallet to `POST /chat`, `GET /events` and the approvals API.
4. **Negotiation and subagents** — the base exists (subagents, sessions, memory, context
   levels); missing: the bargaining logic and the `make_offer` / `counter_offer` tools.
5. **MCP services** — not started.

### Where to start next

1. **Step 1 check-in with the pitch and design team** (goals.md: every step ends with one):
   the hotel sizes, profiles and prices, and Tuttie's identity.
2. **Step 2:** agree on the draft marketplace formats in `documentation/formats.md`,
   then build `code/marketplace/` (:4010) test-first in the same style as `test_tools.py`.
   APS is ready for it: Tuttie signs requests with its own key, and businesses check its
   delegation (`verify_delegation(..., scope="post_requests")`) before answering.
3. **Wallet:** show Tuttie's verified identity on its card from `GET /identity` (proxied in
   the Vite dev server).

### Test coverage

77 tests, all green (`pytest -q`), no network and no LLM: `test_aps.py` (signing, freshness,
seals, tiers, UIDs, approvals, delegations), `test_node_book.py` (node `book`: approval, commitments, replay), `test_node_agent.py` (the
company agent with a fake LLM, private facts, read tools, the three hotel configs),
`test_business_agent.py` (same agent object, persona, tool catalog, card, wake-ups),
`test_sessions.py` and `test_agent_sessions.py` (session memory, isolation, context levels,
parallel subagents against the real node apps), `test_tools.py` (assistant trust gate and
Tuttie's identity, with mocked HTTP and the real demo keys).
Not covered yet: `registry/app.py`, the assistant's LLM loop (`assistant/agent.py`) and its HTTP
routes (`assistant/app.py`).

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

- **UIDs are vouched for by the commercial register only.** Every seal signs the node's
  `uid` (or `null`), so it cannot be swapped later; `handelsregister-bs` has
  `vouches_for_uid` and its seal is invalid without a well-formed UID. A UID under any
  other seal is shown as a claim, not as verified. The demo UIDs are made up but have
  correct check digits.
- **Tuttie has its own key, separate from the user's.** A seal says who the agent is (the
  platform, Adobe, vouches for the software: blue); the user's signed delegation says for
  whom it speaks and with which scopes. The `user` key stays the person's: it signs
  approvals and delegations, never messages. User agents live in `data/agents/` (in the
  registry, but no node server) and `issue_seals.py` re-signs the delegation for 365 days
  on every run.
- **Private facts never reach an LLM.** The node's agent used to get all `facts` in its
  prompt; with negotiation floors in the config that would leak them to any agent that asks
  cleverly. `PRIVATE_FACTS` in `node/agent.py` keeps them out of the prompt and out of every
  tool reply. Add any new owner-only fact there.
- **Hotel sizes are in `facts.profile`, not in tags or seals:** owners can edit them without
  new seals. The demo prices and the dog storyline (Rheinblick, CHF 180 + 15) are unchanged.
- **Freshness is opt-in per call.** Live replies must be at most 300 s old
  (`MAX_REPLY_AGE_S` in `assistant/tools.py`); stored envelopes like commitments are
  verified without it because they have `valid_until`.

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
- **Sessions and memory** live in each agent's process for now, so a restart forgets them.
  Each session has its own lock: turns within one session stay in order, different sessions
  run in parallel.
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
