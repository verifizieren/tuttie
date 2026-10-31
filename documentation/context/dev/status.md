# Status: done, pending, conventions

The shared state of the project, for teammates and for AI coding agents working with us.
**Read this first, and update it in the same change** whenever you finish something, start
something big, or make a decision others need to know. Goals and build order:
[goals.md](goals.md); concept: `documentation/concept.md`; work areas:
`documentation/architecture.md`; formats: `documentation/formats.md`.

Last updated: 2026-10-31 (weather and train services: sealed, signed MCP tools, live data, Tuttie uses them).

## Done

- Wallet and local development fixes (2026-10-31): zero-duration face transitions finish
  immediately, preventing invalid coordinates when the first frame shares the startup
  timestamp; regression test added. Wallet dev proxy forwards history, reset, voice and RTC
  WebSockets. Owner tests use explicit test-file discovery compatible with Node 22.
  Validation: 310 Python, 23 wallet and 7 owner tests pass; both apps build. Local Chrome
  check confirms eyes render and animate, including the equal-timestamp startup case.
  Voice/WebSocket operation has not been verified end to end.
- Resumable wallet history: New chat retains the prior assistant and verified booking
  context in a bounded, browser-owned server cache. History → Continue chat restores its
  timeline, tool state and signed agreements; legacy/expired entries remain readable and
  explain that a fresh request is required. Reload keeps the selected conversation. Voice
  rooms reconnect on selection and reject utterances from an inactive chat. History text
  no longer uses the live view's fade mask. Validation: 318 Python tests, 25 wallet tests,
  wallet build; browser regression with API fixtures covers new → history → continue →
  choose → approve → booked, plus expired history. Real signed agreement redemption after
  switching is covered by the in-process backend test (only the LLM is stubbed).

