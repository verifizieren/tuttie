# Wallet app (issue #2) — React + Vite PWA, not connected to the backend yet

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
- Not connected yet: voice and text only make the eyes react. The backend already offers
  what the next steps need: `POST /chat`, the timeline at `GET /events`, and signed phone
  approvals at `GET /approvals/pending` and `POST /approvals/{id}`.

## Code

```
index.html                 entry page (PWA meta tags)
vite.config.js             base /wallet/, dev server on 4041 with API proxy to 4040
public/                    manifest.json, sw.js (service worker), icons/
src/main.jsx               loads the styles, registers the service worker, renders <App/>
src/App.jsx                the screen and its modes: closed / voice / typing
src/components/            BankCard, AgentCard (face card), AgentControls (status, keyboard, text)
src/hooks/                 useCardGestures (iOS-sheet swipes), useFace, useVisibleViewport (keyboard-safe)
src/lib/face.js            procedural eyes: port of pycozmo's face and 25 expressions (MIT)
src/wallet.css             layout; brand colours and fonts come from apps/shared/tuttie.css
```

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
