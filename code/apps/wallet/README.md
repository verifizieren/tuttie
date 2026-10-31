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
- **Connected:** spoken or typed requests go to Tuttie (`POST /chat`, or the voice agent).
  The wallet follows Tuttie's timeline (`GET /events`) and shows, under its eyes, two progress
  lines (what Tuttie knows, what it does), then the hotels as a **swipe deck** (photos, rating,
  features in green or red, the agreed price with the hotel's own offer crossed out; right =
  like, left = pass), the chosen hotel, the booking and Tuttie's current answer. Tapping a
  hotel shows who vouches for it. The face follows each phase through Tuttie's presence (below).
- **Approvals happen in the wallet:** a sheet shows hotel, seals and amount; approving runs a
  Face ID-style confirmation before the decision goes to `POST /approvals/{id}`, where the
  assistant signs it with the user's key. The sheet can also allow a small mandate, so the
  city tax is paid right after the booking without a second prompt. The booking card shows
  what Tuttie checked ("Checked by Tuttie") and the paid tax.
- **Voice** (`hooks/useVoice.js`, server side in `code/voice/`): the wallet joins the
  conversation's LiveKit room with the microphone off; opening Tuttie's card switches it on.
- **Dock** under the open card: history of earlier conversations (they can be continued), new
  chat, keyboard, microphone mute.

## Code

```
index.html                 entry page (PWA meta tags)
vite.config.js             base /wallet/, dev server on 4041 with API proxy to 4040
public/                    manifest.json, sw.js (service worker), icons/
src/main.jsx               loads the styles, registers the service worker, renders <App/>
src/App.jsx                the screen and its modes: closed / voice / typing; sends requests to Tuttie
src/components/            BankCard, AgentCard (face card), AgentControls (status, keyboard, text),
                           Activity (progress, cards, booking, answer), Deck (swipe cards), FeatureIcon,
                           BookingCard, Seals, ApprovalSheet (Face ID), Dock, History
src/hooks/                 useCardGestures (iOS-sheet swipes), useFace, useVisibleViewport (keyboard-safe),
                           useAgentStream (follows GET /events), usePresence (Tuttie's presence, below),
                           useVoice (LiveKit room, microphone, spoken answers)
src/lib/activity.js        turns timeline events into what the wallet shows (pure reducer)
src/lib/conversation.js    rebuilds a conversation from the server's timeline
src/lib/history.js         earlier conversations on this device (localStorage)
src/lib/iceReport.js       reports voice connection facts to the server (POST /voice/diag)
src/lib/presence.js        what Tuttie is doing, as one signal for the eyes (pure; tests: npm test)
src/lib/faceDirector.js    moves the eyes from that signal: looks per state, reactions to cues
src/lib/api.js             POST /chat, POST /approvals/{id}, POST /conversations, POST /conversations/{id}/resume
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

**Who moves the eyes:** `src/lib/faceDirector.js` (connected in App with `useFaceDirector`). It
turns the presence into the face's own methods (`set`, `lookAt`, `setVoice`, `sleep`, `wake`):
each state has a base expression and a loop of looks (searching scans left and right, thinking
looks up and around, listening nods, waiting looks down at the approval sheet, watching follows
the dragged card; asleep and typing close the eyes), the voice levels make the eyes pulse, and
each cue plays a short reaction (`REACTIONS`) before the loop goes on. Tune the looks and
reactions there. A new face with the same methods works as it is; a face that defines
`onPresence(event)` animates the presence itself and the director steps aside. Nothing else in
the wallet calls the face any more.

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

Minimal, voice first, the agent as a face; offers, negotiation and approvals appear inside
the wallet (`documentation/context/dev/goals.md`, steps 3 and 4). Keep the look
calm: no glow borders, a faint halo on the eyes, brand from `apps/shared/tuttie.css`. A
design example lives locally in `code/.context/` (not in git); take its look, keep it more
minimal.

## Continuing an earlier chat

New chat keeps the previous assistant on the server. Open History, choose a conversation,
then Continue chat to restore its context and signed offers before typing or choosing a hotel.
Reload keeps the selected chat. Offers are still verified for expiry by the normal booking gate.
Conversations are in memory and bounded: after eviction or a server restart, history remains
readable but cannot resume; make a fresh request. Older browser-only archives cannot be restored.
Switching is refused while a request or approval is pending. Voice reconnects to the selected chat.