| Area | What works | Where |
| --- | --- | --- |
| APS signing | Canonical JSON, Ed25519 keys, signed envelopes with an optional freshness check (the assistant drops node replies older than 5 min as replays), seals with gold / blue / grey / broken tiers, Swiss UIDs (check digit) bound into every seal and verified only by the commercial register's seal, signed user approvals, user delegations (the user's key signs which scopes an agent may use for them: `ask_agents`, `post_requests`, `negotiate`, `book`; paying is never delegated). **For MCP actions:** signed calls (`aps/call.py`: the agent signs tool + args + nonce + time; replays fail the 300 s window or the nonce book) and one action gate (`aps/gate.py` `check_action(call, needs)`: caller seals, signature, nonce, delegation scope, the hotel's own agreement, the user's approval for exactly the amount; a refusal names the missing signature, `checks` lists what passed). | `code/aps/`, `code/tests/` |
| Registry | Search by tags and capability, sealed records. | `code/registry/` |
| Business nodes | Signed tools (`get_availability`, `get_policies`, which includes the business profile), `book` (only with the user's signed approval for exactly the right total, no replays). | `code/node/`, `code/data/nodes/` |
| Company agents | The same agent object for every company: persona, a shared tool catalog with `available` / `planned` tools, a signed agent card (`GET /agent/card`), A2A answers in persona with priced add-ons from the config (`POST /agent`), wake-ups from the marketplace (`POST /agent/invoke`: interested?, which tool next), and sessions. The LLM never sets a price and never sees private facts (`PRIVATE_FACTS`: negotiation limits). Three hotel agents, each with a public profile and private negotiation limits: **Alpina Grand Basel** (large chain branch, 220 rooms, Lena, gold + blue), **Hotel Rheinblick** (medium, family-owned, 42 rooms, Marco, gold + blue), **Gästehaus am Rhein** (small independent, 7 rooms, Anna, gold). | `code/node/agent.py`, `code/node/catalog.py`, `code/node/README.md` |
| Demo data | The three hotel agents above; also Spalenhof (medium, 48 rooms, blue) and Gundeli (small, 11 rooms, gold, family rooms) as further hotels with profiles, Basel Budget Rooms (unsigned → untrusted), basel-cheap-hotels (forged seal → broken); a licensed lawyer (gold) and a self-signed fake lawyer (untrusted). | `code/data/nodes/` |
| Sessions and memory | Shared module for all agents: isolated sessions with their own memory (many in parallel), and context passing where every item is public, negotiation or private (private never leaves). Hotels keep one memory per session and answer with the history. | `code/sessions/`, node `/agent/sessions/...` |
| Tuttie's subagents | Tuttie spawns one subagent per business with its own memory and only the shareable context; a pool runs them in parallel; every call goes through the trust gate. Live-tested: three hotels in parallel over two rounds, each remembering its own offer, the private budget never shared. Bargaining logic is step 4. | `code/assistant/subagents.py` |
| User's agent | LLM tool loop with the trust gate: search, signed facts, A2A commitments, booking with phone approval, cited answers, reasoning summaries as "thinking". Own identity: Tuttie (`ch.tuttie.alex-muster`) has its own key, an Adobe (blue) seal and the user's signed delegation; `GET /identity` returns it checked. | `code/assistant/`, `code/data/agents/` |
| Marketplace (agent layer) | Built against the draft formats: Tuttie's signed postings in (seals, freshness, user delegation `post_requests`), matching businesses woken in parallel at `POST /agent/invoke` (broken ones never contacted), only verified businesses whose agent card subscribes to new postings, signed offers in (only from invited businesses, fresh, for this request, still valid); it decides nothing. Formats as strict Pydantic models in one place. | `code/marketplace/` (:4010) |
| Bargaining (step 4) | Hotel side: the `counter_offer` tool, stateless like `book` (the counter carries the hotel's own signed offer and last counter), checks Tuttie's seals, signature, freshness and the user's `negotiate` delegation; the hotel meets halfway and never goes below its private floor or past its rounds, compared in code (`negotiation/rules.py`), never in a prompt or reply. Tuttie's side: one subagent per offer, all in parallel in their own sessions, counters signed with Tuttie's key, the private `max_price_chf` only compared in code; ends in a signed Agreement, a rejection or walking away; `best()` picks the cheapest agreement. Booking can redeem an Agreement (`AgreementRedeemer`: own signature, not expired, only once). Formats: `Counter` (+ `final`), `Agreement`, `Rejection`. Mounted in every node (`node/server.py`); Tuttie reaches it through its `negotiate` tool. | `code/negotiation/` |
| Tuttie's presence (hooks for the eyes) | One signal for the eye animations: the state (asleep, listening, speaking, typing, error, waiting, watching, negotiating, searching, booking, thinking, done, idle), voice levels ~20×/s and one-off cues (offer, agreement, scam_blocked, approved, booked, paid, ...), from mode, conversation, voice, approval and errors. Read with `usePresenceState` / `usePresenceEvents`, or `face.onPresence(event)`. The eyes are moved only by `lib/faceDirector.js` from that signal (looks per state, voice pulsing, reactions to cues); a new face with the same methods works as it is, one with `onPresence` animates it itself. Tests: `npm test` in apps/wallet. | `code/apps/wallet/src/lib/presence.js`, `hooks/usePresence.js`, wallet README |
| Weather and trains | Two sealed public information services on the agent web (gold): `get_forecast` (Open-Meteo) and `get_connections` (transport.opendata.ch), signed MCP tools, marked sample data without internet, signed refusals. Tuttie finds them in the registry and checks their answers like any node (rule 6 of its prompt; `READ_TOOLS`). Live-tested with the real LLM: "Will it rain in Basel on 14 Nov?" and "which train from Zürich before midnight" (IR 36, 22:36 → 23:52). | `code/services/`, `code/data/services/` |
| End-to-end run | The whole signed flow in one process with a simulated phone. | `code/scripts/demo_headless.py` |
| Dev tooling | `./run.sh` shows every service's log lines with its name, warns without an OpenAI key and stops everything within 3 s on Ctrl+C; `scripts/check.sh` runs the checks before a push (tests, wallet build, real flow; `--no-llm` without the LLM). | `code/run.sh`, `code/scripts/run_all.py`, `code/scripts/check.sh` |
| Wallet app | React + Vite PWA, phone-first: card stack, the Tuttie card is the agent's face (pycozmo eyes), asleep → tap to voice mode, text behind a keyboard icon, iOS-sheet swipe to close, keyboard-safe, installable. **Connected:** requests go to Tuttie; posting, offers, shortlist, bargaining and answer shown under its eyes; approvals in the wallet with a Face ID-style confirmation. | `code/apps/wallet/` |
| Owner view | React + Vite, one minimal page in the wallet's look, live from the business's node and **editable**: rooms (price, offered), extras (price), negotiation (on/off, lowest price, rounds), agent (name, tone, answers new requests). Its sidebar labels are Overview, Agent, Negotiation and Versions; Rooms and prices, Add-ons and Policies are removed. Edits are a draft in the browser; the owner reviews the changes in words and deploys; the node validates, stores the next numbered version and its tools, agent and bargaining limits use it from the next request (no restart). The node can change more (profile, policies, charges, rows) and keeps a version history (`GET /owner/versions`); the page shows neither on purpose. A stale draft cannot overwrite a newer deploy (409). Needs the owner token (`OWNER_TOKEN` in `code/.env`; unset = refused). Served at `/owner/` by the assistant; dev server on 4042. | `code/apps/owner/`, `code/node/owner.py`, `settings.py`, `deployments.py` |
| Hosting | Live at <https://web4.mendes.dev> on the team server, kept running by a systemd user service. | `code/deploy/tuttie.service` |
| Repo structure | BaselHack template, work-area folders with scope READMEs, team context folders, concept and architecture docs, draft marketplace formats. | `documentation/`, `code/*/README.md` |

## Pending

Build order from [goals.md](goals.md):

1. **Agents** — done: the three hotel agents (same agent object, personas, profiles, private
   limits), sessions with memory, Tuttie's identity and its parallel subagents. Tuttie signs
   its postings and counters with its own key.
2. **Agent layer of the marketplace** — done: Tuttie posts a signed request with only public
   needs (`post_request` tool, `assistant/marketplace.py`); the market wakes verified,
   subscribed businesses; interested agents send signed offers (`make_offer`, prices from the
   config); Tuttie re-checks every offer and builds the shortlist itself (verified, within the
   private budget, cheapest first, at most five). Live-tested end to end with the real LLM.
   Tests: `test_market_agents.py`, `test_tuttie_market.py`.
3. **Human layer in the wallet** — done: typed requests go to Tuttie; the wallet follows the
   timeline and shows the posting (budget private), the hotels asked and skipped, offers with
   seal colours and size, the shortlist, the bargaining and the answer under Tuttie's eyes;
   approvals happen in the wallet with a Face ID-style confirmation. Tested in a headless
   iPhone against a separate assistant instance with the real LLM. Missing: voice recognition.
4. **Negotiation** — done (dev member 2, `code/negotiation/`): `counter_offer` is mounted in
   every node and available; Tuttie's `negotiate` tool hands the shortlist to
   `TuttieNegotiator.negotiate_all` with the budget as a private item and shows `best()`'s
   signed Agreement. Tuttie negotiates only when the user asks for a better price. `book`
   redeems a hotel's signed Agreement once (`AgreementRedeemer`), and Tuttie books it with
   `use_agreement` after the user approves exactly the agreed price on the phone. Tests:
   `test_node_book.py`, `test_tuttie_market.py` (post → shortlist → negotiate → book).
   Tuned for the pitch story (Gästehaus am Rhein, CHF 135, budget 160: three visible rounds,
   agreed at CHF 128; Rheinblick still CHF 185; preview with `scripts/bargain_preview.py`). **Decided:** no `negotiation.counter` wake-up; counters go
   straight to the `counter_offer` tool. Done: no hotel's `wakes_on`
   lists `negotiation.counter` any more (`DEFAULT_WAKES_ON` never did). Anna offers the double
   with `late-arrival-dog` (CHF 135) for a dog guest: her config notes the single is too small
   for a dog. Verified headless: 135 → 121/131 → 126/130 → agreed 128 → approved → booked.
5. **MCP services** — done (goal 4), both sides:
   - **APS side (dev member 2):** signed calls (`aps/call.py`, C1), the action gate
     (`aps/gate.py`, C2; Tuttie's delegation grants `book`), payment mandates
     (`aps/mandate.py`, C3), `counter_offer` as an MCP tool (`negotiation/hotel.py`, C4).
   - **Nodes, Tuttie, wallet (dev member 1):**
     - Every node serves `get_availability`, `get_policies`, `book`, `pay` and
       `counter_offer` over MCP at `/mcp/` (`node/mcp_tools.py`, `mcp==2.3.0`, stateless,
       JSON); the HTTP `/tools/*` routes for the first three are gone.
     - `book` and `pay` on the node compute their own amount and run only through the
       gate, then `commit`; the signed confirmation / receipt lists the passed `checked`.
     - Hotels list `facts.charges` (city tax CHF 4) in their signed policies; `pay` collects
       one charge once per booking, with the user's mandate or approval.
     - Tuttie calls tools through `assistant/mcp_client.py` behind its trust gate and signs
       action calls (`Toolbox.signed_call`). The booking approval offers a mandate for the
       city tax; if the user allows it (switch on the wallet's approval sheet), the user's
       key signs it and Tuttie pays the tax right after the booking (`may_auto_pay`), no
       second prompt. Otherwise the charge stays open and `pay` asks on the phone.
     - The wallet's booking card lists what Tuttie checked about the hotel ("Checked by
       Tuttie": its verified seals, the hotel signed the agreed price / extras, the hotel
       signed the booking, approved by you) and the paid city tax. The gate's own `checked`
       (caller, signature, delegation, ...) stays in the signed confirmation.
   - Tests: `test_node_book.py`, `test_node_pay.py`, `test_tools.py`,
     `test_tuttie_market.py`; in-process MCP helpers in `tests/mcp_helpers.py`. Headless
     story: 135 → 128 agreed → approved → booked through the gate → city tax CHF 4 paid
     with the mandate.

### Who works on what

| Area | Owner | Others |
| --- | --- | --- |
| APS: signing, seals, UIDs, delegations, freshness (`code/aps/`) | dev member 2 | only use it; changes go through its owner |
| **Bargaining (step 4):** the `counter_offer` tool on the hotel side, the logic that keeps hotels within their private limits (`facts.negotiation`), how Tuttie's subagents negotiate in parallel in their sessions, using the `Counter` format | dev member 2 | don't touch `counter_offer`, `Counter` or negotiation logic |
| Company agents, `make_offer`, sessions, subagents (`code/node/`, `code/sessions/`, `assistant/subagents.py`) | dev member 1 | tell the owner before changing them; bargaining builds on top of them |
| Marketplace (`code/marketplace/`) | dev member 1 (aligned with the concept) | tell the owner before changing it |
| Tuttie on the marketplace (`assistant/marketplace.py`, `post_request` and `negotiate` tools) and the wallet's human layer (`code/apps/wallet/`) | dev member 1 (wallet in progress) | tell the owner before changing them |

### Dos and don'ts for parallel work

- **Do** `git fetch` and rebase or merge before you start, and again before you push; we both
  work on `main`. Never force-push.
- **Do** stay inside the agreed step of the build order (goals.md). If something outside it
  looks useful, write it under "Pending" and ask first instead of building it.
- **Do** add an integration test when two areas meet (e.g. `test_market_agents.py`: the real
  market against the real agents). Tests against fakes alone missed a body-format mismatch.
- **Do** update this file in the same change, including "Who works on what".
- **Don't** change another owner's files without telling them first.
- **Don't** build a second version of something listed here as done or owned; extend it.
- **Don't** let the marketplace decide for the user: it checks and relays signed messages;
  Tuttie builds the shortlist.

### Where to start next

1. **dev member 1:** step-3 check-in with the pitch and design team (the wallet now shows the
   whole run); then voice (`code/voice/`) or the demo runner (`code/demo/`), whichever the
   pitch needs first.
2. **dev member 1:** done: M1–M5 and `pay` (see step 5 above); the double-charge race in
   `pay` is fixed (64197e9, `test_node_pay.py`).
3. **dev member 2:** **Confirmed live** (real LLM, `demo_headless.py`, 2026-10-31): the pitch
   request "quiet hotel in Basel, arriving after midnight, with my dog, under 160" gives
   Gästehaus 135 → 121/131 → 126/130 → agreed CHF 128 → approved → booked (caller, signature,
   delegation, agreement, approval) → city tax CHF 4 paid with the mandate. Next: check with the pitch team where `pay` happens in the story (e.g. city tax
   with a mandate, under CHF 10, no phone; above that the phone asks); then check the tuned story with the pitch team (`scripts/bargain_preview.py`,
   numbers in formats.md) and confirm it live with the real LLM
   (`scripts/demo_headless.py approved "<a request that asks for a better price>"`; needs
   `code/.env`). The stage numbers are pinned in `test_the_pitch_story_anna_s_guesthouse`; if
   they have to change, tell the pitch team.
4. **Check-in with the pitch and design team** after these steps; agree the marketplace
   formats as a team and update formats.md + `marketplace/messages.py` together.

**Review of owner view and voice (dev member 2, 2026-10-31, commits 8763423..6819267):** all
299 tests green, owner view's JS tests and build green, the pitch story still runs live
(128, booked, city tax with the mandate). Owner backend (`node/owner.py`, `settings.py`,
`deployments.py`) is solid: strict validation, floor ≤ room price, atomic versioned writes,
constant-time token check, tests isolated from local deploys; `negotiation/hotel.py` now reads
the owner's limits live, once per answer (fine). Open points, none blocking:
- **Before the pitch:** owner deploys persist (`data/deployments/`, also on the team server)
  and change the stage numbers. Check `GET /owner/versions` on the server, or remove the
  folder, before the demo; `test_the_pitch_story_anna_s_guesthouse` only covers the committed config.
- The owner page on the live site cannot reach a node (port 4009 is closed to the internet,
  which is right): it works locally only. To show it from the live site, proxy it under the
  site's origin, still behind the token.
- One `OWNER_TOKEN` for every node: any owner could read and change every hotel's private
  limits. Fine for the demo; real owners would sign deploys with their own key (APS).
- `assistant/voice.py`: `agent_only` compares the secret with `!=`; use
  `secrets.compare_digest` like `node/owner.py`. `voice_rooms` grows with every
  `POST /voice/token` (no login needed) and is never pruned.
- `requirements.txt` gained `livekit`: run `uv pip install -r requirements.txt` (or pip)
  after pulling, or the assistant and three test files fail to import.

### Test coverage

326 tests, all green (`pytest -q`), no network and no LLM (plus `npm test` in `apps/owner` for the settings helpers): `test_node_owner.py` (the owner endpoints: token, validation, deploy goes live in every tool, versions, restart, stale deploys, CORS only on `/owner`), `test_aps.py` (signing, freshness,
seals, tiers, UIDs, approvals, delegations), `test_node_book.py` (node `book`: approval, commitments, replay), `test_node_agent.py` (the
company agent with a fake LLM, private facts, read tools, the three hotel configs),
`test_business_agent.py` (same agent object, persona, tool catalog, card, wake-ups),
`test_sessions.py` and `test_agent_sessions.py` (session memory, isolation, context levels,
parallel subagents against the real node apps), `test_marketplace.py` (postings, wake-up,
offers, shortlist, strict formats, HTTP service), `test_market_agents.py` (the real market
waking the real company agents, which send signed offers back), `test_tuttie_market.py` (Tuttie
posting, its own shortlist with a private budget, negotiating the shortlist), `test_negotiation_rules.py` (limits, counters toward the guest, never below the floor),
`test_counter_offer.py` (the hotel tool on the real node app: signatures, delegation, limits
never in replies), `test_negotiation_flow.py` (real market offers, then Tuttie's subagents
bargain in parallel), `test_agreement.py` (redeeming signed agreements once, from the real
counter_offer tool), `test_negotiation_edges.py` (refusals mid-negotiation, Tuttie's round
cap, unreachable registry, signed non-object payloads), `test_registry.py` (search, records,
live reload), `test_marketplace_edges.py` (unknown or broken requesters, unverifiable agent
cards, odd wake-up replies), `test_tools.py` (assistant trust gate and Tuttie's identity,
with mocked HTTP and the real demo keys), `test_call.py` (signed calls: tampering, time window, nonces), `test_gate.py` (the action gate: one refusal test per missing signature, agreement and approval used once), `test_counter_offer_mcp.py` (counter_offer over a real MCP server: same replies as HTTP, the pitch rounds), `test_mandate.py` (payment mandates, auto-pay only to gold/blue and ≤ CHF 10, `pay` through the gate).
Coverage (`pytest --cov`, with `pytest-cov` installed locally): 92 % overall; `aps/` and
`negotiation/` 100 %, `marketplace/` 97 %, `node/` 93 %. Lowest: `llm.py` 44 %, `assistant/agent.py`
56 %, `assistant/events.py` 56 % (the real LLM loop and SSE streaming, not run in tests; checked by `demo_headless.py`).

Other open items: voice agent (`code/voice/`), the demo runner (`code/demo/`), owner view
presentation site and QR code (`code/apps/presentation/`), a
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

- **The owner view reads and changes the node, behind a token.** The live data comes from the
  node's own config (`node/owner.py`), not from the signed public tools, because add-ons and the
  private negotiation limits are not public. The nodes' ports are open on the team server, so the
  endpoints need `OWNER_TOKEN` and refuse everyone when it is unset; it is a stand-in for the
  owner's own key. Cross-origin access (token in a header, no cookies) is limited to the
  `/owner` routes, which are their own small app mounted on the node.
- **Deploying = a new version of a slice of the config, applied live.** What an owner may change
  is `node/settings.py` (strict Pydantic models: prices are whole francs, unknown fields are
  errors, the floor cannot exceed the standard room's price); everything sealed, the tools and
  the persona's boundaries stay fixed. Versions are `data/deployments/<node_id>.json`
  (git-ignored runtime state, `node/deployments.py`); version 0 is the committed config, which
  is never rewritten. The node applies the latest version over a *copy* of its config at start
  and after each deploy: `create_app` works on that copy, tools read `facts()` per call,
  `BusinessAgent.apply` re-reads persona and facts, and `CounterOfferTool.limits` / `add_ons`
  are properties, so no restart or rebuilt router is needed. A deploy carries the version it
  started from (`base_version`); a stale one gets 409. A damaged deployment file stops the node
  at start: it must never run with other prices than the owner deployed. Rolling back is
  deploying an old version again, so history only grows. Drafts live in the owner's browser.
    Tests never read the machine's real deployments: `tests/conftest.py` points `OWNER_DATA_DIR`
    at a temporary folder (a deploy made while trying the owner view once broke two unrelated
    tests). Facts the owner view does not edit yet (`photos`, `rating`, `amenities`) are kept as
    they are by every deploy.
- **Bookings and offers made before a deploy:** `book` without an agreement uses the room's
  *current* price, so a user approval for the old price no longer matches and the gate refuses
  it; offers, agreements and commitments are signed with their own `valid_until` and keep their
  prices.

- **MCP actions are signed calls through one gate.** Reading tools stay unsigned on the way in
  (their answers are signed); actions need the caller's signature over tool + args, so an
  approval or agreement in the args cannot be swapped. Nonce + 300 s window instead of a
  stored call log: a nonce only has to be remembered while its call is fresh. The gate takes
  the caller's key from the registry, never from the call, and refuses grey callers ("no
  signature, no action"). Checks use nothing up; `commit` does, after the action succeeded,
  so a failed booking does not burn the user's approval. APS does not import the
  negotiation code: the node passes its `AgreementRedeemer` in.
- **`book` is a delegation scope, paying is not.** The scope says Tuttie may book for the
  user at all; each booking still needs the user's signed approval for its amount.
- **Small payments by mandate, not by scope.** A mandate is the user's own signature for one
  agent, one payee, one purpose, a total and an expiry; one payment with it is at most CHF 10
  and only to gold/blue businesses. So a stolen or confused agent can lose at most what the
  user signed for that one business, never pay an untrusted one without the phone.

- **Bargaining is code, not LLM.** Both sides decide prices with deterministic rules
  (`negotiation/rules.py`, `negotiation/tuttie.py`): the hotel meets halfway and never goes
  below its floor; Tuttie opens 10 % below and moves halfway, within the private budget. An
  LLM could leak a limit or invent a price; code can be tested for both.
- **Strategy tuned for a visible story, not maximum savings:** with a 15 % opening and halfway
  hotel steps, the hotels hit their floor in round 1 and the bargaining ended after two
  rounds, for Gästehaus am Rhein (the pitch winner) at exactly Anna's private floor of
  CHF 125, which would effectively reveal it on stage. A 10 % opening and a hotel that moves
  a third of the way give three rounds: Gästehaus agrees at CHF 128, Rheinblick still at 185.
- **Signed is not the same as well-formed.** A signed envelope with a list or string payload
  crashed `counter_offer` (HTTP 500) until `message()` refused non-objects; every parser of a
  signed payload must handle that.
- **`counter_offer` is stateless.** The guest agent sends the hotel's own signed offer and
  last counter with each round, so the hotel only trusts its own signatures for earlier
  prices (like `book` with commitments). No negotiation state can be lost on restart or
  forged; replaying an older round gains nothing.
- **`floor_chf` is for the standard double room**; other rooms drop by the same share and
  add-ons are never discounted, so one number per hotel is enough for every offer.
- **Tuttie's budget limit is the private context item `max_price_chf`**, the same key the
  subagent tests use; it is compared in Tuttie's code and never put in a subagent's context.

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
- **Marketplace built against the draft formats** to save time until Sunday 12:00, not
  after a full team round. All formats live in `code/marketplace/messages.py` (strict:
  unknown fields are refused) so changes stay cheap; formats.md is updated with every change.
- **The marketplace never decides and never prices.** It only checks signatures and stores
  signed offers; Tuttie picks. Woken businesses get Tuttie's signed request unchanged, so
  they verify the requester themselves. Grey businesses are invited and may offer (shown,
  ranked last), but can never be booked.
- **Private facts never reach an LLM.** The node's agent used to get all `facts` in its
  prompt; with negotiation floors in the config that would leak them to any agent that asks
  cleverly. `PRIVATE_FACTS` in `node/agent.py` keeps them out of the prompt and out of every
  tool reply. Add any new owner-only fact there.
- **Hotel sizes are in `facts.profile`, not in tags or seals:** owners can edit them without
  new seals. The demo prices and the dog storyline (Rheinblick, CHF 180 + 15) are unchanged.
- **Freshness is opt-in per call.** Live replies must be at most 300 s old
  (`MAX_REPLY_AGE_S` in `assistant/tools.py`); stored envelopes like commitments are
  verified without it because they have `valid_until`.

- **LLM:** Claude Haiku 5.5 without thinking for Tuttie and the hotel agents (`LLM_MODEL`,
  `AGENT_LLM_MODEL` = `claude-haiku-5-5`, key `ANTHROPIC_API_KEY`): `code/llm.py` picks the
  Anthropic Messages API for `claude-*` names, otherwise the OpenAI **Responses API**. Measured
  per Tuttie round: Haiku ~0.9-1.3 s, gpt-5.1 (effort none) ~1.2 s, gpt-6-luna with thinking
  ~2-3 s; all run the story right. `gpt-4.1-mini` once dropped rules in the full flow.
- **Structure beats prompting.** When the model misbehaved, fixing the tool contract worked
  better than longer prompts: search results split into `verified` / `rejected`, an enum for
  `capability` (the model invented values like "hotel_booking"), booking totals computed only
  from signed facts, commitments built from fixed `add_ons` in the node config.
- **Place tags:** every Basel hotel carries the city tag `basel`; `post_request` only posts
  `basel-sbb` or `kleinbasel` when the user names that area. With `basel-sbb` the Gästehaus am
  Rhein (Kleinbasel) was never woken, so the pitch story (Anna wins) could not happen.
- **Wallet face while busy:** in the thinking, posted, negotiating and booking phases the eyes
  move through a few thinking looks with glances (`THINKING` in `lib/activity.js`).
- **Seals in the wallet** (`apps/wallet/src/components/Seals.jsx`): issuer marks instead of
  dots. Gold = Swiss flag, "Handelsregister · Basel-Stadt" and the business's UID (timeline
  events carry `uid`; shown only inside a valid gold seal); blue = Adobe logo and name. Tap a
  hotel for its seals as an iOS-style grouped list with a checkmark-seal badge; the approval
  sheet shows them too. Businesses never asked are listed: forged seal in red, no valid seal
  grey and struck through.
- **User context** (`assistant/context.py`, `data/users/alex-muster.json`): Tuttie's first tool
  `recall_context` reads the user's location, messages, mail, calendar and preferences (demo
  data, each item public / negotiation / private), so "I want to book something" is enough:
  Basel, night of 14 Nov, arriving ~01:00, with the dog Luna, quiet, budget CHF 160 (private,
  only in `budget_chf`). The wallet's context line shows "Checking location → messages → mails →
  calendar", then "Checked your location, messages, mails and calendar".
- **Swipe cards** (wallet `Deck.jsx` + `assistant/cards.py`): `post_request` posts, collects the
  offers, bargains with the hotels to show (budget private), then shows up to 5 cards: photos
  (tap left/right to flip, Unsplash, `apps/wallet/public/hotels/`), seals, ★ rating, a row of
  5 feature icons (green yes / red no, needs first) and the agreed price with the offer crossed
  out. Swipe right = like, left = pass; the first card nudges once to show it can be swiped,
  and Tuttie's eyes follow the drag. Up/down drags scroll the conversation. After the last card
  the wallet sends the cheapest liked deal with `first_tool: "book"`; the user approves as
  usual. `scripts/demo_headless.py` likes the recommended cards like the wallet.
- **Progress lines:** each turn shows two joined lines that update in place and wrap downwards:
  context, then tools (asked N hotels → offers in, checking seals → comparing → bargaining →
  N hotels for you; later booking, booked).
- **One conversation at a time, history on the device:** no sideways gestures on Tuttie's
  card. A dock under the open card has three buttons: history (earlier conversations, kept in
  `localStorage`, `lib/history.js`), new chat, and the keyboard. Swiping Tuttie down and opening
  it again archives it and starts fresh (`POST /conversations`), unless a request or approval
  waits. Reload keeps the selected conversation (`GET /history`, `X-Conversation-ID`).
  History → Continue chat selects the retained server assistant (`POST /conversations/{id}/resume`);
  old or expired entries stay read-only. Saved conversations are in memory, capped at 200
  globally in addition to the 200 active browser conversations; a restart expires them. The
  user's own words are not shown; businesses with forged or missing seals are never shown either.
- **Voice** (`code/voice/`, `assistant/voice.py`, wallet `hooks/useVoice.js`): self-hosted
  LiveKit 1.13.11 + LiveKit Agents 1.8.10 with ElevenLabs (Scribe v2 realtime, Flash v2.5).
  While Tuttie's card is open the wallet is in a LiveKit room; speech becomes a message to the
  same Tuttie conversation (all tools run as when typing), answers are spoken; concise (short
  confirmation, answer, Face ID prompt only). Signaling is proxied through the assistant (`/rtc`,
  forwards the token header), media on TCP 4042 / UDP 4043. Verified end to end through
  https://web4.mendes.dev with a spoken request. See `code/voice/README.md`.
- **Voice in the wallet:** answers appear word by word as Tuttie speaks them; a typed message
  makes Tuttie quiet (text only) until its face or the mic button is tapped; the dock has a mic
  mute button; the user can interrupt any time (two or more words); a fitting filler only when Tuttie starts a tool. Voice "Germain" on the demo. Amounts are spoken in francs.
- **Speed:** company agents use a fast model without thinking (`AGENT_LLM_MODEL`, Haiku on the
  demo, default gpt-4.1-mini, `node/agent.py`); the add-ons a request needs (dog, late arrival, children) are
  chosen in code (`add_ons_for`), so every fee is in the offer whatever the model picks. Context
  reading paced at 0.15 s per source. Voice uses ElevenLabs Flash. The wallet joins the voice room
  ahead (mic off), so opening the card only turns the mic on. Spoken request to answer: ~8 s.
  `AGENT_LLM_MODEL` is read when needed: `node/agent.py` is imported before `.env` is loaded.
- **Hotel offers in one call:** for a new posting the hotel agent decides and chooses its offer
  (room, add-ons) in one LLM call (`WAKE_OFFER_PROMPT`, `offer_choice` kept out of the signed
  reply); offers reach the guest ~1.3 s sooner (answer ~5 s after the context in a headless run).
- **Voice fixes after the presence/history merge:** the wallet joins the voice room only once
  the conversation is loaded (`useVoice(..., conversationId)`): a token fetched in parallel with
  the first `/history` created a second session, so speech went into a conversation the screen
  did not show (409 on `/events`). LiveKit runs with `singlePeerConnection: false` (classic
  publish + subscribe connections): iPhones joined the room but never sent an ICE check with the
  single connection. Chromium verified end to end (fresh browser, spoken request -> answer);
  Firefox can't be tested headless (no audio device).
- **iPhone voice:** Safari sets up WebRTC connections only while the page uses the microphone.
  Joining the room ahead with the mic off left iPhones stuck in ICE "checking" (no checks, no
  relay allocation; wallet report `closed while checking`). The first tap now captures the mic,
  then joins; the room stays joined while the card is closed (mic released,
  `stopMicTrackOnMute`), so later opens are instant.
- **Voice on phones:** ICE from phones failed (no UDP into the team server; iPhones don't use
  plain TCP). A coturn relay on TCP 4044 (`code/voice/turnserver.conf`, started by run_all when
  `TURN_SECRET` is set) carries their audio; LiveKit hands it to clients. Relays only to the
  server's own IP; no certificate needed. Verified with a relay-only client.
- **Posting tags:** only the city (`basel`); an area went into tags and hid the guesthouse in
  Kleinbasel (the train arrives at Basel SBB). Offers wait up to 45 s (stops when all offered).
- **Tasks in words, the rest in the eyes:** the line under the eyes shows only what Tuttie is
  doing right now (`currentTask`: "Checking calendar", "2 offers in · checking seals", "Agreed
  with …", "Waiting for your approval", "Booking…") or an error; it is empty while Tuttie only
  listens or thinks. The eyes carry that: listening looks with small glances and a nod while
  waiting, thinking looks while busy, looking down at the cards while the user swipes (and
  following a dragged card), the answer's mood for a few seconds, then listening again
  (`LISTENING`, `WATCHING`, `THINKING` in `lib/activity.js`).
- **Minimal booking and approval:** the approval sheet shows the hotel, the amount, its seals and a
  short "Also pay city tax (CHF 4)" switch; the booking card shows hotel, price, date and booking
  id, one line for the paid city tax, and "Checked by Tuttie" folded into one line that opens.
- **Tuttie's priorities** (`assistant/agent.py`): what the user says now beats their saved
  context, preferences, budget and Tuttie's own recommendation ("book it anyway" is booked,
  with the phone approval as the final word); then safety on the agent web; then the context;
  then Tuttie's judgement. Verified headless: an over-budget hotel the user insisted on was
  booked after approval.
- **Answer mood:** Tuttie ends every answer with "Mood: <mood>" (`MOODS` in
  `assistant/agent.py`); `split_mood` strips it and the answer event carries `detail.mood`. The
  wallet shows it on the face (`MOOD` in `lib/activity.js`), so small talk has expressions too.
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
- **One conversation per browser:** the assistant gives every browser a `tuttie_session`
  cookie (`assistant/app.py`) and keeps a `Conversation` per session
  (`assistant/conversations.py`: own assistant, timeline, approvals, chats; at most 200, the
  least recently used is dropped; in memory, so a restart starts everyone fresh). `/chat`,
  `/events`, `/reset` and `/approvals` only touch the caller's conversation; hotels, marketplace
  and registry stay shared. Each person's run uses the real LLM (cost). For automated tests
  prefer `scripts/demo_headless.py`.
