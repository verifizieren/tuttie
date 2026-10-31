# Pitch storyline v3 (draft)

3:00 hard, live demo through the real wallet. Draft from the pitch team's brainstorm on 31 Oct
(5 story drafts, 10 critiques, 2 directors, pitch research, 4 audits). Research playbook:
[playbook.md](playbook.md). Checked against the repo at `b35b271` (three hotel agents,
marketplace, shortlist, bargaining, booking an agreement).

## Recommendation

One world, one camera (the search field whose cursor lies down and becomes Tuttie's eye),
carrying the strongest human lines: the squint gag, "Tuttie read the fine print", Anna and
the honesty line. It fits the clock (planned 2:34, about 2:49 if the live part runs 30 % long),
covers the Adobe criteria (vision, real mechanism, why this offer, small business, human in
control) and opens with what Tuttie is, as the research says.

**Data fit (repo at `b35b271`):** the marketplace has three hotel agents: **Alpina Grand
Basel** (large chain branch, 220 rooms, CHF 240, not quiet), **Hotel Rheinblick** (medium,
42 rooms, CHF 180) and **Gästehaus am Rhein** (small independent, 7 rooms, run by its owner
**Anna**, gold seal, CHF 135, quiet, dogs welcome, arrivals until 02:00). The request is
"a quiet room in Basel tonight, after midnight, with my dog, under 160". With the real facts
and the private budget, Alpina and Rheinblick are over budget, the forged basel-cheap-hotels
node is refused by the marketplace (broken seal, never asked), and the small guesthouse wins;
Tuttie's subagent can then bargain within Anna's private limits. Anna is a demo persona from
the repo; say so.

**The posting must use category `hotel` and only the tag `dog-friendly`.** The registry wakes
only businesses that carry all posted tags: `basel-sbb` would drop Gästehaus am Rhein (it is in
Kleinbasel), `quiet` would drop Alpina. Quiet, late arrival and the budget are checked by Tuttie
on the signed facts.

**The forged business never sends an offer.** The marketplace refuses broken seals before it
wakes anyone and lists them as skipped. The wallet shows that refusal (name, red seal, "never
asked"); it must never show a fake offer row that then fails.

## The throughline

**"Signed businesses reach you. Fakes never do."** Said three times: at 0:05, right after the
forgery dies, and before the closing line. "In 2000 you needed a website. In 2033 you need a
signature." stays the only other slogan.

## Storyline v3

On screen: 14 words in total (the wallet UI is the product and is not counted). Spoken: about
250 words, 16 clicks.

| Time | On screen | Camera | Spoken | Live wallet |
| --- | --- | --- | --- | --- |
| 0:00–0:09 | — (sleeping eye lines) | fade up, locked | [1.5 s, eyes open] This is Tuttie, my agent. She lives in my wallet. Signed businesses reach you. Fakes never do. | asleep in the pocket |
| 0:09–0:32 | `quiet hotel basel tonight dog` · one red tab `Super quiet!!! CHF 99` | the right eye line stands up into a cursor; pull back 50× through 2,000 tabs; push onto the one red tab, still | Here's how we find a room today. Ten tabs. Fifty. The cheapest: super quiet, dogs welcome, pay by bank transfer. [pause] Scam. [pause] And the best little hotel in Basel? Page nine. Nobody goes to page nine. | — |
| 0:32–0:47 | — | lights go out from the edges in; dive back to the field; the cursor lies down into the eye | So we turned the web around. [1.5 s] Tuttie works only for me. Trust me. [squint at Thomas, 1 s] …Fair. I'm not signed. | giant face, cued expression |
| 0:47–0:49 | — | matched cut: the giant eyes land on the card's eyes | — | wallet in the page, asleep |
| 0:49–1:12 | wallet UI | one punch-in to 1.25× on the forgery, hold, release | Tuttie, a quiet room in Basel tonight. I arrive after midnight, with my dog. Under one-sixty, and get me a good price. She asks their agents. Every answer shows who vouches for it. Gold: a business register. [squint, 2 s silence] Remember that look? The ninety-nine-franc one. Forged seal. Never even asked. [pause] Signed businesses reach you. Fakes never do. | wake; request; offer rows slide in (seal colour, name, price); basel-cheap-hotels shows up among the businesses the marketplace refused (its gold seal fails verification: red, never asked), then dissolves |
| 1:12–1:40 | winner card | locked | Tuttie read the fine print, and bargained for me. Too loud there. Over budget there. This one: quiet, by the Rhine, dogs welcome, door code after midnight. [pause] That's Anna. One tap. Signed with my key, for exactly the price they agreed. Goodnight, Tuttie. | Gästehaus am Rhein card: gold seal, 3 signed facts, the signed agreement price; signed approval for exactly that total → `book()`; booking card files into the stack; swipe to sleep |
| 1:40–1:47 | — | hold | The hotels and the register are demo. My request was a button. The signatures are real. | asleep |
| 1:47–2:18 | — | pull out to the exact framing of the red tab: now gold eyes sit in its slot; a gold thread from you to her; then the whole field opens its eyes, threads flow inward | Remember page nine? That was Anna. Seven rooms, no marketing team. She was asleep. Her agent wasn't. Anna is a demo. But two in three Swiss firms under ten people are like her: no website. And agents already shop: last holiday season, AI traffic to US travel sites grew over 500 percent, says Adobe Analytics. Content Credentials show where a photo comes from. Our seals show where an offer comes from. | — |
| 2:18–2:34 | `website → signature` · `Wake yours.` · URL + QR | everything converges into the face; locked; words swap; the QR blooms | Signed businesses reach you. Fakes never do. In 2000, you needed a website. [pause] In 2033… you need a signature. [2 s silence] Tuttie is live. [pause] Wake yours. | Thomas raises the real phone and wakes it |

**Checkpoints:** in the wallet by 0:50, pulling out by 1:48. **Cut first if long:** the
Content Credentials line, then "Ten tabs. Fifty.", then "Seven rooms, no marketing team". **Never
cut:** the identity line, the honesty line, the market sentence, the closing line and its 2 s
of silence.

## Zoom system

- **One world, one camera:** `cam {x, y, s}` on a 1920×1080 stage scaled to the window. Scale
  is interpolated in log space so every power of ten takes the same time; x/y keep the anchor
  still. Anchor chain: eyes → cursor → red tab → eyes → card → you-dot → face → QR. The centre
  is never fully black (a black projector reads as a crash).
- **Two curves, no bounce:** ARRIVE `cubic-bezier(.22, 1, .36, 1)` (the brand `--ease`) for
  pans, hand-offs and the punch-in; TRAVEL `power2.inOut` on log scale for every move larger
  than 10×.
- **Durations:** ARRIVE 0.6–1.8 s; TRAVEL 2.0–2.4 s for dives, 4–6 s for reveals Thomas talks
  over. The camera is still whenever a line lands.
- **Build big, scale down:** every object is drawn at its largest on-screen size; `will-change`
  only while moving, so the frame re-rasterises sharp at rest.
- **The live wallet** sits at its native size at rest (punch-in at most 1.25×). Matched cuts use
  the eye rectangles from the face; on the way out it swaps to a still image, then to the
  you-dot.
- **Two canvases:** the procedural tab field (about 2,000 items) and a giant face from the
  wallet's `face.js` (pixel ratio ≤ 2, no glow).
- **Control:** one clicker, a paused timeline driving a state machine: → next, ← back, R reset,
  V plays this beat's fallback recording. Live steps are click-driven, never on a timer.
  Offline build on the stage laptop.

## Facts we may say

| Fact | Source | Confidence |
| --- | --- | --- |
| Two in three Swiss firms under ten people have no website | localsearch & HSLU, SME Digital Pulse 2025 | high |
| AI traffic to US travel sites +539 %, holidays 2025 | Adobe Analytics via Digital Commerce 360, Jan 2026 | high |
| Q&A: online agencies take 29.6 % of EU hotel bookings; Booking Holdings has 71 % of that | HOTREC European Hotel Distribution Study 2024 | high |
| Q&A: 3 % of Swiss SMEs take bookings online | localsearch & HSLU 2025 | high |
| Q&A: about 92 % of Swiss hotels are independent | Horwath HTL 2021 | medium |
| Q&A: commissions "typically 15–18 %, they vary" | Best Western FDD 2025 | medium |

**Never say:** "Adobe signs…" or "C2PA-compliant"; "the register signed her description" (it
vouches for identity and UID, not facts); "Every offer is signed" as a universal claim; "in the
browser" (unless a JS verifier ships); "AI names the big chains"; +3,500 % or "31 % more
conversions"; Booking.com by name or the "500 % fraud" figure; "scripted" (say "demo"); UIDs or
addresses on screen.

## What is missing

| Severity | Gap | Fix | Owner | Effort |
| --- | --- | --- | --- | --- |
| blocker | The wallet shows nothing of the flow yet (status.md step 3, "human layer": in progress). The agent side is done end to end: post → offers → shortlist → negotiate → book | the wallet shows request, offers (seal colour, name, price), the refused forged business, the winner with its signed facts and the signed approval; a demo runner in `code/demo` that drives the real flow without live speech | dev member 1 | 8–12 h |
| blocker | Verdicts must be computed, never hard-coded | server-side verdicts (1 h); JS verifier optional (4–5 h); without either, drop "The signatures are real" | dev | 1–5 h |
| blocker | Presentation app not started (`code/apps/presentation`) | camera, tab field, face hand-off, QR, per-beat recordings | Max + pitch | ~20 h |
| blocker | "Adobe Business Registry" is not a real Adobe product; Alpina, Rheinblick, Spalenhof, the lawyer and Tuttie carry an "adobe" seal | rename the issuer to a neutral demo platform, re-run `issue_seals.py`, tests, status.md (owner of `code/aps/` decides) | dev member 2 | 45 min |
| high | The winner's reason must be real | Tuttie's shortlist over the signed facts (quiet, dogs, late arrival) and the private budget, with a test; shown as one line on the winner card | dev member 1 | 2 h |
| high | face.js is not stage-ready at giant size | idle freeze, pixel ratio cap, glow off, expose eye rectangles, move to `apps/shared` | dev | 2–3 h |
| high | The QR would hit the shared server (`/reset` clears everyone) | static stage build for jurors: no `/chat`, no `/reset`, no user key; back-row scan test | Max + Thomas | 3–4 h |
| high | No fallback, no offline build | per-beat recordings after code freeze, kiosk script, USB copy | dev + Thomas | 3–4 h |
| high | Repo hygiene the jury will see | `license.txt` (2026, names), team profiles in the readme, readme tested on a clean machine, repo link on the QR page | all | 30 min |
| high | Rubric unknown; does Q&A count inside the 3:00? | ask the organisers / Adobe mentor today; if Q&A is inside, cut to about 190 words | Thomas | 5 min |
| medium | No proof view for Q&A | signed timeline one tap from the winner card | dev | 2–3 h |
| medium | Stage hardware untested | 1920×1080, fps overlay, service worker off, 10 timed runs | Thomas + dev | 2–3 h |
| resolved | Small vs chain hotel, marketplace, shortlist, bargaining, booking an agreement | done by the dev team (status.md): Alpina large, Rheinblick medium, Gästehaus am Rhein small; post → offers → shortlist → negotiate → book runs end to end | — | — |

## Ideas worth trying

1. After the signed tap, the eyes smile at Thomas: the third squint beat, no words.
2. The juror build gets a "forge" button, so each juror watches their own fake die.
3. Show the chain's row dropping on budget, so "small wins" is visible, not stated.
4. A small gold card ("Booked · signed") lands on Anna's eyes in the pull-out (a one-card
   owner glimpse).
5. Tapping the winner flips it to its signed timeline, for Q&A.

## Decisions for the team

1. **Spine:** one camera world with the human lines on top. Recommended.
2. **Throughline:** freeze "Signed businesses reach you. Fakes never do." Recommended.
3. **The request** "quiet, Basel, after midnight, with my dog, under 160" so Gästehaus am
   Rhein (small, Anna) wins on real data. Recommended; agree with the dev team so the demo data
   and the bargaining numbers keep this outcome.
4. **Live offers** from the running marketplace and hotel agents on the stage laptop.
   Recommended; if live LLM calls are too slow or risky on stage, say "fetched for stage".
5. **Verification:** server verdicts first, JS port only if there is time. Drop "in the browser".
6. **Adobe line:** keep the Content Credentials analogy; first on the cut list.
7. **Tuttie's voice:** silent eyes, no speaker dependency. Recommended.
8. **Clicker:** Thomas fires every move; Max holds only the fallback key and the checkpoints.
