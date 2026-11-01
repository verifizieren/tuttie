# Presentation site (QR page, issues #1, #6)

The page the pitch's QR code opens. Phone first, static, no build: served by the assistant at
`/presentation/` (it serves `code/apps/` as static files), e.g.
<https://web4.mendes.dev/presentation/>. Locally: `python3 -m http.server` in this folder
(the eyes are an ES module, so `file://` does not work).

What it shows, top to bottom:

1. **Hero:** the Tuttie card wakes up; the product in one sentence.
2. **Numbers:** pinned while you scroll, one figure per screen (2 in 3 small Swiss firms
   without a website, 3 % taking bookings online, 29.6 % of EU hotel bookings via agencies,
   +539 % AI traffic to US travel sites). Only figures from the "facts we may say" table in
   `documentation/context/pitch/storyline.md`, each with its source on the page.
3. **The idea:** "So we turned the web around", the four steps and the seal colours.
4. **Business case:** Anna's 7 rooms vs a 220-room chain, what a 15 to 18 % commission costs
   her on a CHF 135 night, and who pays (fee per signed booking, agent as a service, seals).
   No invented market numbers.
5. **Demo:** an Apple-style scroll: the phone rises and docks, then a demo of the wallet plays
   by itself (tap the phone to pause): wallet → ask → signed request → forged hotel refused →
   bargaining 135 → 128 → swipe deck → signed approval → booking. Light callouts explain what
   happens behind the screen; they are styled apart from the wallet so they never read as UI.
6. **Close:** throughline, "Wake yours" to the live wallet, the honesty line, team, repo.

The demo here is a mock that copies the wallet's look (`apps/wallet/src/wallet.css`) at the
wallet's native 390 x 844 size; the live product is the wallet itself. `face.js` is a copy of
`apps/wallet/src/lib/face.js`: keep it in sync. Photos: `img/` (copied from
`apps/wallet/public/hotels`, credits in `apps/wallet/public/hotels/CREDITS.md`).

Edit the demo's timing in `EVENTS` and `capAt` near the end of `index.html`.
