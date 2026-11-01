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
from assistant.inputs import MAX_MESSAGE_CHARS

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
# When what the user said did not reach Tuttie: never silence.
BUSY = "One moment please."  # too many turns a minute (429): the user can say it again shortly
NOT_PASSED = "Sorry, that did not go through. Could you say it again?"
# After Tuttie recommends a hotel, the choice goes to the user (said once, after the answer).
HANDOFF = "It's your choice: swipe right on the ones you like, or just tell me."


def francs(match: re.Match) -> str:
    """An amount as it is said: "CHF 128" is "128 francs", "CHF 1" is "1 franc"."""
    amount = re.sub(r"['’]", "", match.group(1) or match.group(2))  # Swiss thousands: "1'280" is said 1280
    return f"{amount} {'franc' if amount == '1' else 'francs'}"


# What the model may put in square brackets, cleaned the same way as the wallet's screen
# (apps/wallet/src/lib/activity.js withoutNotes; shared cases in tests/fixtures/answer_notes.json).
# Only what carries nothing to say goes: citations ([3], [3, 4]), a few labels ([confirmed]),
# booking and receipt ids, node ids, approval, offer and mandate ids (also alone in parentheses:
# "Rheinblick (ch.basel.hotel-rheinblick)"). Any other note may be a fact (a fee, "cancelled"), so it is
# kept and only its brackets go. Markdown links keep their text.
LINK = re.compile(r"\[([^\[\]\n]*)\]\(([^()\n]*)\)")
NOTE = re.compile(r"\[([^\[\]\n]{0,60})\]")
CITATION = re.compile(r"\d+(?:\s*,\s*\d+)*")
LABEL = re.compile(r"confirmed|verified|signed|sources?", re.IGNORECASE)
NODE_ID_TOKEN = r"[a-z]{2}(?:\.[a-z0-9-]{1,40}){2,}"  # ch.basel.hotel-rheinblick, not booking.com
NODE_ID = re.compile(NODE_ID_TOKEN)
# Approval, mandate and offer ids (assistant/approvals.py, aps/mandate.py, node/agent.py).
REF_TOKEN = r"(?:ap|md)-[0-9a-f]{8}|of-[a-z0-9-]{1,60}-[0-9a-f]{6}"
REF = re.compile(REF_TOKEN)
INTERNAL = rf"(?:{NODE_ID_TOKEN}|{REF_TOKEN})"
PAREN_IDS = re.compile(rf"\(\s*{INTERNAL}(?:\s*[,;]\s*{INTERNAL})*\s*\)")  # "(ch.basel.x)", "(ap-…, of-…)"
BARE_INTERNAL = re.compile(rf"[ \t]?(?<![\w.@/-]){INTERNAL}(?![\w-]|\.[a-z0-9])")  # spoken only: never read aloud
ID_TOKEN = r"\b(?:BK|RC)-[0-9A-F]{6}\b"  # booking and receipt ids (node/server.py): one pattern for all uses
ID = re.compile(r",?\s*(?:(?:receipt|booking)(?:\s+id)?\s*)?" + ID_TOKEN, re.IGNORECASE)
BARE_ID = re.compile(r"[ \t]?" + ID_TOKEN, re.IGNORECASE)
URL = re.compile(r"\s*(?:https?://|www\.)\S*\s*", re.IGNORECASE)
GONE = "\x00"   # where a note was taken out: the spaces around it are tidied there only
# "Ignored: <business>." when it starts a line (also as "1.", "•", "- **Ignored:**") or a sentence:
# dropped up to the end of its sentence. A lowercase "was ignored: ..." inside a sentence stays.
IGNORED_LINE = re.compile(r"^[ \t]*(?:(?:[-*•>#]|\d+[.)])[ \t]*)?[*_]*Ignored:[^\n]*?(?:[.!?](?=[ \t]|$)[ \t]*|$)",
                          re.MULTILINE)
IGNORED_SENTENCE = re.compile(r"(?<=[.!?])[ \t]+[*_]*Ignored:[^\n]*?(?:[.!?](?=[ \t]|$)|$)", re.MULTILINE)
LINES = re.compile(r"\r\n?|\n|\u2028|\u2029")  # line breaks, split the same way as the wallet
EMPTY_ANSWER = "Done."  # an answer that cleans to nothing
# 24-hour times (two-digit hour) not already said in 12 hours or meant as a duration; a
# trailing "hrs"/"Uhr" is part of the time: "18:00", "00:52", "14:00 hrs" yes; "8:30 pm",
# "1:30 hours", "18:00:30" no.
CLOCK = re.compile(r"(?<![:\d])\b([01]\d|2[0-3]):([0-5]\d)(?:[ \t]*(?:hrs?|uhr)\b)?\b"
                   r"(?!:\d|\s*(?:[ap]\.?m\b|noon|midnight|h\b|hours?\b|min))", re.IGNORECASE)


