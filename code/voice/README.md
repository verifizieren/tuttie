# Voice agent (issues #2, #3)

Talk to Tuttie in the wallet. While the wallet is on screen it is already in a LiveKit room for
its conversation, with the microphone off, and the voice agent is there too; opening Tuttie's
card (not typing) only switches the microphone on and Tuttie's voice up, so voice starts at
once. The wallet tells the agent with a participant attribute (`voice: on|off`); Tuttie speaks
only while it is on. Tuttie's eyes pulse with its voice and open up while the user talks.

```
wallet (hooks/useVoice.js) ──wss /rtc──► assistant (assistant/voice.py, proxy) ──► LiveKit server (:7880)
                           ──media──────► LiveKit on the public IP: TCP 4042, UDP 4043
voice agent (voice/agent.py) ◄─── LiveKit room ───► ElevenLabs: speech-to-text (Scribe v2 realtime), voice (Flash v2.5)
voice agent ──POST /voice/say──► the same Tuttie conversation as typing (all tools, signatures, MCP)
voice agent ◄─GET /voice/events── its timeline: speaks the answers and the Face ID prompt
```

- The voice layer stays thin: it never decides anything. What the user says becomes a message
  to the user's Tuttie, exactly like typing; Tuttie's answers are spoken.
- Concise by design: no greeting; a filler that fits the request ("Let me take a look." for a
  task, "Hmm, let me think." for a question) only when Tuttie starts a tool for it (its first
  tool event on the timeline), never for small talk or quick answers; then Tuttie's answer;
  the only update in between is "Please confirm with Face ID."
- The user can speak and interrupt at any time, also while Tuttie works or speaks (a new
  message waits for the current one). Robust in a noisy room: English only (speech-to-text,
  voice and Tuttie's answers); the phone's noise suppression, echo cancellation and voice
  isolation clean the microphone; a stricter voice detector (threshold .65, at least 0.2 s);
  fragments under two words or noise tags are dropped; only two or more words (0.5 s) interrupt
  Tuttie, and it resumes after a false interruption. The dock's mic button mutes the microphone.
- Fast: Tuttie and the hotel agents on Claude Haiku 5.5 without thinking (`LLM_MODEL`,
  `AGENT_LLM_MODEL`; ~1 s per round, against ~2-3 s for a thinking model); ElevenLabs Flash v2.5
  (first audio in ~0.15 s; Turbo v2.5 is no faster) and Scribe v2 realtime; end of turn after
  0.3-2 s; the voice model loaded once per worker, two workers kept ready; the wallet joins the
  room ahead. From starting to speak a hotel request to hearing the answer: about 8 s (context,
  market, bargaining, answer), was 14 s.
- Amounts are said in francs ("CHF 128" is spoken as "128 francs").
- Voice: the demo server uses "Germain" (`TUTTIE_VOICE_ID=XJeDCVLci9KGsGtVpFLM`,
  a library voice, needs a paid plan); without it the free "Eric".
- The wallet shows each spoken answer word by word in step with the voice (LiveKit
  "lk.transcription" streams), then the full formatted answer. After a typed message Tuttie
  answers in text only (no voice) until the user taps its face or the mic button.
- Self-hosted LiveKit (`livekit.yaml`): the team server only exposes ports 4000-4049, so
  signaling goes through the assistant on the wallet's own https origin (`/rtc`) and media uses
  TCP 4042 / UDP 4043 on `LIVEKIT_NODE_IP`.

Phones: the team server lets no UDP in, and iPhones don't use LiveKit's plain TCP port, so
their ICE failed (seen in the LiveKit log as failed UDP pairs). A TURN relay (coturn,
`turnserver.conf`) on plain TCP 4044 carries their audio to LiveKit on the same host; LiveKit
hands it to every client. It relays only to this server's own IP, and the audio stays
encrypted end to end (DTLS-SRTP), so it needs no certificate. coturn is unpacked without root:
`apt-get download coturn libpq5 libevent-extra-2.1-7t64 libevent-openssl-2.1-7t64
libevent-pthreads-2.1-7t64`, then `dpkg-deb -x <deb> ~/.local/coturn/root` for each; set
`TURN_SECRET` in `.env`.

Setup: `code/.env` needs `ELEVENLABS_KEY`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`,
`LIVEKIT_URL` and `LIVEKIT_NODE_IP` (see `.env.example`), and the LiveKit server binary in
`~/.local/livekit/livekit-server` (or `LIVEKIT_SERVER`). `scripts/run_all.py` then starts the
LiveKit server and the voice agent too. Optional: `TUTTIE_VOICE_ID` picks the ElevenLabs voice
(library voices need a paid ElevenLabs plan; the default "Eric" works on every plan).
