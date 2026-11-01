# Presentation site (QR page, issues #1, #6)

The page the pitch's QR code opens. Phone first, static, no build: served by the assistant at
`/presentation/` (it serves `code/apps/` as static files). Locally: `python3 -m http.server` in
`code/apps` and open `/presentation/` (the eyes are an ES module, so `file://` does not work).

What it shows, top to bottom (little text on purpose):

1. **Hero:** the Tuttie card wakes up, "Your agent for the web.", a textless chevron cue.
2. **Numbers:** three figures, one per screen, each with its source and the source's logo
   (`img/sources/`, credits in `img/sources/CREDITS.md`). Only figures from the "facts we may
   say" table in `documentation/context/pitch/storyline.md`: 2 in 3 small Swiss firms without a
   website (localsearch & HSLU 2025), 29.6 % of European hotel bookings via online agencies
   (HOTREC 2024), +539 % visits to US travel sites from AI assistants, holiday season
   (Nov–Dec) 2025 vs 2024 (Adobe Analytics; clicks, not bookings). One scroll gesture (wheel,
   trackpad flick, swipe, arrow key) moves exactly one number (`numsTarget` in `index.html`);
   before and after the section the page scrolls natively.
3. **A reverse marketplace:** two animated graphics, your request goes out to three
   businesses, their offers come back.
4. **It searches, checks, bargains; you tap:** the kinds of businesses and the seal colours.
5. **For businesses:** 7 rooms vs 220, the commission an agency takes on a CHF 135 night,
   and who pays. No invented market numbers.
6. **Demo:** an Apple-style scroll docks the phone, then the demo plays by itself, like a story:
   one progress segment per part, tap right = next part, tap left = previous part, press and
   hold = pause, arrow keys (Space pauses) and side arrows on desktop. It follows the real
   wallet's screens and wording. Dark "behind the screen" callouts explain what happens out of
   sight. At the end: Replay on the phone and a textless chevron to scroll on.
7. **Close:** throughline, "Watch it again", the honesty line, team, a "Code on GitHub" pill.

A small textless arrow brings you back to the top once you are past the hero.

Design rules (from the user): light theme (page #f2f2f7, white panels, ink
#17171d), accents blue #2f6fe0, purple #7a5af8, pink #e5489b only (no orange), nothing in
italic, no eyebrow labels above headings, no domain or URL as visible text, buttons are pills
that fit their label. The page never links to the live wallet: people who scan the QR get the
feeling, not the shared live system. The browser scrollbar is hidden.

The demo is a mock that copies the wallet's look (`apps/wallet/src/wallet.css`) at the wallet's
native 390 x 844 size; the live product is the wallet itself. The bank cards are UBS and ZKB as
in `apps/wallet/src/components/BankCard.jsx`. `face.js` is a copy of
`apps/wallet/src/lib/face.js`: keep it in sync. Photos: `img/` (copied from
`apps/wallet/public/hotels`, credits in `apps/wallet/public/hotels/CREDITS.md`).

Edit the demo's timing in `EVENTS` and `capAt` near the end of `index.html` (`capAt` also
defines the story parts the taps jump between).