def link(match: re.Match) -> str:
    """A markdown link: its text; a citation link ("[3](...)") keeps only a parenthesis that is not a URL."""
    text, target = match.group(1).strip(), match.group(2)
    if text and not CITATION.fullmatch(text):
        return text
    return GONE if not target.strip() or URL.fullmatch(target) else f"({target})"


def note(match: re.Match) -> str:
    """A bracketed note: dropped if it says nothing, else its words without the brackets."""
    inner = re.sub(r"^[\s,;]+|[\s,;]+$", "", ID.sub("", match.group(1)))
    if (not inner or CITATION.fullmatch(inner) or LABEL.fullmatch(inner) or NODE_ID.fullmatch(inner)
            or REF.fullmatch(inner)            or inner.lower().startswith("ignored:")):
        return GONE
    glued = match.start() > 0 and match.string[match.start() - 1].isalnum()
    return (" " if glued else "") + inner


def without_notes(raw: str) -> str:
    """Links and bracketed notes cleaned (see above), lines starting with "Ignored:" dropped, and
    the spaces tidied only where something was taken out. Same rules as the wallet's
    withoutNotes. A non-empty answer never cleans to nothing: then its words stay, unbracketed."""
    text = PAREN_IDS.sub(GONE, LINK.sub(link, re.sub(r"\r\n?", "\n", raw)))
    for _ in range(3):  # nested brackets: "[[3]]" leaves "[]" after one pass
        text = NOTE.sub(note, text)
    text = re.sub(r"\x00(?:[ \t]*\x00)+", GONE, text)       # notes in a row count as one
    text = re.sub(r"[ \t]?\x00(?=[.,;:!?)\]'\"’]|$)", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\x00[ \t]?", "", text, flags=re.MULTILINE)
    text = re.sub(r"[ \t]?\x00[ \t]?", " ", text)
    lines = LINES.split(text)
    text = "\n".join(cut for line in lines if (cut := IGNORED_SENTENCE.sub("", IGNORED_LINE.sub("", line))).strip(" \t-*_#>•")
                     or not line.strip())
    # A non-empty answer never cleans to nothing (nor to raw links or forged names): a neutral line.
    return EMPTY_ANSWER if not text.strip() and raw.strip() else text


# Before a time these words make it a length of time ("takes 01:15"); "for" and "in" only when
# "hrs" follows ("for 01:15 hrs"), since "hold the room for 00:52" is a clock time.
DURATION_WORDS = re.compile(r"(?:^|\s)(?:takes|take|took|lasts)(?:\s+(?:about|around|approx\.?))?\s+$",
                            re.IGNORECASE)
MAYBE_DURATION_WORDS = re.compile(r"(?:^|\s)(?:for|in)(?:\s+(?:about|around|approx\.?))?\s+$", re.IGNORECASE)


def clock(match: re.Match) -> str:
    """A 24-hour time as it is said: "18:00" is "6 pm", "00:52" is "12:52 am", "00:00" is "midnight".
    After "takes", "lasts" ... (and after "for", "in" with "hrs") it is a length of time and stays."""
    before = match.string[max(0, match.start() - 12):match.start()]
    if DURATION_WORDS.search(before) or (MAYBE_DURATION_WORDS.search(before)
                                         and re.search(r"hrs?$", match.group(0), re.IGNORECASE)):
        return match.group(0)
    hour, minute = int(match.group(1)), int(match.group(2))
    if minute == 0 and hour in (0, 12):
        return "midnight" if hour == 0 else "noon"
    said = str(hour % 12 or 12) + (f":{minute:02d}" if minute else "")
    return f"{said} {'am' if hour < 12 else 'pm'}"


def spoken(answer: str) -> str:
    """An answer as it should sound: amounts in francs, temperatures in degrees, times as said
    (6 pm), no bracketed notes, no markdown, no emoji."""
    text = without_notes(answer)
    text = BARE_ID.sub("", text)  # ids are never spoken: the wallet shows them
    text = BARE_INTERNAL.sub("", text)  # nor node, approval, offer or mandate ids
    text = re.sub(r"[ \t]?(?:\([ \t]*\)|\[[ \t]*\])", "", text)  # "Booking (BK-…)" leaves no "()"
    text = CLOCK.sub(clock, text)
    amount = r"(\d{1,3}(?:['’]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"  # "1'280" (Swiss thousands) too
    text = re.sub(rf"\bCHF\s?{amount}|{amount}\s?CHF\b", francs, text)
    text = re.sub(r"\bCHF\b", "francs", text)
    text = re.sub(r"\s?°\s?[CF]\b|\s?°", " degrees", text)  # "11.6 °C" is said "11.6 degrees"
    text = re.sub(r"(\d)\s?%", r"\1 percent", text)
    text = re.sub(r"[*_`#]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FFFF☀-➿]", "", text)
    return " ".join(line.strip() for line in LINES.split(text) if line.strip()).strip()


def meaningful(text: str) -> bool:
    """A real request, not a noise tag like "(laughs)" or a stray word from the room."""
    words = re.findall(r"[A-Za-zÀ-ÿ']+", re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text))
    return card_choice(text) is not None or len(words) >= MIN_WORDS


