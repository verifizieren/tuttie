# Status: done, pending, conventions

The shared state of the project, for teammates and for AI coding agents working with us.
**Read this first, and update it in the same change** whenever you finish something, start
something big, or make a decision others need to know. Goals and build order:
[goals.md](goals.md); concept: `documentation/concept.md`; work areas:
`documentation/architecture.md`; formats: `documentation/formats.md`.

Last updated: 2026-10-31 (bargaining tuned for the demo, coverage gaps closed) (bargaining, step 4: counter_offer within private limits, Tuttie's parallel negotiating subagents).

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
| Marketplace (agent layer) | Built against the draft formats: Tuttie's signed postings in (seals, freshness, user delegation `post_requests`), matching businesses woken in parallel at `POST /agent/invoke` (broken ones never contacted), only verified businesses whose agent card subscribes to new postings, signed offers in (only from invited businesses, fresh, for this request, still valid); it decides nothing. Formats as strict Pydantic models in one place. | `code/marketplace/` (:4010) |
| Bargaining (step 4) | Hotel side: the `counter_offer` tool, stateless like `book` (the counter carries the hotel's own signed offer and last counter), checks Tuttie's seals, signature, freshness and the user's `negotiate` delegation; the hotel meets halfway and never goes below its private floor or past its rounds, compared in code (`negotiation/rules.py`), never in a prompt or reply. Tuttie's side: one subagent per offer, all in parallel in their own sessions, counters signed with Tuttie's key, the private `max_price_chf` only compared in code; ends in a signed Agreement, a rejection or walking away; `best()` picks the cheapest agreement. Booking can redeem an Agreement (`AgreementRedeemer`: own signature, not expired, only once). Formats: `Counter` (+ `final`), `Agreement`, `Rejection`. Mounted in every node (`node/server.py`); Tuttie reaches it through its `negotiate` tool. | `code/negotiation/` |
| End-to-end run | The whole signed flow in one process with a simulated phone. | `code/scripts/demo_headless.py` |
| Wallet app | React + Vite PWA, phone-first: card stack, the Tuttie card is the agent's face (pycozmo eyes), asleep → tap to voice mode, text behind a keyboard icon, iOS-sheet swipe to close, keyboard-safe, installable. **Connected:** requests go to Tuttie; posting, offers, shortlist, bargaining and answer shown under its eyes; approvals in the wallet with a Face ID-style confirmation. | `code/apps/wallet/` |
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
   straight to the `counter_offer` tool. **Request to dev member 1:** drop
   `negotiation.counter` from the hotels' `wakes_on` (configs) and from `DEFAULT_WAKES_ON`
   (`node/agent.py`) so no agent card promises an event nothing sends.
5. **MCP services** — not started.

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
2. **dev member 2:** check the tuned story with the pitch team (`scripts/bargain_preview.py`,
   numbers in formats.md) and confirm it live with the real LLM
   (`scripts/demo_headless.py approved "<a request that asks for a better price>"`; needs
   `code/.env`). The stage numbers are pinned in `test_the_pitch_story_anna_s_guesthouse`; if
   they have to change, tell the pitch team.
3. **Check-in with the pitch and design team** after these steps; agree the marketplace
   formats as a team and update formats.md + `marketplace/messages.py` together.

### Test coverage

163 tests, all green (`pytest -q`), no network and no LLM: `test_aps.py` (signing, freshness,
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
with mocked HTTP and the real demo keys).
Coverage of `aps/`, `registry/`, `marketplace/`, `negotiation/`: 98 % (`pytest --cov`, with
`pytest-cov` installed locally). Not covered yet: the assistant's LLM loop (`assistant/agent.py`) and its HTTP
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

- **LLM:** `gpt-6-luna` through the OpenAI **Responses API** with reasoning on
  (`code/llm.py`). Reasoning models only allow tools together with reasoning there;
  `gpt-5.6-luna` did no reasoning at its default and gave no summaries; `gpt-4.1-mini`
  dropped rules in the full flow. Only `llm.py` would change for another provider.
- **Structure beats prompting.** When the model misbehaved, fixing the tool contract worked
  better than longer prompts: search results split into `verified` / `rejected`, an enum for
  `capability` (the model invented values like "hotel_booking"), booking totals computed only
  from signed facts, commitments built from fixed `add_ons` in the node config.
- **Place tags:** every Basel hotel carries the city tag `basel`; `post_request` only posts
  `basel-sbb` or `kleinbasel` when the user names that area. With `basel-sbb` the Gästehaus am
  Rhein (Kleinbasel) was never woken, so the pitch story (Anna wins) could not happen.
- **Wallet face while busy:** in the thinking, posted, negotiating and booking phases the eyes
  move through a few thinking looks with glances (`THINKING` in `lib/activity.js`).
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
