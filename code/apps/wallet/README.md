# Wallet app (issue #2) — first UI, not connected yet

The phone is the main stage of the demo. This is the real product: the demo is only a
simulated run through this same app (`code/demo/` feeds the storyline's input), so every screen
must work for real use too. The web app **is** the wallet: built for phone
screens first (one column, safe areas, big touch targets), not a phone mock-up on a laptop.

Direction agreed by the team:

- **Minimal**, Apple Wallet-like: a stack of cards. The Tuttie agent card plus two generic
  bank cards that only resemble cards (no names, numbers or other details).
- Swiping the agent card up opens the voice agent (`code/voice/`).
- Agents are shown as **procedural eyes** (`apps/shared/face.js`, a port of pycozmo's
  procedural face and expressions), not logos.
- The agent view is **voice first** (big eyes, mic button); a small text field is the
  fallback for typing a prompt.
- Offers, shortlist, negotiation and approvals appear inside the wallet.
- Brand: `apps/shared/tuttie.css` (colours, fonts, seal badges); seal badges come from
  `apps/shared/seals.js`.

What exists: `index.html` (served at `/` and `/wallet/`) shows the card stack; tapping or
swiping up the Tuttie card opens the agent view. Mic and text field only make the eyes
react; nothing is sent to the agent backend yet. Tap the big eyes to cycle through the
expressions. The approval flow of the first prototype is in `apps/old/wallet/`
(`GET /approvals/pending`, `POST /approvals/{id}`) and can be reused here.

A design example (phone, wallet cards, voice orb, behind-the-scenes panel) lives locally in
`code/.context/` and is not in git; ask the team for it. Take its look, keep it more minimal.
