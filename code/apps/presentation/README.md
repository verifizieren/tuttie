# Presentation site (QR page, issues #1, #6)

The page the pitch's QR code opens. Phone first, static, no build: served by the assistant at
`/presentation/` (it serves `code/apps/` as static files), e.g.
<https://web4.mendes.dev/presentation/>. Locally: `python3 -m http.server` in this folder
(the eyes are an ES module, so `file://` does not work).

What it shows, top to bottom (short points only, little text on purpose):

1. **Hero:** the Tuttie card wakes up. Tuttie is framed as your agent for the web; the hotel
   is one example.
2. **Numbers:** pinned while you scroll, one figure per screen, each with its source (only
   figures from the "facts we may say" table in `documentation/context/pitch/storyline.md`).
   Every figure has a baseline: the 58 % fraud share is of all 35,727 NCSC reports; the +539 % shows the 2024 and 2025 holidays as bars to scale.
3. **The idea:** it searches, checks, bargains; you tap. Four steps and the seal colours.
4. **Under the hood:** what is signed, for technical readers: seals (UID), signed offers and
   agreements, the delegation (never paying), the approval for one exact amount, the mandate
   (≤ CHF 10, trusted businesses), prices only from signed data. Keep it true to `code/aps/`.
5. **For businesses:** 7 rooms vs 220 (with why the small one won in the demo: signed facts
   and budget), the commission an agency takes on a CHF 135 night against Tuttie's fixed fee
   per signed booking (amount not set yet). No invented market numbers.
6. **Demo:** an Apple-style scroll: the phone rises and docks, then a demo of the wallet plays
   by itself (tap the phone to pause, Replay on the phone at the end). It follows the real
   wallet's screens and wording (progress lines, swipe deck, approval sheet, booking card).
   Light "behind the screen" callouts explain what happens out of sight (the context it reads
   is demo data; the budget is never sent; limits are compared in code; the signed amount).
   Only *forged* seals "never reach you": unsigned businesses are shown untrusted and never book.
7. **Close:** throughline, "Watch it again", the honesty line, team, repo.

The page never links to the live wallet: people who scan the QR get the feeling, not the
shared live system. The browser scrollbar is hidden.

The page is light and calm like the wallet's light design (page #f2f2f7, white panels with
hairline borders, dark text, accent #d97757; the Tuttie card is white with black eyes, the bank
cards are UBS and ZKB as in `apps/wallet/src/components/BankCard.jsx`). The demo here is a mock
that copies the wallet's look (`apps/wallet/src/wallet.css`) at the wallet's native 390 x 844 size; the live product is the wallet itself. `face.js` is a copy of
`apps/wallet/src/lib/face.js`: keep it in sync. Photos: `img/` (copied from
`apps/wallet/public/hotels`, credits in `apps/wallet/public/hotels/CREDITS.md`).

Edit the demo's timing in `EVENTS` and `capAt` near the end of `index.html`.
