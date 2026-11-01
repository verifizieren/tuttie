# Tuttie pitch

Eight scenes, 1:54 of narration. An optional rehearsed live handoff adds up to 30 seconds; the pitch stays below the three-minute limit.

Lives in `code/apps/keynote1/`. Tuttie serves it at `/keynote1/` (static, from disk, no restart needed). It also opens directly from `index.html` in Chrome or Safari (file://), or locally with `python3 -m http.server 4048` from `code/apps` and `/keynote1/`. The hotel photos are relative (`hotels/…`), so both ways work. The illustrated walkthrough works offline and is silent. The QR and live wallet require a connection. No URL is shown on any slide: the QR encodes the link, and L opens the wallet next to the deck (`../wallet/`; from file:// the public site).

Controls: Space/→ next; ← back; F fullscreen; T start/pause clock; R reset; N speaker notes/clock; A auto-play; Home/End first/last scene; L open the actual wallet. `?theme=dark` previews the alternate background.

Design: the light wallet look (`code/apps/wallet/src/wallet.css`) and the team design rules: a #f2f2f7 stage, #17171d text, Inter, accents only blue #2f6fe0, purple #7a5af8 and pink #e5489b (green and red stay status colours), nothing italic, no small labels above headings. The white Tuttie card has the black glossy eyes (drawing ported from `code/apps/wallet/src/lib/face.js`, inlined so the file also opens offline) and the Swiss bank cards from `BankCard.jsx`. Change the phone mock-ups together with the wallet.

Rehearse aloud using [speaker notes](SPEAKER-NOTES.md). The phone is an illustration of the prototype using fictional hotels and personal context, not a recording of a live session. Do not present the animation as the live app. Use the optional handoff only after a successful rehearsal.

[Research and scope](RESEARCH.md) · [Photo credits](PHOTO-CREDITS.md). Procedural eye attribution is preserved in the HTML.
