"""Tuttie's voice: a LiveKit agent that listens and speaks for the user's Tuttie.

It is ears and mouth only, and it keeps quiet: no greeting, a short confirmation as soon as
the user has asked something, then Tuttie's answer. What the user says (ElevenLabs
speech-to-text, Silero voice activity) goes into the same conversation the wallet types into
(POST /voice/say on the assistant), so every tool call runs exactly as when typing: context,
signed MCP calls, bargaining, booking. It follows that conversation's timeline (GET
/voice/events) and speaks every answer, also to turns the user started by touch (e.g. the
booking after swiping), and asks for the Face ID approval.

The user can talk at any time, also while Tuttie works or speaks; what they say is queued as
the next message. Robust in a noisy room: English only, fragments without meaning (one word,
noises) are dropped, and only real words (two or more, half a second) interrupt Tuttie; if a
noise cut it off and no words follow, it carries on. The wallet can mute the microphone.

Run from code/: python -m voice.agent start   (scripts/run_all.py does this when configured)
"""

import asyncio
import json
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, StopResponse, cli
from livekit.plugins import elevenlabs, silero

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ASSISTANT_URL = os.environ.get("ASSISTANT_URL", f"http://127.0.0.1:{os.environ.get('ASSISTANT_PORT', '4040')}")
# ElevenLabs voice: TUTTIE_VOICE_ID in code/.env (library voices such as "Germain", XJeDCVLci9KGsGtVpFLM,
# need a paid ElevenLabs plan). The default "Eric" is one of the free conversational voices.
VOICE_ID = os.environ.get("TUTTIE_VOICE_ID", "cjVigY5qzO86Huf0OWal")
TTS_MODEL = "eleven_turbo_v2_5"  # more natural than Flash, still quick
LANGUAGE = "en"  # Tuttie only speaks English; without this, an accent was heard as German
MIN_WORDS = 2    # shorter fragments are noise, not a request
VAD_THRESHOLD = .65  # Silero's default is .5; background voices stay below this more often
MIN_SPEECH_S = .2    # a click or a clatter is shorter than that
# Interrupting Tuttie takes real words; a false interruption (no words follow) resumes its speech.
INTERRUPTION = {"mode": "vad", "min_words": 2, "min_duration": .5, "resume_false_interruption": True}
STT_MODEL = "scribe_v2_realtime"
KEYTERMS = ["Tuttie", "Basel", "Gästehaus am Rhein", "Rheinblick", "Alpina", "Luna", "Kleinbasel"]  # heard right

# A quick confirmation as soon as the user has asked something, varied so it never drones.
CONFIRMATIONS = ["On it.", "Sure.", "Got it.", "One moment.", "Okay."]
# The only update in between: the user has to act. The answers themselves come from Tuttie.
UPDATES = {"approval": "Please confirm with Face ID."}


def spoken(answer: str) -> str:
    """An answer as it should sound: no citations, no markdown, no emoji."""
    text = re.sub(r"\s*\[\d+\]", "", answer)
    text = re.sub(r"[*_`#]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FFFF☀-➿]", "", text)
    return " ".join(line for line in text.splitlines() if not line.strip().lower().startswith("ignored:")).strip()


def meaningful(text: str) -> bool:
    """A real request, not a noise tag like "(laughs)" or a stray word from the room."""
    words = re.findall(r"[A-Za-zÀ-ÿ']+", re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text))
    return len(words) >= MIN_WORDS


def update_for(event: dict, said: set[str]) -> str | None:
    """The short line to speak for a timeline event, once per turn, or None."""
    detail = event.get("detail") or {}
    key = "approval" if event["kind"] == "approval" and event["status"] == "pending" else None
    if key is None or key in said:
        return None
    said.add(key)
    return UPDATES[key]


class Tuttie(Agent):
    """Passes each finished user turn to the user's Tuttie instead of answering itself."""

    def __init__(self, room: str, http: httpx.AsyncClient):
        super().__init__(instructions="Relay only; Tuttie in the assistant answers.")
        self.room = room
        self.http = http
        self.turns = 0

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        text = (new_message.text_content or "").strip()
        if meaningful(text):  # noise and stray words are not requests
            self.session.say(CONFIRMATIONS[self.turns % len(CONFIRMATIONS)])
            self.turns += 1
            await self.http.post("/voice/say", json={"room": self.room, "text": text})
        raise StopResponse()  # Tuttie answers through the timeline, spoken by follow()


async def follow(session: AgentSession, http: httpx.AsyncClient, room: str) -> None:
    """Speak every answer and the approval prompt from the conversation's timeline."""
    said: set[str] = set()
    async with http.stream("GET", "/voice/events", params={"room": room}, timeout=None) as stream:
        async for line in stream.aiter_lines():
            if line.startswith("event: reset"):
                said.clear()
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:])
            if event["kind"] == "answer":
                said.clear()  # the next turn may prompt again
                session.say(spoken(event["summary"]))
            elif prompt := update_for(event, said):
                session.say(prompt)


server = AgentServer()


@server.rtc_session()
async def entry(ctx: JobContext) -> None:
    """One voice session per wallet room (rooms are created by /voice/token)."""
    await ctx.connect()
    key = os.environ["ELEVENLABS_KEY"]
    http = httpx.AsyncClient(base_url=ASSISTANT_URL, timeout=20,
                             headers={"Authorization": f"Bearer {os.environ['LIVEKIT_API_SECRET']}"})
    session = AgentSession(
        # Only clear, near speech counts: a higher threshold and a minimum length keep voices and
        # noise in the background from starting a turn.
        vad=silero.VAD.load(activation_threshold=VAD_THRESHOLD, min_speech_duration=MIN_SPEECH_S),
        stt=elevenlabs.STT(api_key=key, model=STT_MODEL, keyterms=KEYTERMS, language_code=LANGUAGE,
                           tag_audio_events=False),
        tts=elevenlabs.TTS(api_key=key, voice_id=VOICE_ID, model=TTS_MODEL, language=LANGUAGE),
        turn_handling={"interruption": INTERRUPTION},
    )
    await session.start(Tuttie(ctx.room.name, http), room=ctx.room)
    follower = asyncio.create_task(follow(session, http, ctx.room.name))

    async def cleanup() -> None:
        follower.cancel()
        await http.aclose()

    ctx.add_shutdown_callback(cleanup)


if __name__ == "__main__":
    cli.run_app(server)
