# Pitch handoff

Where the pitch work stands, so anyone (teammate or AI agent) can pick it up. Last updated:
31 Oct 2026, repo at `b35b271`. Read [project-summary.md](project-summary.md) first.

## Files

| File | What it is |
| --- | --- |
| [project-summary.md](project-summary.md) | Tuttie in one page: problem, idea, flow, what is built |
| [storyline.md](storyline.md) | Storyline v3 (draft): shot table with exact spoken lines, zoom system, facts we may and may not say, missing work, decisions |
| [playbook.md](playbook.md) | Research on winning short pitches (hackathon finals, Apple keynotes, TED, the Adobe brief): 10 rules, jury checklist, demo safety, delivery, anti-patterns |

## How we got here

1. A first slide deck (9 slides, 17 clicks, full sentences) was rejected: too much text, too
   many pages for 3:00. Rule since then: the audience listens, it does not read.
2. Brainstorm with several AI agents: 5 storyline drafts with different story engines (keynote
   reveal, TED story, one-shot camera, the great inversion, Tuttie as co-presenter), each
   critiqued twice and rewritten; 2 directors; a research sweep on winning pitches with
   verified numbers; 4 audits (jury criteria, pitch rules, build effort, honesty).
3. Storyline v3 merges the camera-led and the human-led option and was adapted to the latest
   demo data (three hotel agents; the small Gästehaus am Rhein and its owner Anna win).

## Agreed so far

- 3:00 hard including the live demo; plan 2:34 so a slow demo still fits.
- Almost no text on screen (14 words in v3); one continuous camera, no slide cuts.
- The demo is a run through the real wallet; words and choices may be fixed, verification never.
- Say "demo", not "scripted"; one honesty line on stage: "The hotels and the register are demo.
  My request was a button. The signatures are real."

## Open decisions (see storyline.md for recommendations)

1. Freeze the throughline "Signed businesses reach you. Fakes never do."
2. Confirm the demo request and outcome with the dev team (Gästehaus am Rhein wins), so the data
   and the bargaining numbers keep it.
3. Live marketplace calls on stage, or "fetched for stage".
4. Keep the Content Credentials analogy line or cut it.
5. Who holds the clicker (recommended: Thomas), who holds the fallback key.
6. English or German on stage.
7. Rename the "Adobe Business Registry" demo issuer (it is not a real Adobe product): the pitch team asks for it, dev member 2 (owner of `code/aps/`) decides and re-runs `issue_seals.py`.
8. Ask the organisers whether Q&A counts inside the 3:00.

## Next steps

| # | Step | Owner | Needs |
| --- | --- | --- | --- |
| 1 | Answer the open decisions above | pitch team | 15 min together |
| 2 | Wallet human layer: request, offers with seal colours, the refused forged business, winner, signed approval | dev member 1 | status.md step 3 (in progress) |
| 3 | Seal verdicts computed by the services and shown in the wallet, never hard-coded; without them, drop "The signatures are real" | dev | storyline.md, missing work |
| 4 | Presentation page `code/apps/presentation/`: camera, tab field, face hand-off, QR | pitch + dev | storyline.md zoom system |
| 5 | Juror build for the QR (no shared `/reset`, no user key) | dev | — |
| 6 | Fallback recordings per beat after code freeze, offline build on the stage laptop | dev + Thomas | step 2-4 done |
| 7 | Repo hygiene the jury sees: `license.txt`, team profiles in the readme, readme tested on a clean machine | everyone | — |
| 8 | 10 timed run-throughs on the stage hardware | Thomas | steps 2-6 |

## Outside the repo

An earlier stand-alone pitch demo ("Two Webs", before the Tuttie name) with an HTML deck and a
phone remote with a 3:00 timer lives on Thomas's laptop (`hackbasel/demowebsite/`). Useful
parts for the presentation page: the phone remote (`remote.html`, `server.js`) and the step
engine; the deck itself is superseded by storyline v3.
