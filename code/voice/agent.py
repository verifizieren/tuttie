"""Tuttie's voice: a LiveKit agent that listens and speaks for the user's Tuttie.

It is ears and mouth only, and it keeps quiet: no greeting, a short filler that matches the
request only when Tuttie starts using a tool for it (the first tool event on the timeline), then
Tuttie's answer. Small talk and quick answers get no filler. What the user says (ElevenLabs
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

from assistant.card_commands import card_choice

import httpx
from dotenv import load_dotenv
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, StopResponse, cli
from livekit import rtc
from livekit.plugins import elevenlabs, silero

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ASSISTANT_URL = os.environ.get("ASSISTANT_URL", f"http://127.0.0.1:{os.environ.get('ASSISTANT_PORT', '4040')}")
# ElevenLabs voice: TUTTIE_VOICE_ID in code/.env (library voices such as "Germain", XJeDCVLci9KGsGtVpFLM,
# need a paid ElevenLabs plan). The default "Eric" is one of the free conversational voices.
VOICE_ID = os.environ.get("TUTTIE_VOICE_ID", "cjVigY5qzO86Huf0OWal")
TTS_MODEL = "eleven_flash_v2_5"  # the fastest ElevenLabs model: the first words come in a fraction of a second
LANGUAGE = "en"  # Tuttie only speaks English; without this, an accent was heard as German
MIN_WORDS = 2    # shorter fragments are noise, not a request
VAD_THRESHOLD = .65  # Silero's default is .5; background voices stay below this more often
MIN_SPEECH_S = .2    # a click or a clatter is shorter than that
# Interrupting Tuttie takes real words; a false interruption (no words follow) resumes its speech.
INTERRUPTION = {"mode": "vad", "min_words": 2, "min_duration": .5, "resume_false_interruption": True}
STT_MODEL = "scribe_v2_realtime"
KEYTERMS = ["Tuttie", "Basel", "Gästehaus am Rhein", "Rheinblick", "Alpina", "Luna", "Kleinbasel"]  # heard right

# A filler that matches what the user asked, said when Tuttie starts a tool for it; varied so it never drones.
FILLERS = {
    "task": ["Let me take a look.", "Sure, let me check.", "On it, one second."],
    "question": ["Hmm, let me think.", "Good question, one moment."],
    "other": ["Sure, one moment.", "Okay, give me a second."],
}
TASK_WORDS = ("book", "find", "search", "hotel", "room", "reserve", "need", "want", "get me", "pay", "look for")
QUESTION_WORDS = ("what", "how", "why", "when", "where", "who", "which", "can", "could", "is", "are", "do", "does",
                  "will", "would", "should")
# Quick end of turn: answer soon after the user stops (at most 2 s when the model is unsure).
ENDPOINTING = {"min_delay": .3, "max_delay": 2.0}
# The only update in between: the user has to act. The answers themselves come from Tuttie.
UPDATES = {"approval": "Please confirm with Face ID."}


def francs(match: re.Match) -> str:
    """An amount as it is said: "CHF 128" is "128 francs", "CHF 1" is "1 franc"."""
    amount = match.group(1) or match.group(2)
    return f"{amount} {'franc' if amount == '1' else 'francs'}"


BRACKETS = re.compile(r"\s*\[[^\]\n]{0,60}\]")   # notes the model put in brackets: [3], [confirmed]
CLOCK = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")  # 24-hour times: 18:00, 00:52


def clock(match: re.Match) -> str:
    """A 24-hour time as it is said: "18:00" is "6 pm", "00:52" is "12:52 am", "00:00" is "midnight"."""
    hour, minute = int(match.group(1)), int(match.group(2))
    if minute == 0 and hour in (0, 12):
        return "midnight" if hour == 0 else "noon"
    said = str(hour % 12 or 12) + (f":{minute:02d}" if minute else "")
    return f"{said} {'am' if hour < 12 else 'pm'}"


def spoken(answer: str) -> str:
    """An answer as it should sound: amounts in francs, temperatures in degrees, times as said
    (6 pm), no bracketed notes, no markdown, no emoji."""
    text = BRACKETS.sub("", answer)
    text = CLOCK.sub(clock, text)
    text = re.sub(r"\bCHF\s?(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s?CHF\b", francs, text)
    text = re.sub(r"\bCHF\b", "francs", text)
    text = re.sub(r"\s?°\s?[CF]\b|\s?°", " degrees", text)  # "11.6 °C" is said "11.6 degrees"
    text = re.sub(r"(\d)\s?%", r"\1 percent", text)
    text = re.sub(r"[*_`#]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FFFF☀-➿]", "", text)
    return " ".join(line for line in text.splitlines() if not line.strip().lower().startswith("ignored:")).strip()


def meaningful(text: str) -> bool:
    """A real request, not a noise tag like "(laughs)" or a stray word from the room."""
    words = re.findall(r"[A-Za-zÀ-ÿ']+", re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text))
    return card_choice(text) is not None or len(words) >= MIN_WORDS


def filler_kind(text: str) -> str:
    """What kind of request it is, for a filler that fits: a task, a question or anything else."""
    lowered = text.lower().strip()
    if any(word in lowered for word in TASK_WORDS):
        return "task"
    first = lowered.split()[0] if lowered.split() else ""
    return "question" if lowered.endswith("?") or first in QUESTION_WORDS else "other"


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
        self.asked = None  # what the user asked last, until Tuttie uses a tool for it or answers

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        text = (new_message.text_content or "").strip()
        if meaningful(text):  # noise and stray words are not requests
            self.turns += 1
            self.asked = text
            await self.http.post("/voice/say", json={"room": self.room, "text": text})
        raise StopResponse()  # Tuttie answers through the timeline, spoken by follow()

    def filler(self) -> str | None:
        """A filler fitting the last request, once, when Tuttie starts a tool for it."""
        if self.asked is None or self.session.agent_state == "speaking":
            return None
        options = FILLERS[filler_kind(self.asked)]
        self.asked = None
        return options[self.turns % len(options)]


def voice_on(room: rtc.Room) -> bool:
    """The wallet is in voice mode (card open, not typing): it sets the attribute voice=on.

    The wallet stays in the room with the microphone off while the card is closed, so voice
    starts at once; Tuttie only speaks while voice mode is on.
    """
    return any(p.attributes.get("voice") == "on" for p in room.remote_participants.values())


async def follow(session: AgentSession, agent: Tuttie, http: httpx.AsyncClient, room: rtc.Room) -> None:
    """Speak every answer and the approval prompt from the conversation's timeline, in voice mode."""
    said: set[str] = set()

    def say(text: str) -> None:
        if voice_on(room):
            session.say(text)

    async with http.stream("GET", "/voice/events", params={"room": room.name}, timeout=None) as stream:
        async for line in stream.aiter_lines():
            if line.startswith("event: reset"):
                said.clear()
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:])
            if event["kind"] == "answer":
                said.clear()  # the next turn may prompt again
                agent.asked = None  # answered without (or after) a tool: no filler any more
                say(spoken(event["summary"]))
                continue
            # The first tool for the request gets a filler; opening the turn, thinking and closing the
            # card do not (a goodbye follows).
            if event["kind"] not in ("turn", "thinking", "close") and (line := agent.filler()):
                say(line)
            if prompt := update_for(event, said):
                say(prompt)


