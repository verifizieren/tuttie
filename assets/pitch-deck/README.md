# Tuttie pitch

Eight scenes, 1:54 of narration. An optional rehearsed live handoff adds up to 30 seconds; the pitch stays below the three-minute limit.

Open `index.html` directly in Chrome or Safari, or serve the repository with `python3 -m http.server 4050` and visit `/assets/pitch-deck/`. The illustrated walkthrough works offline and is silent. The QR and live wallet require a connection.

Controls: Space/→ next; ← back; F fullscreen; T start/pause clock; R reset; N speaker notes/clock; A auto-play; Home/End first/last scene; L open the actual wallet. `?theme=dark` previews the alternate background.

Design: the light wallet look (`code/apps/wallet/src/wallet.css`): a #f2f2f7 stage, #17171d text, the white Tuttie card with black glossy eyes (drawing ported from `lib/face.js`, inlined so the file also opens offline) and the Swiss bank cards from `BankCard.jsx`. Change the phone mock-ups together with the wallet.

Rehearse aloud using [speaker notes](SPEAKER-NOTES.md). The phone is an illustration of the prototype using fictional hotels and personal context, not a recording of a live session. Do not present the animation as the live app. Use the optional handoff only after a successful rehearsal.

[Research and scope](RESEARCH.md) · [Photo credits](PHOTO-CREDITS.md). Procedural eye attribution is preserved in the HTML.
