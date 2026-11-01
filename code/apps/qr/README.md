# Presentation site (QR page, issues #1, #6)

The page the pitch's QR code opens. Phone first, static, no build: served by the assistant at
`/qr/` (it serves `code/apps/` as static files). Locally: `python3 -m http.server` in
`code/apps` and open `/qr/` (the eyes are an ES module, so `file://` does not work).

What it shows, top to bottom (little text on purpose):

1. **Hero:** the Tuttie card wakes up, "Your agent for the web.", a textless chevron cue.
2. **Numbers:** three figures, one per screen, each with its source and the source's logo
   (`img/sources/`, credits in `img/sources/CREDITS.md`). Only figures from the "facts we may
   say" table in `documentation/context/pitch/storyline.md`: 58 % of Swiss cyber reports
   are fraud (NCSC, H1 2025, of 35,727 reports), 29.6 % of European hotel bookings via online agencies
   (HOTREC 2024), +539 % visits to US travel sites from AI assistants, holiday season
   (Nov–Dec) 2025 vs 2024 (Adobe Analytics; clicks, not bookings). One scroll gesture (wheel,
   trackpad flick, swipe, arrow key) moves exactly one number (`numsTarget` in `index.html`);
   before and after the section the page scrolls natively.
3. **A reverse marketplace:** two animated graphics, your request goes out to three
   businesses, their offers come back.
4. **Under the hood:** what is signed, for technical readers (seals, offers and agreements,
   delegation, approval, mandate, prices from signed data). Keep it true to `code/aps/`.
5. **It searches, checks, bargains; you tap:** the kinds of businesses and the seal colours.
6. **For businesses:** "A fair chance." Matches on signed facts, needs and budget, without
   the room-count comparison cards. The commission an agency takes on a CHF 135 night
   (15–18 %) against Tuttie's 5 % per signed booking (CHF 6.75), bars to scale. No invented
   market numbers.
7. **The agent web:** "One web. Two layers." Websites remain for people; agents exchange
   signed facts and offers alongside them. A responsive HTML/CSS and inline SVG diagram
   shows the two layers, ownership links and APS exchanges, with a screen-reader description.
   **APS** follows as a nested "Trust, signed." subsection about sender identity, offer
   integrity and user permission, with a smaller heading and a subtle divider.
8. **Demo:** an Apple-style scroll docks the phone, then the demo plays by itself, like a story:
   one progress segment per part, tap right = next part, tap left = previous part, press and
   hold = pause, arrow keys (Space pauses) and side arrows on desktop. It follows the real
   wallet's screens and wording. Dark "behind the screen" callouts explain what happens out of
   sight. At the end: Replay on the phone and a textless chevron to scroll on.
9. **Close:** throughline, "Watch it again", the honesty line, team, a "Code on GitHub" pill.

A small textless arrow brings you back to the top once you are past the hero.

Design rules (from the user): light theme (page #f2f2f7, white panels, ink
#17171d), accents blue #2f6fe0, purple #7a5af8, pink #e5489b only (no orange), nothing in
italic, no eyebrow labels above headings, no domain or URL as visible text, buttons are pills
that fit their label. The page never links to the live wallet: people who scan the QR get the
feeling, not the shared live system. The browser scrollbar is hidden.

The demo is a mock that copies the wallet's look (`apps/wallet/src/wallet.css`) at the wallet's
native 390 x 844 size; the live product is the wallet itself. The bank cards are UBS and BKB as
in `apps/wallet/src/components/BankCard.jsx`. `face.js` is a copy of
`apps/wallet/src/lib/face.js`: keep it in sync. Photos: `img/` (copied from
`apps/wallet/public/hotels`, credits in `apps/wallet/public/hotels/CREDITS.md`).

Speed: both faces paint only while their canvas is on screen (`paintOnlyOnScreen` wraps the
instance, so `face.js` stays an exact copy); each frame draws two eyes with a blurred halo at
up to 3x resolution. Inter loads without blocking the first paint. Only the top bar keeps a
backdrop blur (a blur under an almost opaque button costs every scroll frame and does not show).

Edit the demo's timing in `EVENTS` and `capAt` near the end of `index.html` (`capAt` also
defines the story parts the taps jump between).
