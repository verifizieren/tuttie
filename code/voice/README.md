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
- Concise by design: no greeting, a short varied confirmation ("On it.") as soon as the user
  has asked, then Tuttie's answer; the only update in between is "Please confirm with Face ID."
  The user can talk over it at any time.
- Self-hosted LiveKit (`livekit.yaml`): the team server only exposes ports 4000-4049, so
  signaling goes through the assistant on the wallet's own https origin (`/rtc`) and media uses
  TCP 4042 / UDP 4043 on `LIVEKIT_NODE_IP`.

Setup: `code/.env` needs `ELEVENLABS_KEY`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`,
`LIVEKIT_URL` and `LIVEKIT_NODE_IP` (see `.env.example`), and the LiveKit server binary in
`~/.local/livekit/livekit-server` (or `LIVEKIT_SERVER`). `scripts/run_all.py` then starts the
LiveKit server and the voice agent too. Optional: `TUTTIE_VOICE_ID` picks the ElevenLabs voice
(library voices need a paid ElevenLabs plan; the default "River" works on every plan).
