# Voice agent (issues #2, #3)

Talk to Tuttie in the wallet: while Tuttie's card is open (and the user is not typing), the
wallet joins a LiveKit room for its conversation, sends the microphone and plays Tuttie's
voice. Tuttie's eyes pulse with its voice and open up while the user talks.

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
  task, "Hmm, let me think." for a question) only if Tuttie has not answered within 1.5 s; then
  Tuttie's answer; the only update in between is "Please confirm with Face ID."
- The user can speak and interrupt at any time, also while Tuttie works or speaks (a new
  message waits for the current one). Robust in a noisy room: English only (speech-to-text,
  voice and Tuttie's answers); the phone's noise suppression, echo cancellation and voice
  isolation clean the microphone; a stricter voice detector (threshold .65, at least 0.2 s);
  fragments under two words or noise tags are dropped; only two or more words (0.5 s) interrupt
  Tuttie, and it resumes after a false interruption. The dock's mic button mutes the microphone.
- Fast: ElevenLabs Flash v2.5 (first words in about 0.3 s), end of turn after 0.3-2 s, hotel
  agents on a fast model (`AGENT_LLM_MODEL`, default gpt-4.1-mini). A spoken request to Tuttie's
  answer took about 14 s end to end (context, market, bargaining, answer).
- Voice: the demo server uses "Germain" (`TUTTIE_VOICE_ID=XJeDCVLci9KGsGtVpFLM`,
  a library voice, needs a paid plan); without it the free "Eric".
- The wallet shows each spoken answer word by word in step with the voice (LiveKit
  "lk.transcription" streams), then the full formatted answer. After a typed message Tuttie
  answers in text only (no voice) until the user taps its face or the mic button.
- Self-hosted LiveKit (`livekit.yaml`): the team server only exposes ports 4000-4049, so
  signaling goes through the assistant on the wallet's own https origin (`/rtc`) and media uses
  TCP 4042 / UDP 4043 on `LIVEKIT_NODE_IP`.

Setup: `code/.env` needs `ELEVENLABS_KEY`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`,
`LIVEKIT_URL` and `LIVEKIT_NODE_IP` (see `.env.example`), and the LiveKit server binary in
`~/.local/livekit/livekit-server` (or `LIVEKIT_SERVER`). `scripts/run_all.py` then starts the
LiveKit server and the voice agent too. Optional: `TUTTIE_VOICE_ID` picks the ElevenLabs voice
(library voices need a paid ElevenLabs plan; the default "Eric" works on every plan).