def prewarm(proc: JobProcess) -> None:
    """Load the voice activity model once per worker process, before any wallet connects."""
    proc.userdata["vad"] = silero.VAD.load(activation_threshold=VAD_THRESHOLD, min_speech_duration=MIN_SPEECH_S)


# Idle processes wait with the model loaded, so opening the card only joins one.
server = AgentServer(setup_fnc=prewarm, num_idle_processes=2)


@server.rtc_session()
async def entry(ctx: JobContext) -> None:
    """One voice session per wallet room (rooms are created by /voice/token)."""
    key = os.environ["ELEVENLABS_KEY"]
    http = httpx.AsyncClient(base_url=ASSISTANT_URL, timeout=20,
                             headers={"Authorization": f"Bearer {os.environ['LIVEKIT_API_SECRET']}"})
    session = AgentSession(
        # Only clear, near speech counts: a higher threshold and a minimum length keep voices and
        # noise in the background from starting a turn.
        vad=ctx.proc.userdata["vad"],
        stt=elevenlabs.STT(api_key=key, model=STT_MODEL, keyterms=KEYTERMS, language_code=LANGUAGE,
                           tag_audio_events=False),
        tts=elevenlabs.TTS(api_key=key, voice_id=VOICE_ID, model=TTS_MODEL, language=LANGUAGE),
        turn_handling={"interruption": INTERRUPTION, "endpointing": ENDPOINTING},
    )
    agent = Tuttie(ctx.room.name, http)
    await session.start(agent, room=ctx.room)  # connects to the room itself
    follower = asyncio.create_task(follow(session, agent, http, ctx.room))

    async def cleanup() -> None:
        follower.cancel()
        await http.aclose()

    ctx.add_shutdown_callback(cleanup)


if __name__ == "__main__":
    cli.run_app(server)
