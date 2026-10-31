# Wallet app (issue #2) — approvals page only; wallet UI not started

The phone is the main stage of the demo. The web app **is** the wallet: built for phone
screens first (one column, safe areas, big touch targets), not a phone mock-up on a laptop.

Direction agreed by the team:

- **Minimal**, Apple Wallet-like: a stack of cards. The Tuttie agent card plus two generic
  bank cards that only resemble cards (no names, numbers or other details).
- Swiping the agent card up opens the voice agent (`code/voice/`).
- Agents are shown as **procedurally generated avatars** ("pycozme", library to be
  confirmed by the team), not logos.
- Offers, shortlist, negotiation and approvals appear inside the wallet.
- Brand: `apps/shared/tuttie.css` (colours, fonts, seal badges); seal badges come from
  `apps/shared/seals.js`.

What exists: `index.html` lists pending approvals from `GET /approvals/pending` and sends
the decision to `POST /approvals/{id}`; the assistant signs it with the user's key.

A design example (phone, wallet cards, voice orb, behind-the-scenes panel) lives locally in
`code/.context/` and is not in git; ask the team for it. Take its look, keep it more minimal.
