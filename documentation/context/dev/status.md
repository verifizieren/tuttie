# Status: done, pending, conventions

The shared state of the project, for teammates and for AI coding agents working with us.
**Read this first, and update it in the same change** whenever you finish something, start
something big, or make a decision others need to know. Goals and build order:
[goals.md](goals.md); concept: `documentation/concept.md`; work areas:
`documentation/architecture.md`; formats: `documentation/formats.md`.

Last updated: 2026-10-31.

## Done

| Area | What works | Where |
| --- | --- | --- |
| APS signing | Canonical JSON, Ed25519 keys, signed envelopes with an optional freshness check (the assistant drops node replies older than 5 min as replays), seals with gold / blue / grey / broken tiers, Swiss UIDs (check digit) bound into every seal and verified only by the commercial register's seal, signed user approvals, user delegations (the user's key signs which scopes an agent may use for them; paying is never delegated). | `code/aps/`, `code/tests/` |
| Registry | Search by tags and capability, sealed records. | `code/registry/` |
| Business nodes | Signed tools (`get_availability`, `get_policies`), `book` (only with the user's signed approval for exactly the right total, no replays), own A2A agent whose LLM only picks a priced add-on from the config. | `code/node/`, `code/data/nodes/` |
| Demo data | Hotels Rheinblick (gold + blue), Spalenhof (blue), Gundeli (gold only, family rooms), Basel Budget Rooms (unsigned → untrusted), basel-cheap-hotels (forged seal → broken); a licensed lawyer (gold) and a self-signed fake lawyer (untrusted). | `code/data/nodes/` |
| User's agent | LLM tool loop with the trust gate: search, signed facts, A2A commitments, booking with phone approval, cited answers, reasoning summaries as "thinking". Own identity: Tuttie (`ch.tuttie.alex-muster`) has its own key, an Adobe (blue) seal and the user's signed delegation; `GET /identity` returns it checked. | `code/assistant/`, `code/data/agents/` |
| End-to-end run | The whole signed flow in one process with a simulated phone. | `code/scripts/demo_headless.py` |
| Wallet app | React + Vite PWA, phone-first: card stack, the Tuttie card is the agent's face (pycozmo eyes), asleep → tap to voice mode, text behind a keyboard icon, iOS-sheet swipe to close, keyboard-safe, installable. **Not connected to the backend yet.** | `code/apps/wallet/` |
| Hosting | Live at <https://web4.mendes.dev> on the team server, kept running by a systemd user service. | `code/deploy/tuttie.service` |
| Repo structure | BaselHack template, work-area folders with scope READMEs, team context folders, concept and architecture docs, draft marketplace formats. | `documentation/`, `code/*/README.md` |

## Pending

Build order from [goals.md](goals.md):

1. **Agents** — mostly done; missing: the three hotel agents in the planned sizes (big chain
   branch, mid-sized, small independent). Tuttie's identity is done; it does not sign its own
   outgoing messages yet.
2. **Agent layer of the marketplace** — not started (`code/marketplace/`, draft formats in
   `documentation/formats.md`).
3. **Human layer in the wallet** — not started: postings, offers and approvals in the wallet;
   connect the wallet to `POST /chat`, `GET /events` and the approvals API.
4. **Negotiation and subagents** — not started.
5. **MCP services** — not started.

### Where to start next

1. **Finish step 1 (small, data first).** Reshape the three hotels into the planned sizes in
   `code/data/nodes/` (e.g. Rheinblick = branch of a chain, Spalenhof = mid-sized, Gundeli =
   small independent), give each `facts.add_ons` and `facts.negotiation`
   (`floor_chf`, `max_rounds`). Re-run `issue_seals.py` if capabilities or keys change.
2. **Tests for `node/agent.py`** with a fake LLM: the commitment is built from the config,
   unknown add-on ids give no commitment, and the fallback reply on LLM errors. Offers in step 2
   reuse this logic, so it should be pinned down first.
3. **Then step 2:** agree on the draft marketplace formats in `documentation/formats.md`,
   then build `code/marketplace/` (:4010) test-first in the same style as `test_tools.py`.
   APS is ready for it: Tuttie signs requests with its own key, and businesses check its
   delegation (`verify_delegation(..., scope="post_requests")`) before answering.
4. **Wallet:** show Tuttie's verified identity on its card from `GET /identity` (proxied in
   the Vite dev server).

### Test coverage

45 tests, all green (`pytest -q`), no network and no LLM: `test_aps.py` (signing, freshness,
seals, tiers, UIDs, approvals, delegations), `test_node_book.py` (node `book`: approval, commitments, replay),
`test_tools.py` (assistant trust gate and Tuttie's identity, with mocked HTTP and the real
demo keys).
Not covered yet: `node/agent.py`, the node's `get_availability`, `get_policies` and `/agent`
endpoints, `registry/app.py`, the assistant's LLM loop (`assistant/agent.py`) and its HTTP
routes (`assistant/app.py`).

Other open items: voice agent (`code/voice/`), the demo runner (`code/demo/`), owner view
(`code/apps/owner/`), presentation site and QR code (`code/apps/presentation/`), a
behind-the-scenes view of the signed timeline, team names in `license.txt` and the team
profiles in the readme.

## Conventions

- **One app.** The wallet is the real product; the demo is a run through it. Never build
  separate demo screens. In repo files say "demo", not "scripted demo".
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
