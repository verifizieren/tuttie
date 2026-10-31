# Wallet app (issue #2) — React + Vite PWA, the human layer of the agent web

The phone is the main stage of the demo, and this is the real product: the demo is only a
run through this same app (`code/demo/` feeds the storyline's input), so every screen must
work for real use too. Built for phone screens first; installable on the home screen.
Live at <https://web4.mendes.dev/wallet/>.

## What it does today

- A minimal Apple Wallet-like stack: two generic bank cards (only colour and chip) and the
  **Tuttie card**, which is nothing but the agent's face (procedural eyes ported from
  pycozmo) with a quiet "Tuttie" label.
- **Asleep** in the stack (eyes closed). **Tap or swipe up** wakes Tuttie into **voice
  mode**, the main interface; it stays on until the card is **swiped down**. Taps never send
  Tuttie away.
- **Text is a fallback** behind a small keyboard icon; the eyes close while typing, and the
  keyboard never opens by accident.
- **Connected:** typed requests go to Tuttie (`POST /chat`). The wallet follows Tuttie's
  timeline (`GET /events`) and shows, under its eyes, what Tuttie posted (the budget stays
  private), which hotels were asked or skipped, their offers with seal colours and size, the
  shortlist, the bargaining (offer → agreed price) and Tuttie's answer. The face follows each
  phase (curious, happy about offers, sceptical while bargaining).
- **Approvals happen in the wallet:** a sheet shows hotel, seals and amount; approving runs a
  Face ID-style confirmation before the decision goes to `POST /approvals/{id}`, where the
  assistant signs it with the user's key.
- Voice recognition is not connected yet (its own work area, `code/voice/`).

## Code

```
index.html                 entry page (PWA meta tags)
vite.config.js             base /wallet/, dev server on 4041 with API proxy to 4040
public/                    manifest.json, sw.js (service worker), icons/
src/main.jsx               loads the styles, registers the service worker, renders <App/>
src/App.jsx                the screen and its modes: closed / voice / typing; sends requests to Tuttie
src/components/            BankCard, AgentCard (face card), AgentControls (status, keyboard, text),
                           Activity (posting, offers, shortlist, bargaining, answer), ApprovalSheet (Face ID)
src/hooks/                 useCardGestures (iOS-sheet swipes), useFace, useVisibleViewport (keyboard-safe),
                           useAgentStream (follows GET /events), usePresence (Tuttie's presence, below)
src/lib/activity.js        turns timeline events into what the wallet shows (pure reducer)
src/lib/presence.js        what Tuttie is doing, as one signal for the eyes (pure; tests: npm test)
src/lib/api.js             POST /chat, POST /approvals/{id}, POST /reset
src/lib/face.js            procedural eyes: port of pycozmo's face and 25 expressions (MIT)
src/wallet.css             layout; brand colours and fonts come from apps/shared/tuttie.css
```

## Tuttie's presence: hooks for the eyes' animations

The eyes should move with what Tuttie does. `src/lib/presence.js` folds everything the wallet
knows (card mode, conversation phase, both voice levels, approval, errors, a dragged card) into
one signal; the animation only reacts to it. Three kinds of events:

| Event | When | Fields |
| --- | --- | --- |
| `state` | what Tuttie is doing changed | `state`, `detail`, `since` (ms) |
| `levels` | ~20× a second while voice is live | `speaking`, `hearing` (0..1: Tuttie's voice, the user's mic) |
| `cue` | a one-off moment | `name`, `detail` |

**States** (first match wins): `asleep` (card closed) · `listening` (the user is talking) ·
`speaking` (Tuttie is talking) · `typing` · `error` · `waiting` (approval on the phone; amount,
hotel) · `watching` (user swipes hotel cards; `lean` -1..1) · `negotiating` (hotel, price,
rounds of the latest round) · `searching` (posting, offers, seal checks) · `booking` ·
`thinking` · `done` (answer arrived; `mood`: happy, sorry, ...) · `idle` (awake, ready).
Talking holds through short pauses (`VOICE.holdMs`), so the state does not flicker between words.

**Cues:** `wake`, `sleep`, `tap`, `new_chat`, `user_said`, `posted`, `scam_blocked` (a broken or
untrusted hotel was not asked: name, tier), `offer` (hotel, price, tiers), `counter`,
`agreement` (hotel, price), `cards`, `approval_requested`, `approved`, `declined`, `booked`,
`paid` (purpose, amount, paidWith), `answer` (mood). Loaded or cleared conversations give no cues.

**Using it** (pick one):

```js
// 1. In the face itself, no React: App calls this for every event if it exists.
class TuttieFace { onPresence(event) { /* event.type: "state" | "levels" | "cue" */ } }

// 2. In any component under App:
import { usePresenceState, usePresenceEvents } from "../hooks/usePresence.js";
const { state, detail } = usePresenceState();          // re-renders only when the state changes
usePresenceEvents(event => { /* levels and cues */ }); // no re-render
```

Today the old face code in `App.jsx` still drives the eyes (phase looks, `setVoice`), so nothing
changes until the new animation uses these hooks; then the matching `face.current?.set(...)`
calls in `App.jsx` can go.

## Run

```bash
cd code/apps/wallet
npm install
npm run dev      # http://localhost:4041/wallet/ with hot reload (start ../../run.sh for the API)
npm run build    # production build in dist/, served by the assistant at /wallet/
```

`code/run.sh` builds the wallet automatically when Node.js is installed. App icons are drawn
by `code/scripts/make_icons.py`.

## Direction (agreed by the team)

Minimal, voice first, the agent as a face; offers, shortlist, negotiation and approvals will
appear inside the wallet (`documentation/context/dev/goals.md`, steps 3 and 4). Keep the look
calm: no glow borders, a faint halo on the eyes, brand from `apps/shared/tuttie.css`. A
design example lives locally in `code/.context/` (not in git); take its look, keep it more
minimal.
