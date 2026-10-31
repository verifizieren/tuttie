# Voice agent (issues #2, #3) — not started

Swiping the agent card up in the wallet opens a voice agent (e.g. built with LiveKit).

- Live mode: speech → text → the user's agent (`assistant/`, same as typing in the chat),
  and its answers → speech.
- Scripted mode (for the stage): the agent's lines are known from the storyline, so they are
  played directly instead of relying on live speech recognition. The actions behind them
  still run for real (`documentation/concept.md`, "scripted, but real").
- Keep the voice layer thin: it only converts speech and text; all logic stays in the
  user's agent.
