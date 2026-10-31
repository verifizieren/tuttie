"""Tuttie's voice: a LiveKit agent that listens and speaks for the user's Tuttie.

It is ears and mouth only, and it keeps quiet: no greeting, a short confirmation as soon as
the user has asked something, then Tuttie's answer. What the user says (ElevenLabs
speech-to-text, Silero voice activity) goes into the same conversation the wallet types into
(POST /voice/say on the assistant), so every tool call runs exactly as when typing: context,
signed MCP calls, bargaining, booking. It follows that conversation's timeline (GET
/voice/events) and speaks every answer, also to turns the user started by touch (e.g. the
booking after swiping), and asks for the Face ID approval. The user can talk over it at any time.

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
# need a paid ElevenLabs plan); the default "River" works on every plan.
VOICE_ID = os.environ.get("TUTTIE_VOICE_ID", "SAz9YHcvj6GT2YYXdXww")
TTS_MODEL = "eleven_flash_v2_5"  # the fastest ElevenLabs voice model
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
        if text:
            self.session.say(CONFIRMATIONS[self.turns % len(CONFIRMATIONS)], allow_interruptions=True)
            self.turns += 1
            await self.http.post("/voice/say", json={"room": self.room, "text": text})
        raise StopResponse()  # Tuttie answers through the timeline, spoken by follow()


async def follow(session: AgentSession, http: httpx.AsyncClient, room: str) -> None:
    """Speak short updates and every answer from the conversation's timeline as they come."""
    said: set[str] = set()
    async with http.stream("GET", "/voice/events", params={"room": room}, timeout=None) as stream:
        async for line in stream.aiter_lines():
            if line.startswith("event: reset"):
                said.clear()
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:])
            if event["kind"] == "answer":
                said.clear()  # the next turn may update again
                session.say(spoken(event["summary"]), allow_interruptions=True)
            elif line := update_for(event, said):
                session.say(line, allow_interruptions=True)


server = AgentServer()


@server.rtc_session()
async def entry(ctx: JobContext) -> None:
    """One voice session per wallet room (rooms are created by /voice/token)."""
    await ctx.connect()
    key = os.environ["ELEVENLABS_KEY"]
    http = httpx.AsyncClient(base_url=ASSISTANT_URL, timeout=20,
                             headers={"Authorization": f"Bearer {os.environ['LIVEKIT_API_SECRET']}"})
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=elevenlabs.STT(api_key=key, model=STT_MODEL, keyterms=KEYTERMS),
        tts=elevenlabs.TTS(api_key=key, voice_id=VOICE_ID, model=TTS_MODEL),
    )
    await session.start(Tuttie(ctx.room.name, http), room=ctx.room)
    follower = asyncio.create_task(follow(session, http, ctx.room.name))

    async def cleanup() -> None:
        follower.cancel()
        await http.aclose()

    ctx.add_shutdown_callback(cleanup)


if __name__ == "__main__":
    cli.run_app(server)