def fitted(text: str) -> str:
    """Long dictation cut to what Tuttie takes (MAX_MESSAGE_CHARS), at a word boundary."""
    if len(text) <= MAX_MESSAGE_CHARS:
        return text
    cut = text[:MAX_MESSAGE_CHARS]
    space = cut.rfind(" ")
    return (cut[:space] if space > MAX_MESSAGE_CHARS // 2 else cut).rstrip()


def filler_kind(text: str) -> str:
    """What kind of request it is, for a filler that fits: a task, a question or anything else."""
    lowered = text.lower().strip()
    if any(word in lowered for word in TASK_WORDS):
        return "task"
    first = lowered.split()[0] if lowered.split() else ""
    return "question" if lowered.endswith("?") or first in QUESTION_WORDS else "other"


PICKED = re.compile(r"^Book (.+?)\.?$")  # what the wallet shows when the user swiped a hotel to book


def pick_ack(event: dict) -> str | None:
    """A short line when the user picked a hotel on the cards (a turn the wallet started, not
    speech): "Nice pick. Let me book Gästehaus am Rhein." Else None."""
    detail = event.get("detail") or {}
    if event.get("kind") != "turn" or detail.get("source") == "voice":
        return None
    match = PICKED.match((detail.get("said") or "").strip())
    return f"Nice pick. Let me book {match.group(1)}." if match else None


def update_for(event: dict, said: set[str]) -> str | None:
    """The short line to speak for a timeline event, once per approval (a booking and then the
    city tax in one turn are two prompts), or None."""
    if event["kind"] != "approval" or event["status"] != "pending":
        return None
    key = f"approval:{(event.get('detail') or {}).get('approval_id') or ''}"
    if key in said:
        return None
    said.add(key)
    return UPDATES["approval"]


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
            if trouble := await self.pass_on(fitted(text)):
                self.asked = None  # no filler for a request Tuttie never got
                self.speak(trouble)
        raise StopResponse()  # Tuttie answers through the timeline, spoken by follow()

    async def pass_on(self, text: str) -> str | None:
        """Send the user's words to Tuttie (POST /voice/say); None if it took them, else the line
        to speak instead (too many turns: BUSY; refused or unreachable: NOT_PASSED)."""
        try:
            response = await self.http.post("/voice/say", json={"room": self.room, "text": text})
        except httpx.HTTPError as error:
            print(f"voice: /voice/say failed: {type(error).__name__}", flush=True)
            return NOT_PASSED
        if response.is_success:
            return None
        print(f"voice: /voice/say answered {response.status_code}", flush=True)
        return BUSY if response.status_code == 429 else NOT_PASSED

    def speak(self, text: str) -> None:
        """Say a short line of the voice layer's own (not one of Tuttie's answers)."""
        self.session.say(text)

    def filler(self) -> str | None:
        """A filler fitting the last request, once, when Tuttie starts a tool for it. An exact
        card command ("next") gets none: the card moves at once, without the LLM."""
        if self.asked is None or self.session.agent_state == "speaking":
            return None
        if card_choice(self.asked):
            self.asked = None
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
    cards = None  # the turn that showed the hotel cards: its answer hands the choice to the user

    def say(text: str) -> None:
        if text.strip() and voice_on(room):
            session.say(text)

    async with http.stream("GET", "/voice/events", params={"room": room.name}, timeout=None) as stream:
        async for line in stream.aiter_lines():
            if line.startswith("event: reset"):
                said.clear()
                cards = None
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:])
            if event["kind"] == "marketplace" and (event.get("detail") or {}).get("phase") == "cards":
                cards = event.get("turn") or "?"
            if event["kind"] == "answer":
                said.clear()  # the next turn may prompt again
                agent.asked = None  # answered without (or after) a tool: no filler any more
                say(spoken(event["summary"]))
                if cards is not None and event.get("turn", "?") == cards:
                    say(HANDOFF)
                    cards = None
                continue
            if ack := pick_ack(event):  # the user swiped a hotel: say what happens next
                agent.asked = None
                say(ack)
                continue
            # The first tool for the request gets a filler; opening the turn, thinking, closing the
            # card (a goodbye follows) and a swipe on the cards (it already happened) do not.
            if event["kind"] not in ("turn", "thinking", "close", "wallet") and (line := agent.filler()):
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
