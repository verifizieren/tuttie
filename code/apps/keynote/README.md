# Keynote: the pitch deck

The three-minute pitch as a static web page, served by the assistant at `/keynote/`, on the
same origin as the wallet (`/wallet/`) and the owner view (`/owner/`). Plain HTML, CSS and ES
modules: no build step, no CDN at runtime. Only the live wallet, the owner view and the QR target
need the network. The assistant serves the folder from disk (`assistant/app.py`, static mount
at `/`), so deck changes need no build and no restart. Open it at `/keynote/` on the same
server as the wallet (live: https://web4.mendes.dev/keynote/ once on `main`).

The speaker is the star: the screen is black most of the time, shows at most three words, and
never shows the spoken sentence. The spoken lines are in `SPEAKER-NOTES.md` and the presenter view.

## Controls (a clicker sends PageDown/PageUp)

| Key | Action |
|---|---|
| → Space PageDown ↓ | next step |
| ← PageUp ↑ | previous step |
| Home / End | first / last step |
| B or . | black screen on/off |
| F | fullscreen |
| N | presenter view in a second window (current and next line, cue, clock, time against plan) |
| V | play the fallback recording in the phone, from the start (again: back to live) |
| L | switch between live wallet and recording without restarting it |
| R | reset: back to the start, fresh demo conversation (`POST /reset`), wallet reloaded |

Keys also work while a framed page has focus, except while typing in one of its fields.

Only one deck tab drives the wallet and follows the presenter view: the one used last (any
key in it claims the stage). Other deck tabs of the same browser turn passive (a small grey
"passive" mark), because all tabs share one wallet session. A clicker press that fires twice,
or a held key, moves one step only.

## Beats

0 black · 1 Anna's guesthouse (photo, slow 1.03 push) · 2 black, then the cheap listing ·
3 Tuttie's eyes · 4 demo: the eyes move into the phone and the real wallet takes over, side
words "Never asked." and "One tap." · 5 black, the honesty line is spoken (hotels and register
are demo, signatures are real) · 6 2000 website → 2033 signature ·
7 one more thing: Anna's owner view in a laptop frame (optional) · 8 closing lines, then QR code.

## The demo (beat 4)

The phone shows the real wallet in `<iframe id="wallet">` (no microphone permission, so the live
wallet does not hear the speaker). `demo.js` supplies input and timing only: each demo click runs
the matching step of `createDemo(iframe).steps` (open, ask, forged, like, approve, done), once
per reset, and only when moving forward one click. Entering the demo beat runs "open": the
wallet's microphone is muted first (the frame has no microphone permission), Tuttie's card
opens, and the big eyes land on her awake eyes in the open card. "ask" posts the request to
`POST /chat` for the wallet's own conversation, so Tuttie stays awake and shows her progress. Steps can wait on the wallet (offers take some
seconds); the stage shows nothing while they wait, the presenter view shows "WAITING". If
`demo.js` is missing or fails, the deck still runs and the demo clicks do nothing.

The fallback recording is `media/fallback.webm` (390x844 at 2x), shown at exactly the iframe's
size. It is loaded on the first V or L; if it is missing, nothing changes on stage.

## Options

- `?owner=0` skips beat 7 (or set `OWNER_BEAT = false` in `beats.js`).
- `?step=n` opens step n (rehearsal), without running demo steps.
- `?wallet=<url>` frames another wallet path on the same origin (layout checks only).

Beat 7 shows `img/owner.webp`, a screenshot of the real owner view (Gästehaus am Rhein, review
before deploy), so it needs no sign-in on stage.

## Files

`index.html`, `deck.css`, `deck.js` (stage, step machine, phone, keys), `beats.js` (beats, steps,
spoken lines and cues; shared with the presenter view), `eyes.js` (Tuttie's eyes),
`presenter.html` + `presenter.js`, `demo.js` (demo driver), `img/` (photo, QR code),
`fonts/` (Inter), `media/` (fallback recording). Credits: `CREDITS.md`.
