# Status: done, pending, conventions

The shared state of the project, for teammates and for AI coding agents working with us.
**Read this first, and update it in the same change** whenever you finish something, start
something big, or make a decision others need to know. Goals and build order:
[goals.md](goals.md); concept: `documentation/concept.md`; work areas:
`documentation/architecture.md`; formats: `documentation/formats.md`.

Last updated: 2026-11-01 (QR page: two-layer web vision and stacked-card diagram; light design for wallet, QR page and pitch deck; decks at `/pitch/` (Sebastian's pitch); the demo runner is open).

## Done

- **QR page web vision (1 Nov)**: "One web. Two layers." now explicitly describes our vision
  of a new agent layer while existing websites stay the same. Replaced the flow diagram with
  two offset cards: a website in front and an illustrative agent code layer behind. Uses the
  existing guesthouse photo, purple accents and an updated screen-reader description.
- **QR page APS and agent web (1 Nov)**: ported the sections from `qr-aps` into the current
  `code/apps/qr/` site. "A fair chance." replaces the business heading and 7 / 220 room cards.
  "One web. Two layers." includes the responsive diagram and a nested APS explanation with
  a smaller heading and divider. Adapted to the current purple accents and no-eyebrow design;
  retained the 5 % fee, reverse marketplace, source figures, bank cards and story demo.
- **Design rules (1 Nov)**: black/white with blue #2f6fe0, purple #7a5af8, pink #e5489b accents, no
  orange, no italic, no small labels above headings, no URL text, pill buttons; the top seal tier is
  purple. Wallet, owner (now light), QR page and `/pitch/` follow them. The QR page has
  a story-style demo (tap left/right), one number per scroll, source logos and a reverse-marketplace section.
- **Keynote 2 removed (1 Nov)**: the live-demo deck (`code/apps/keynote2/`) is gone; the pitch uses `/pitch/`.
- **QR page speed (1 Nov)**: the two faces painted 60 frames a second even off screen (724 blurred
  draws in 3 s while reading the business part); now they paint only while visible. Fonts no longer
  block the first paint; two invisible nested backdrop blurs removed. Look unchanged (pixel compare).
- **QR page for technical readers (1 Nov)**: the first figure is now the NCSC's 58 % fraud share of
  35,727 Swiss cyber reports (H1 2025) instead of "2 in 3 have no website"; the +539 % has its baseline (2024 vs 2025 holidays,
  bars to scale, replacing the illustrative curve); a new "Under the hood" block says what is
  signed (seals, offers and agreements, delegation, approval, mandate, prices from signed data);
  the agency bar is set against Tuttie's 5 % commission per signed booking (CHF 6.75 on 135); "fakes never
  reach you" became "forged seals"; 7 vs 220 says why the small one won; a callout marks the
  read context as demo data. Details: `code/apps/qr/README.md`.
- **Light design (1 Nov)**: the wallet takes the `feature/tuttie-wallet-design` look (white Tuttie
  card, black glossy eyes with a catchlight, idle glances, ZKB and UBS bank cards) on a full light theme
  (page #f2f2f7, white panels, ink #17171d, Approve = dark button); a closed card rests awake with a
  neutral face, typing still closes the eyes; status bar `default`, `CACHE` v4. The QR page
  (`apps/qr`) and Sebastian's pitch deck (`code/apps/pitch`, served at `/pitch/`) use the same light design.
- **Round 11 (owner view)**: `?node=` is used only for the page's own host or localhost (the owner
  token never goes to a linked server); a deploy without an available room is refused, a left-out
  `facts.negotiation` keeps the live floor (the owner view sends `null` to end bargaining); public
  facts are capped at 8000 characters per hotel prompt; a stored version that fails today's checks is
  skipped (logged) instead of stopping the node and the whole service; the change list keys add-ons by `id`.
- **Round 10 (closing)**: a deploy reaches every phone on its next load (`Cache-Control: no-cache`
  on the apps' unhashed files, service worker fetches with `cache: "no-cache"`, `CACHE` v3; reload the
  presenter phone after a deploy anyway); a hotel's malformed signed session reply skips that hotel
  instead of sinking all bargaining (`assistant/subagents.py`); a free (CHF 0) signed add-on books. A hand-started stack without `AGENT_WEB_KEY` shares the keyless 10 postings/min across all users
  (run.sh/run_all.py always set a key). The service worker caches only successful answers. The action gate refuses calls and approvals stamped before
  it started (whole-second stamps), so nothing captured before a node restart books again. After a
  decline the very next yes books the offered hotel at once, for the room of its card offer
  (the cards summary names each card's room; a room the user asks for is still bookable). The private budget amount is dropped
  from answer phrases like "your CHF 160 budget" unless the user asks about the budget (`agent.without_budget`).
  A double tap on Send sends the words once (`lib/sendGuard.js`).
  The same message sent twice at once from two tabs (or a retype) joins the running turn on the server,
  and the wallet drops its local copy (`bindTurn`); card commands stay separate swipes.
  Private context never reaches a business: questions to a hotel (`ask_agent`) are refused and posted
  requirements dropped when they name a private place, person, train or time (`tools.private_terms`).
  Internal services listen on 127.0.0.1 by default now (`SERVICE_HOST`, set 0.0.0.0 only on purpose; the
  owner page's direct node fetch then works only on the server itself). A booking without a deal for
  another room than the liked card's gets one nudge back to the card's room; the cards turn's answer
  keeps two sentences. A booking is in the user's name unless said otherwise (Tuttie never asks for it).
  Internal services listen on 127.0.0.1 by default now (`SERVICE_HOST`, set 0.0.0.0 only on purpose; the
  owner page's direct node fetch then works only on the server itself). A booking without a deal for
  another room than the liked card's gets one nudge back to the card's room; the cards turn's answer
  keeps two sentences.
- **Red team round 9 (overnight, last review)**: a finger held across an approval sheet swap
  never decides the new sheet (capture-phase pointerdown tracker; VoiceOver taps, which send no
  pointerdown, are judged by click time); a sealed hotel's huge or non-number price never crashes
  the booking path (`tools.finite_price`/`chf`, the timeline shows "?"); `post_request` and `book`
  return `night` ("Saturday 14 November") and the prompt names a weekday only from it (Tuttie said
  "Friday" for a Saturday); answers say 24-hour times as people do on screen too ("12:52 am",
  `code/speech.py`, shared with the voice).
- **Red team round 7, exposure and gate** (branch `fix/r7-gate`):
  - Internal services (registry, marketplace, nodes, weather/trains) listen on `SERVICE_HOST` (`code/hosting.py`, default `127.0.0.1` since the end of the night); Tuttie on 4040 stays public. To close the public ports (the demo keys are public, so a reachable node takes forged approvals): add `SERVICE_HOST=127.0.0.1` to `code/.env`, then `systemctl --user restart tuttie` (run_all.py passes it to every service). Caveat: the owner page fetches `<host>:4009/owner/...` straight from the browser, so with loopback binding it only works on the server itself. The MCP Host-header check is off explicitly, so `http://localhost:<port>/mcp/` works either way.
  - The marketplace takes at most 10 keyless postings per requester a minute (only outsiders: wallet users post through Tuttie with the key) (429 + Retry-After) and keeps the newest 500. Tuttie's own postings carry the deployment's `X-Agent-Web-Key` and skip the cap, so an outsider with the public demo key cannot lock the wallet users out. Tuttie turns a busy (429), unreachable or non-JSON market into a calm tool error and never posts again in that turn; a market that times out while waking the hotels makes Tuttie say the hotels are slow and to ask again.
  - The action gate refuses an approval whose signed `decided_at` is over 900 s old or in the future (after a node restart an old approval no longer books again).
  - `registry_lookup` (negotiation/hotel.py) looks up only node-id-shaped ids and returns only dict records; `../search` gave a 500 on `/tools/counter_offer` and made the gate raise.
- **Round 6 (overnight)** (branches `fix/r6-trust`, `fix/r6-approval-sheet`, `fix/r6-voice`,
  `overnight/harden`, merged for testing on `overnight/integration`, not on main, not deployed):
  - Trust: a verified hotel's signed agent card and `get_policies` profile are type-checked and
    cleaned (`assistant/cards.py` `clean_text`/`profile_of`: agent name max 60 chars, profile
    `size` 20, `about` 500, no control or RTL/format characters; rating only as numbers), so a
    non-dict persona no longer crashes every search. The card is fetched once per hotel per
    search and the offer deadline is checked per offer; malformed relayed offers are dropped.
    `aps/canonical.py` `b64decode` accepts only canonical base64 and used commitments are keyed
    by signature bytes (a re-encoded signature could be redeemed twice).
  - Wallet approval sheet: finishes on the streamed `decided` event (approval id read from
    `detail.decision.approval_id`, existing shape) when the POST answer is lost; `decide()`
    gives up after 15 s (`DECIDE_TIMEOUT_MS`) and offers another try; New chat / History wait
    for a decision on its way instead of opening under the sheet. Booking message names the
    other liked hotels without card prices.
  - Voice: spoken turns have their own budget (`VOICE_TURNS_PER_SESSION_PER_MIN` = 20/min per
    browser); exact card commands count only towards `CARD_COMMANDS_PER_SESSION_PER_MIN` = 30/min
    and only while a card can be swiped (else they are normal voice turns); `/voice/diag` logs one
    clean line, max 10/min per address. `follow()` reconnects (0.5 s doubling to 10 s, stops on
    404/409) instead of going mute; while the Face ID sheet is up a spoken line gets "Please
    approve or decline on your phone first." (at most every 5 s) instead of queueing; Face ID is
    asked once per approval; node/approval/offer/mandate/request ids and web addresses are never
    read aloud; "for 00:52" is a clock time; CHF 1'280 (or 1 280 with a no-break space) is one
    amount, a plain space never joins two numbers ("CHF 128 100 percent"); no filler on swipes;
    no "swipe right" handoff line when the cards answer already says to swipe.
  - Tuttie (`overnight/harden`): Claude prompt caching of the fixed prompt + tools (`llm.py`,
    round notes stay an uncached second system block; ~90 % cheaper input, latency unchanged);
    after `recall_context` for a hotel it posts the request in the same turn; cards answer = pick
    + one reason; after booking only "booked" + total (the `book` result carries an LLM-facing
    `note`); after a decline one other hotel by name, no price; "yes, book that one" books
    without an agreement at the cheapest fitting rate; the budget amount is said only when the
    user asks for it. A hotel's signed confirmation never fills Tuttie's own `book` result keys
    (`node_id`, `source_step`, `note`, `charges_paid`, `open_charges`, `mismatch`); a non-number
    `total_chf` counts as a mismatch. After a decline Tuttie offers only a hotel the user's
    message named as liked (else it just stops). `/reset` also forgets the old posting and its
    offers (`MarketDesk.forget`).
  - Trust, numbers: NaN, Infinity and integers too big for a float never reach events or cards:
    `mcp_client` refuses an MCP reply holding them, `EventBus.emit` turns any non-finite float
    into null (SSE frames and `/history` stay valid JSON), `cards.number()` accepts only finite
    numbers (a 400-digit integer is no OverflowError), card ratings only 0..5, and an offer whose
    price is not a finite number is dropped.
  - Wallet sheet and cards (after the first pass): a `decided` event for an older approval never
    closes a newer sheet; the city tax sheet waits until the booking's checkmark was shown
    (`sheetOf`); a sheet replaced mid-decision tells the wallet, so no ghost sheet stays; the
    streamed decision also finishes the sheet after the 15 s timeout or a "gone" answer
    (`finishesOn`). A newly shown sheet ignores finger taps for 600 ms (`ARM_MS`, its slide-in),
    judged by the pointerdown time or, for assistive taps without one, the click time;
    `button.click()` (keyboard, keynote deck) always counts. Hotel cards pass through `cardOf`
    (shown fields are plain text, finite numbers or null; rating only 0..5); a late agreement
    whose price is not a number is ignored; long hotel names clamp to two lines.
  - Note: the LLM behaviour eval used overnight (real Haiku, 24 scenarios) lives outside the repo
    (`/home/baselhack/overnight/eval`). Left open: 24-hour times on screen, long answers outside
    the pitch path, re-dating after the cards.
- **Red team round 5, commitments and answers** (branch `fix/r5-commitments`): `ask_agent` shares the posted night (never the budget) and the hotel anchors a commitment's `valid_until` to noon after it, so Rheinblick after a Decline books with the dog/late-arrival extra; `drop_notes` drops only clear narration; all text parts are kept; an empty goodbye says "Bye, Alex! Enjoy Basel."; the model is told when no deals exist yet.
- **Wallet real-user test round 4** (branch `wip/r4d-wallet`, not deployed): a refused
  microphone (denied, missing, busy) now says "Microphone blocked — type instead" under the
  eyes and shows the dock mic as off; typing works, and a tap on the face or the mic asks for
  it again (no prompt loop; `lib/recovery.js` `micRefused`, `hooks/useVoice.js` `micBlocked`).
  A server restart that lost an unfinished chat (open question, approval or cards) archives it
  to History and says "Tuttie restarted — please ask again" until the next message
  (`lostOnRestart`). A booking approval puts the hotel cards away in every tab (it sets
  `picked`), so a second tab can no longer swipe a second booking after a Decline.
- **Real-user test round 4, Tuttie's turn** (branch `wip/r4d-backend`, not deployed): the
  user's own date, nights and party size beat the calendar ("tomorrow for 2 people" posts
  2 November, guests 2; the calendar only fills in what was not said, "I want to book
  something" still posts 14 Nov). `post_request` takes `guests` and `nights` and refuses in code
  a past night (Swiss today), a bad party size and more than one night (hotels book one night
  per booking), so Tuttie asks instead of booking something else. Only the answer reaches the
  user: `llm.py` keeps the text after the last tool call (last block / last message item) and
  `agent.py` `drop_notes` drops a leading paragraph about "the user". `negotiate` right after
  `post_request` in the same message returns its signed outcomes instead of bargaining twice;
  a new message or another budget bargains again. Open: hotels still offer a "double room" to
  5 guests (node side ignores `guests`).

- **Wallet red-team round 2 holes closed** (branch `wip/r2-wallet`, not deployed): booking
  terms (room, night, rate, included items) are short plain text before the user signs them
  (`aps/approval.py` `plain_term`, max 120 chars, same on hotel and assistant side), so a
  verified hotel's odd `rate` (an object) no longer reaches the phone; the wallet keeps only
  plain text and numbers in an approval and its seals (`lib/activity.js` `approvalOf`,
  `sealsOf`), and the approval sheet sits in an error boundary whose fallback still offers
  Decline. A stored deck / pick / turns in the wrong shape is dropped on restore
  (`validDeck`). "Tuttie is unreachable" from a failed send goes once the stream connects
  again. A broken stream frame is ignored (`lib/stream.js` `parseFrame`). The note under the
  hotel cards shows markdown as plain text (`plainMarkdown`). Hotel names in the book request
  (`lib/picks.js`) are one short line without brackets or quotes. Open: landscape layout of
  the hotel card (name overlaps the photo bars, "1 of 2" cut off).

- **Red team round 4, conversation store and throttle** (branch `wip/r4-conv`, not deployed):
  empty chats are never saved; above 200 saved chats one without approvals or agreements goes
  first, from the browser with the most, on a tie the one that saved last (bots, not the user
  who saved first). Above 400 active chats: offers-only before approvals/agreements (saved chats
  count), the most recently started session first; a session with saved chats is never
  "empty". `POST /conversations` is throttled (10/min per browser, 120 per address, 429). The
  per-address key of an IPv6 client is its /64. `/chat` counts a turn only after a valid body
  (422/409 no longer cost a turn). Conversation ids of dropped sessions never come back (the
  bounded memory raises a floor), and the throttle sweeps idle keys amortised. **Tell the team
  (formats.md):** `/conversations` 429; resuming an empty chat is a 410. Remaining: a patient
  bot can still create sessions early and use them later (N3 cannot be fully solved).
  Tests: `tests/test_r4_conversations.py`.
- **Red team round 4, hotel sessions** (branch `wip/r4-sessions`, not deployed): Tuttie never
  closed the hotel sessions it opened, so after 200 negotiations a hotel answered 500 to every
  user until restart. Now Tuttie closes them when a negotiation ends, a full store closes its
  least recently used idle session (429 only if all are busy), closed sessions are freed (50
  kept) and turns are capped (100). Sessions are bound to their opener (`session_token`, header
  `X-Session-Token`, else 403; 128-bit ids); message/context sizes are capped (422); a close
  waits for a reply in progress. Tuttie sends the agent key only to gold/blue nodes (grey nodes
  could replay it). A signed commitment books once; the LLM's arrival date is bounded.
  **Tell the team (formats.md):** the session table and the agent key note.
  Regression tests: `tests/test_r4c_sessions.py`.
- **Red team round 3, approvals, booking and payments** (branch `wip/r3-pay`, not deployed):
  an approval is signed before it leaves the pending list, so a failing mandate no longer loses
  the decision (a CHF 0 charge used to 500 the approve call and hang the booking 300 s); a
  decision landing at the timeout still counts; Tuttie handles a dropped approval. Charges are
  CHF 1 or more and mandates are offered only above zero. `book` refuses an extra whose
  commitment has expired or ends before the booked night. **Tell the team (formats.md):** a
  `pay` approval now carries a signed `charge = {purpose, booking_id}` and the gate refuses an
  approval for another charge or booking (book approvals unchanged). Tuttie flags a
  confirmation whose extras differ from the approved `includes` (`mismatch: ["includes"]`).
  Regression tests: `tests/test_r3_approvals.py`, `tests/test_r3_booking.py`.
- **Tell the team: the seal body changed (red team round 4, trust core; branch
  `wip/r4-trust`, not deployed).** Seals now also sign `name`, `kind` and `endpoint`
  (`aps/seals.py` `seal_body`, `documentation/formats.md`), and `data/registry.json` is
  re-signed. Pull it and run `scripts/issue_seals.py` after any change to a node config's
  name, kind or port; the live service must be restarted to load the new registry. Also fixed:
  a node whose `node_id` equals an authority id (e.g. "bar-association-ch") and self-seals
  stays grey with no licence or vouched UID (issue_seals refuses such ids); hotels answer a
  posting only if the requester holds the user's `post_requests` delegation; a delegation
  whose `scopes` is a string never verifies; the marketplace refuses an agent card older than
  300 s. Tiers unchanged (Rheinblick gold+blue, Spalenhof blue, scam broken, fake lawyer grey,
  Budget Rooms grey, Gästehaus gold, Alpina gold+blue, Tuttie blue).
- **Red team round 2, hotel side** (branch `wip/r2-node`, not deployed): `/agent/invoke`
  answers only posting events, and `posting.updated` now gets the same checks as
  `posting.created` (valid posting, the market's offer door, a fresh request signed by a
  verified user agent that is itself a valid Request) before any LLM runs. A request already
  handled is answered "already handled" without the LLM or a second offer (kept in memory per
  node, bounded, 10 min). An offer's `valid_until` comes from the signed request's
  `expires_at`, at most 24 h ahead and never past noon after the stay night (it came from the
  unsigned posting). The offer-door check compares the effective port (443 for https) and
  refuses any user info. Tuttie accepts an agreement only at a real price (finite, above zero,
  not a bool) and only if it is a valid `Agreement`; a counter without a real price ends the
  negotiation.
- **Presentation QR page** (branch `presentation-site`, not merged or deployed yet): a
  static, phone-first page in `code/apps/qr/`, served at `/qr/` (e.g.
  <https://web4.mendes.dev/qr/>) by the assistant's static mount of `code/apps/`; no
  build step. Hero with the Tuttie card, the pitch numbers with sources, the idea, the business
  case, a self-playing demo of the wallet in a phone, and links to the live wallet and the repo.
  It replaces the `assets/qr-landing` idea on the unmerged branch `pitch-deck-and-qr`. Details:
  `code/apps/qr/README.md`.
- **Wallet stays in step with the server** (branch `wip/live-edge`, not deployed): the
  timeline stream (`hooks/useAgentStream.js`, rules in `lib/stream.js`) no longer dies
  silently. On a stream error the line under the eyes says "Reconnecting…" (after 3 failed
  attempts "Connection lost · retrying"), the wallet retries with backoff (0.5 s up to 10 s),
  first catches up from `GET /history` by step (or reloads if the conversation changed or its
  timeline was reset) and then reconnects; it also checks `/history` every 10 s while an
  answer is awaited, and when the page becomes visible or the network comes back. A failed
  first load retries the same way and re-enables sending. A message whose `POST /chat` fails
  is dropped (it no longer stays an open turn that swallows later events); a sent one is
  bound by the returned `turn_id`. Another tab starting/resuming a chat (`storage` event on
  `tuttie.current`) or a 409 on send switches this tab to the server's conversation and
  refreshes its history list. The swipe deck's position (index + liked hotels) is saved per
  conversation on this device (`state.deck`, `saveCurrent`) and restored on reload.
  Verified: 50 wallet tests; Playwright on a local test instance (real server events, LLM out
  of credit so answers were error answers): aborted first `/chat` then the second answer shows;
  stream killed + `/events` and `/history` blocked shows Reconnecting → Connection lost, the
  answer finished meanwhile appears after recovery; first `/history` 502 twice recovers and
  sends; tab two follows tab one's new chat and lists the old chat in History; deck with fake
  cards stays at 2 of 3 after a reload. Not tested on a real phone.
- **Wallet recovery** (`lib/recovery.js`, `hooks/useVoice.js`, `App.jsx`): a failed voice join
  (token or connection) is now "unavailable": in voice mode the line under the eyes says
  "Voice unavailable · tap to retry", it is tried again after 2, 4, 8, ... up to 30 s, and at
  once on a tap or when voice mode starts again (back from typing). A server without voice
  (503 on `/voice/token`) is "disabled": text only, no note, no retries. A booking choice from
  the swipe cards that does not reach Tuttie (network or 5xx, never a 4xx) is sent once more;
  if that fails too the cards come back with "Tuttie could not be reached — swipe again to
  book". New chat while Tuttie works (409) shows "Tuttie is still working — new chat after
  this answer" for 4 s instead of the server's text. Verified with Playwright against the
  built wallet and a mocked backend (no LLM, no LiveKit); not verified with live voice. Open:
  on short screens with a long timeline the approval sheet (an overlay at the bottom) can
  cover the chosen hotel row; not a spacing fix, left as is.

- **Turns with ids** (fix "messages disappear or get overwritten"): every typed or spoken
  request is a server turn (`assistant/conversations.py` `start` returns its id and emits a
  `turn` event; `assistant/events.py` stamps every event with the running turn via a
  ContextVar). The wallet attaches events by `event.turn` (`lib/activity.js`), binds its own
  typed message to the server turn, adds spoken ones, keeps every booking in its turn (a new
  search no longer drops the last BookingCard) and shows the newest answer until the next one
  arrives; a late answer never replaces a newer one. History restore rebuilds turns from the
  server timeline. The voice agent says no filler for a `turn` event. Format in
  `documentation/formats.md` (UI event). Not verified in a browser or with live voice.
- Wallet hardening (2026-10-31, branch wip/hunt-wallet): reopening Tuttie after a swipe down
  starts a new chat only when the current one is finished (`startsFresh` in lib/history.js), so
  a deck waiting to be swiped or a running request is never lost; the approval sheet takes one
  decision per tap, no longer shows "Approved" while declining and says when a decision failed;
  an error boundary (components/Boundary.jsx) keeps a render failure in the chat or history from
  blanking the wallet; the booking card tolerates older bookings without checks or payments.
  Checked in headless Chromium (iPhone 14 Pro) on a test instance: type → deck → swipe →
  approve/decline → booking → follow-up → new chat → history → continue, reloads at the deck
  and at the sheet, close/reopen while working and at the deck, a failing and a slow decision.
- Backend hardening (2026-10-31): a failed turn (LLM refused, over its usage limit, timed out, or a
  tool crashed) ends with a friendly answer and the chat stays usable (open tool calls get a
  result); empty messages are answered without the LLM; LLM calls time out after 40 s
  (`LLM_TIMEOUT_S`, one retry); hotel agents also fall back on Anthropic errors; a hotel never
  offers a room whose note rules out a need (Anna's single for a dog guest), and an unknown room
  choice gets the cheapest real room. Tests: `test_agent_errors.py`, `test_node_agent.py`, `test_llm.py`.
- Budget leak fixed (2026-11-01, bug #18, branch wip/budget-leak): Tuttie's counters were capped
  at the private budget, so a hotel far above it got the budget itself as a counter (CHF 160 to
  Rheinblick and Alpina). Now a counter comes only from the offer and the hotel's prices: open
  10 % below the offer, else 20 % below, else walk away without a counter; move halfway, or hold
  the last counter when the step would not stay below the budget. A hotel price at or below the
  budget is still accepted. Demo numbers unchanged (Gästehaus 121/126 → 128, Rheinblick
  175/182 → 185 at budget 200). Also in code, not the prompt: `post_request` drops requirements
  that name a price or the budget's number, and `ask_agent` refuses a question naming a private
  amount. Tests: `test_budget_leak.py`.
- API hardening (2026-11-01, branch wip/harden-api): reading endpoints (`/history`,
  `/approvals/pending`, `/approvals/{id}`, `/reset`, `/identity`) no longer create a
  conversation, so crawlers and QR previews without cookies cannot fill the store and evict
  real chats; `/history` names the id the first conversation will get (HMAC of the session) and
  `/events` with that id or any action creates it. Hotel nodes: `POST /agent/invoke` validates a
  `posting.created` event (422), accepts only an `offer_url` of the configured market
  (`MARKETPLACE_URL`, default `http://localhost:4010`; set it on the nodes too if the market
  moves) and only a fresh request signed by a verified user agent (403), all before the LLM.
  `get_availability` and `book` refuse (signed) a night that is not `YYYY-MM-DD`, in the past
  or over a year ahead, and guests outside 1-10. Tests: `test_conversations.py`,
  `test_node_agent.py`, `test_node_book.py`. Note: tests use the night 2026-11-14 and will fail
  after it has passed.
  The hotel nodes are public (4001-4012), so `/agent`, `/agent/invoke` and `/agent/sessions*`
  now need the deployment's agent key (`AGENT_WEB_KEY`, header `X-Agent-Web-Key`, 401
  otherwise; `aps/agent_key.py`). `run_all.py` makes a new key per run and passes it to every
  service; the market and Tuttie send it. **A Tuttie started by hand next to the running
  services (test instance on 4046) needs the same key: put `AGENT_WEB_KEY` in `code/.env` and
  restart the service once.** Unset (tests), the doors stay open. `POST /voice/token`: at most
  10 new rooms a minute per conversation and 300 per client address, else 429 (the wallet
  retries on its own); rooms are not reused because the voice agent closes its session when
  the wallet disconnects. Tests: `test_agent_key.py`, `test_voice.py`.
- Conversation store, red team round 2 (2026-11-01, branch wip/r2-conv; many visitors share
  the live site via the QR code): saved chats are capped at 20 per browser (its own oldest go)
  and 200 in all (the browser with the most gives one up), so one browser pressing "new chat"
  cannot expire anyone else's chats. Active conversations: empty ones are dropped first; one
  with history only above 400, the fewest turns first. A browser whose conversation was dropped
  gets a new id for its next one (no longer the same HMAC), so a late "book" for the old chat
  is a 409. `POST /chat` (and spoken turns, `POST /voice/say`): at most 10 turns a minute per
  browser and 600 per client address, else 429 with `Retry-After` (the wallet shows the
  server's sentence). `POST /voice/token` throttles before it creates a conversation. A
  TypeError inside a tool is reported as a failure, not as "bad arguments" (the LLM retried
  correct calls). Tests: `test_r2_conversations.py`, `test_book_args.py`.
- Voice, red team round 3 (2026-11-01, branch wip/r3-voice): a flood of anonymous
  `POST /voice/token` calls no longer unmaps live users' rooms. Above 1000 rooms only unused
  ones are forgotten: first rooms whose conversation is gone, then rooms unused for 2 min
  (least recently used first); a room the voice agent follows (open `/voice/events`) never goes.
  Rooms in use may reach 2000; beyond that new rooms get 429 "Voice is busy" (the wallet
  retries). The voice agent's secret is compared in constant time. The voice agent cuts long
  dictation to 2000 characters (at a word) and never stays silent when `/voice/say` fails: 429
  is spoken as "One moment please.", other refusals and transport errors as "Sorry, that did
  not go through. Could you say it again?". Tests: `test_r3_voice.py`.

- Demo-story polish (2026-10-31, branch wip/story-polish), from live runs: (1) the facts note
  Tuttie gets every round (`current_deals`) now carries each card hotel's signed policies
  (check-in, dogs, cancellation, address, amenities, charges; `policy_facts` in
  assistant/tools.py), so "what time is check-in?" after booking is answered from signed facts;
  (2) after swiping, the wallet's booking message names the other liked hotels with their
  prices (`lib/picks.js`), and after a decline Tuttie offers the next one in one question
  (prompt rule 4); (3) Tuttie's recommendation stays visible under the deck (`.deck-note`,
  3 lines max) and the prompt asks it to invite a swipe, never "shall I book"; (4) a card over
  the user's private budget says "over your budget" under the price (wallet only; judged on
  the agreed price). Checked at iPhone 14 Pro with a static build and fake events.

- Local voice/offer follow-up on `fix/voice-offer-sync`: hotel-position bars (count hotels, not photos), spoken like/pass
  reaches the visible swipe deck, single-word commands survive voice filtering; verified
  agreement facts are available to price follow-ups and final counters say quoted.
  Validation: 341 Python tests, 34 wallet tests and production build pass. Local Chrome
  received live like/pass SSE events, advanced both cards and requested CHF 128 approval
  for the liked hotel without browser errors. The Chrome run used deterministic sample
  offers, not a microphone or an LLM. Broader audit: explicit English/German card synonyms
  dispatch without the model; every follow-up completion receives fresh signed deal data;
  later agreements update card prices, rapid choices queue, leaving a deck cancels its
  delayed action, new searches clear old signed-price caches, live status renders once.
  Chrome also passed two consecutive searches with rapid choices and one progress group.
  Repeat-booking follow-up: a new posting initializes fresh hotel offers/rounds/agreed
  prices and clears deck commands; empty historical turns no longer create flex gaps in
  the live view. Chrome passed two consecutive typed search → choice → approved booking
  flows at CHF 128 with no empty turns, duplicate bookings or browser errors. Verified
  web4 still serves the old photo-bar assets; PR #16 remains unmerged.
  Not deployed; live voice/provider testing needs credentials.


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
| User's agent | LLM tool loop with the trust gate: search, signed facts, A2A commitments, booking with phone approval, short voice-first answers (each result keeps its `source_step` for traceability), reasoning summaries as "thinking". Own identity: Tuttie (`ch.tuttie.alex-muster`) has its own key, an Adobe (blue) seal and the user's signed delegation; `GET /identity` returns it checked. | `code/assistant/`, `code/data/agents/` |
| Marketplace (agent layer) | Built against the draft formats: Tuttie's signed postings in (seals, freshness, user delegation `post_requests`), matching businesses woken in parallel at `POST /agent/invoke` (broken ones never contacted), only verified businesses whose agent card subscribes to new postings, signed offers in (only from invited businesses, fresh, for this request, still valid); it decides nothing. Formats as strict Pydantic models in one place. | `code/marketplace/` (:4010) |
| Bargaining (step 4) | Hotel side: the `counter_offer` tool, stateless like `book` (the counter carries the hotel's own signed offer and last counter), checks Tuttie's seals, signature, freshness and the user's `negotiate` delegation; the hotel meets halfway and never goes below its private floor or past its rounds, compared in code (`negotiation/rules.py`), never in a prompt or reply. Tuttie's side: one subagent per offer, all in parallel in their own sessions, counters signed with Tuttie's key, the private `max_price_chf` only compared in code; ends in a signed Agreement, a rejection or walking away; `best()` picks the cheapest agreement. Booking can redeem an Agreement (`AgreementRedeemer`: own signature, not expired, only once). Formats: `Counter` (+ `final`), `Agreement`, `Rejection`. Mounted in every node (`node/server.py`); Tuttie reaches it through its `negotiate` tool. | `code/negotiation/` |
| Tuttie's presence (hooks for the eyes) | One signal for the eye animations: the state (asleep, listening, speaking, typing, error, waiting, watching, negotiating, searching, booking, thinking, done, idle), voice levels ~20×/s and one-off cues (offer, agreement, scam_blocked, approved, booked, paid, ...), from mode, conversation, voice, approval and errors. Read with `usePresenceState` / `usePresenceEvents`, or `face.onPresence(event)`. The eyes are moved only by `lib/faceDirector.js` from that signal (looks per state, voice pulsing, reactions to cues); a new face with the same methods works as it is, one with `onPresence` animates it itself. Tests: `npm test` in apps/wallet. | `code/apps/wallet/src/lib/presence.js`, `hooks/usePresence.js`, wallet README |
| Weather and trains | Two sealed public information services on the agent web (gold): `get_forecast` (Open-Meteo) and `get_connections` (transport.opendata.ch), signed MCP tools, marked sample data without internet, signed refusals. Tuttie finds them in the registry and checks their answers like any node (rule 6 of its prompt; `READ_TOOLS`). Live-tested with the real LLM: "Will it rain in Basel on 14 Nov?" and "which train from Zürich before midnight" (IR 36, 22:36 → 23:52). | `code/services/`, `code/data/services/` |
| End-to-end run | The whole signed flow in one process with a simulated phone. | `code/scripts/demo_headless.py` |
| Dev tooling | `./run.sh` shows every service's log lines with its name, warns without an OpenAI key and stops everything within 3 s on Ctrl+C; `scripts/check.sh` runs the checks before a push (tests, wallet build, real flow; `--no-llm` without the LLM). | `code/run.sh`, `code/scripts/run_all.py`, `code/scripts/check.sh` |
| Wallet app | React + Vite PWA, phone-first: card stack, the Tuttie card is the agent's face (pycozmo eyes), asleep → tap to voice mode, text behind a keyboard icon, iOS-sheet swipe to close, keyboard-safe, installable. **Connected:** spoken or typed requests go to Tuttie; posting, offers and bargaining shown under its eyes; the hotels as a swipe deck (photos, rating, features, agreed price); approvals in the wallet with a Face ID-style confirmation and an optional city-tax mandate; booking card with what Tuttie checked; dock with history, new chat, keyboard and mic mute; earlier conversations can be continued. | `code/apps/wallet/` |
| Voice | Talk to Tuttie in the wallet. Self-hosted LiveKit (signaling proxied by the assistant at `/rtc`, media TCP 4042 / UDP 4043, coturn TURN relay on TCP 4044 for phones); ElevenLabs Scribe v2 realtime (speech-to-text) and Flash v2.5 (voice), English only. The voice agent decides nothing: what the user says goes to the same Tuttie conversation as typing (`POST /voice/say`), the answers and the Face ID prompt are spoken (`GET /voice/events`). Spoken request to spoken answer about 8 s. Not yet confirmed on a real iPhone over the TURN relay. | `code/voice/`, `code/assistant/voice.py`, `apps/wallet/src/hooks/useVoice.js` |
| Owner view | React + Vite, one minimal page in the wallet's look, live from the business's node and **editable**: rooms (price, offered), extras (price), negotiation (on/off, lowest price, rounds), agent (name, tone, answers new requests). The tabs at the top (Overview, Agent, Negotiation, Versions) are labels only; the page shows the four blocks. Edits are a draft in the browser; the owner reviews the changes in words and deploys; the node validates, stores the next numbered version and its tools, agent and bargaining limits use it from the next request (no restart). The node can change more (profile, policies, charges, rows) and keeps a version history (`GET /owner/versions`); the page shows neither on purpose. A stale draft cannot overwrite a newer deploy (409). Needs the owner token (`OWNER_TOKEN` in `code/.env`; unset = refused). Served at `/owner/` by the assistant; dev server on 4042. | `code/apps/owner/`, `code/node/owner.py`, `settings.py`, `deployments.py` |
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
   Offer checks (2026-11-01): the wait counts hotels, not offers (one hotel's two offers
   ended it early: likely the "only Rheinblick offered" sighting), one offer per hotel (its
   latest); offers for another request or past `valid_until` are refused; Tuttie accepts an
   Agreement only at or below its own last counter and on the offer's unchanged terms.
   Tests: `test_market_agents.py`, `test_tuttie_market.py`.
3. **Human layer in the wallet** — done: typed requests go to Tuttie; the wallet follows the
   timeline and shows the posting (budget private), the hotels asked and skipped, offers with
   seal colours and size, the shortlist, the bargaining and the answer under Tuttie's eyes;
   approvals happen in the wallet with a Face ID-style confirmation. Tested in a headless
   iPhone against a separate assistant instance with the real LLM. Voice is done too (see
   the Voice row above).
4. **Negotiation** — done (dev member 2, `code/negotiation/`): `counter_offer` is mounted in
   every node and available; Tuttie's `negotiate` tool hands the shortlist to
   `TuttieNegotiator.negotiate_all` with the budget as a private item and shows `best()`'s
   signed Agreement. Tuttie bargains right after the offers arrive (inside `post_request`), before the user sees
   anything, so the swipe cards show the agreed prices; after swiping, Tuttie books the cheapest
   liked deal. `book`
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

1. **dev member 1:** voice is done; next the demo runner (`code/demo/`); the presentation QR page
   (`code/apps/qr/`) is on branch `presentation-site`, to merge; confirm voice on a real
   iPhone.
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

**Before the pitch:**
- Rehearse on the stage hardware (laptop, projector, clicker) at least once.
- Do not restart the live service (`tuttie`) during the pitch: sessions are in memory.
- Rehearsals: at most ~4 runs a minute back to back (the `/chat` rate limit is about 10
  requests a minute per browser).

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
  `POST /voice/token` (no login needed) and is never pruned. (Both fixed: round 3 voice.)
- `requirements.txt` gained `livekit`: run `uv pip install -r requirements.txt` (or pip)
  after pulling, or the assistant and three test files fail to import.

### Test coverage

336 tests, all green (`pytest -q`), no network and no LLM (plus `npm test` in `apps/owner` for the settings helpers): `test_node_owner.py` (the owner endpoints: token, validation, deploy goes live in every tool, versions, restart, stale deploys, CORS only on `/owner`), `test_aps.py` (signing, freshness,
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

Other open items: the demo runner (`code/demo/`), merging the presentation QR page
(`code/apps/qr/`, branch `presentation-site`), voice confirmed on a real iPhone, a
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

- **A booking is bound to the selected offer, in code.** Offers and Agreements carry
  `room_type`, `date` and `rate` (cancellation terms) as fields; the hotel copies them into the
  Agreement unchanged. `book(use_agreement=true)` books exactly those terms and refuses LLM
  arguments that would change room, night or extras (before the phone is asked); the approval
  carries the `terms`, the user's key signs them, and the node refuses an agreement booked as
  another room/night/rate or an approval for other terms. Before this, the LLM's `room_type`
  went to the node unchecked, so a non-refundable deal could be booked as the flexible rate.
  The approval sheet and booking card show the room and rate.

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
  started from (`base_version`); a stale one gets 409. A deployment file that is not JSON stops
  the node at start; a single version that fails today's checks is skipped (logged, kept on disk)
  and the newest valid one is live. Rolling back is
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
  below its floor; Tuttie opens 10 % below and moves halfway, always below the private budget,
  and no counter price is ever computed from the budget (bug #18, see above). An
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
  the wallet sends the cheapest liked deal with `first_tool: "book"` and names the other liked
  hotels (offered after a decline); the user approves as usual. `scripts/demo_headless.py`
  likes every card like the wallet and asks for the check-in time after booking.
- **Progress lines:** each turn shows two joined lines that update in place and wrap downwards:
  context, then tools (asked N hotels → offers in, checking seals → comparing → bargaining →
  N hotels for you; later booking, booked).
- **One conversation at a time, history on the device:** no sideways gestures on Tuttie's
  card. A dock under the open card has three buttons: history (earlier conversations, kept in
  `localStorage`, `lib/history.js`), new chat, and the keyboard. Swiping Tuttie down and opening
  it again archives it and starts fresh (`POST /conversations`), unless a request or approval
  waits. Reload keeps the selected conversation (`GET /history`, `X-Conversation-ID`).
  History → Continue chat selects the retained server assistant (`POST /conversations/{id}/resume`);
  the keyboard in an open past chat resumes that chat before typing, and the dock's History
  button always returns to the list. Old or expired entries stay read-only: a 404/410 shows
  "This chat has expired" inline in the history, nothing starts elsewhere. Saved conversations are in memory, capped at 20
  per browser and 200 globally, in addition to the active browser conversations; a restart expires them. The
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
- **Goodbye closes the card:** Tuttie's tool `end_conversation` emits a `close` event; the wallet
  closes the card once the goodbye has arrived and been spoken (`closing` in lib/activity.js; a
  loaded or resumed chat never closes itself; a new message cancels it). No voice filler for it.
- **Chat layout:** actions stay in the chat (steps, chosen hotel, booking card, payments); of
  Tuttie's answers only the current one is shown (the history shows all). While the swipe cards
  are up they fill the conversation's space (`.activity.swiping`) with only Tuttie's short
  recommendation under them.
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
- **Choosing a hotel is guided:** after the cards, Tuttie says how many hotels it found and which
  it would pick and why; the voice then adds "It's your choice: swipe right on the ones you like,
  or just tell me" (`HANDOFF`, once per cards turn); a swiped pick is acknowledged ("Nice pick.
  Let me book …", `pick_ack` on the wallet's turn event) before the Face ID prompt. The cards go
  away once a hotel is liked or a booking is under way (`choosing()` in lib/activity.js), so
  booking by voice while the cards are up also leads to the approval and the booked block.
- **Approval sheet finishes before it goes:** the decided approval stays on screen until the
  checkmark (or X) was shown ~1.4 s, then the sheet slides down (App `finishing`, sheet
  `onDecide`/`onFinished`), even though the server stopped waiting for it.
- **Face ID glyph in the approval sheet** (`ApprovalSheet.jsx` `FaceId`, `wallet.css`): rounded
  corner brackets around a simple face (eyes, L-shaped nose, smile) like the iPhone's; while
  scanning the face turns a little and the brackets pulse; on approval the face fades and a
  checkmark is drawn inside the brackets as the glyph turns green. A decline keeps the grey X.
- **Answers are written to be heard** (`assistant/agent.py`): one to three short sentences, no
  lists, markdown, emoji or square brackets, no ids or codes (node ids, booking ids, receipt
  numbers: the wallet shows them), numbers as people say them ("CHF 128", "6 pm", "14
  November", "about 9 degrees", "25 percent"); no "[3]" step citations any more (results still
  carry `source_step`); a booking is confirmed as "booked" plus the total. Bracketed notes
  the model still writes are cleaned the same on screen (`withoutNotes`/`cleanAnswer` in
  `apps/wallet/src/lib/activity.js`) and in voice (`spoken()` in `voice/agent.py`): citations,
  a few labels ([confirmed]), booking/receipt ids and node ids are dropped; any other note keeps
  its words without the brackets, so a fee or "cancelled" is never hidden. Shared cases:
  `code/tests/fixtures/answer_notes.json`. The voice says two-digit 24-hour times as "6 pm",
  "12:52 am", "midnight", "noon" (also "14:00 hrs" / "18:00 Uhr") and leaves "8:30 pm",
  durations ("1:30 hours") and "18:00:30" alone. Only whole lines starting with "Ignored:" are
  dropped, and a non-empty answer never cleans to nothing (its words stay, unbracketed); a time
  after "takes"/"for"/"in" is a duration and stays; booking and receipt ids are never spoken;
  citation links never read out a URL; spaces are tidied only where a note was removed. Both
  sides are tested against the same "screen" column of the fixture. Reason: "18:00" was read as "1800"; "[confirmed]" / "[receipt RC-...]"
  showed up. Found and checked by a bug hunter and two attacker rounds.
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
- **Hardening (1 Nov):** the weather and train services fall back to their marked sample data
  only on a real outage (no connection, timeout, 5xx, garbled answer); a 4xx or empty answer is
  a signed refusal, so nobody gets a signed made-up timetable. `trains.check_request` refuses
  past dates and origin == destination. No app serves `/docs`, `/redoc` or `/openapi.json`
  unless `API_DOCS=1` (`code/apidocs.py`, local development). The `tuttie_session` cookie is
  `Secure` when the request came over https (directly or `X-Forwarded-Proto: https` from
  nginx), still `HttpOnly` and `SameSite=lax`; plain-http local development keeps working.
- **Round 5b (1 Nov):** an offer's name/uid come from the sealed registry record and agent/profile
  from the hotel's signed agent card (never the market's relay); card photos only `hotels/<node_id>/<file>.jpg|png|webp`.
- **Round 11 faults (1 Nov):** one slow piece no longer sinks a search: POST /postings waits
  60 s (`marketplace/client.py` `POST_TIMEOUT_S`, above the market's 20 s card + 20 s wake), a
  failed offer poll keeps polling, an unknown add-on id is dropped (the hotel still offers), a
  registry blip refuses only that call and `negotiate_all` isolates each hotel, MCP calls give up
  after 15 s (`CALL_TIMEOUT_S`). An LLM error after the cards or a confirmed booking answers from
  code ("I found 3 hotels; swipe...", "It's booked: <hotel>, CHF 128.") instead of "try again".

## Environment

- **Team server:** only ports 4000-4049 are open. Registry 4000, nodes 4001-4009,
  marketplace 4010, weather and trains 4011-4012, assistant and apps 4040, wallet dev server
  4041, LiveKit media TCP 4042 / UDP 4043, TURN relay TCP 4044 (owner dev server also 4042:
  use it locally only).
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


## Presentation

- `code/apps/pitch/` (moved from `assets/pitch-deck/`, served at `/pitch/`) contains the offline eight-scene illustrated pitch, timed to 1:54, with speaker notes, research and photo credits. The optional live wallet handoff requires rehearsal; the phone animation uses demo data.
