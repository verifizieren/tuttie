"""Voice for the wallet: a LiveKit room per conversation, and the doors the voice agent uses.

Tuttie's voice is a thin layer (code/voice/agent.py): it turns the user's speech into a
message for the same conversation the wallet types into, and speaks what Tuttie does and
answers. All logic, tools and signatures stay in the assistant.

- POST /voice/token  (wallet): a LiveKit token for a new room tied to this browser's
  conversation. The voice agent is dispatched into every new room automatically.
- /rtc               (wallet): LiveKit's signaling WebSocket, proxied to the local LiveKit
  server, so it shares the wallet's https origin (the team server exposes no other port for it).
- POST /voice/diag     (wallet): what a phone saw when its voice connection failed or worked
  (kinds of addresses, ICE errors, relay servers), written to the log to debug real phones.
- POST /voice/say, GET /voice/events  (voice agent only, with the LiveKit secret as bearer
  token): send what the user said into the room's conversation, and follow its timeline.
"""

import asyncio
import hmac
import os
import secrets
import time
from collections import Counter, deque
from datetime import timedelta

import httpx
import websockets
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from livekit import api
from pydantic import BaseModel

from assistant.card_commands import card_choice
from assistant.inputs import UserText
from assistant.throttle import TURNS_PER_SESSION_PER_MIN

LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880")
API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")
TOKEN_TTL_S = 2 * 60 * 60
ROOMS_PER_CONVERSATION_PER_MIN = 10  # a flaky phone retries after 2, 4, 8 ... s; a loop gets 429
ROOMS_PER_CLIENT_PER_MIN = 300  # per client address a minute: a venue's Wi-Fi shares one, and every page load asks
MAX_VOICE_ROOMS = 1000  # the wallet asks for a room on every page load; unused ones are forgotten
VOICE_ROOM_GRACE_S = 120
# Spoken turns share the browser's turn count with typed ones (key ("session", id)), but may
# fill it further: fragments from the room count as turns too. A flood still stops at this.
VOICE_TURNS_PER_SESSION_PER_MIN = 2 * TURNS_PER_SESSION_PER_MIN
# Exact card commands ("next", "like") move a card without the LLM, so they do not count as
# turns; their own cap stops a flood (without cards on screen they fall through to the LLM).
CARD_COMMANDS_PER_SESSION_PER_MIN = 30  # a new room is kept this long before it is used (the wallet joins within seconds)

router = APIRouter()


def configured() -> bool:
    """Voice works only with LiveKit credentials; without them the wallet stays text-only."""
    return bool(API_KEY and API_SECRET)


def public_url(request: Request) -> str:
    """The LiveKit URL the wallet connects to: this site itself (wss behind nginx), which proxies /rtc."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    return f"{'wss' if proto == 'https' else 'ws'}://{host}"


def room_conversation(request: Request, room: str):
    """The conversation a voice room belongs to, or 404."""
    owner = request.app.state.voice_rooms.get(room)
    if owner is None:
        raise HTTPException(status_code=404, detail="unknown voice room")
    try:
        return request.app.state.conversations.active(*owner)
    except KeyError:
        raise HTTPException(status_code=409, detail="voice room belongs to an inactive conversation") from None


def passed_headers(headers) -> dict:
    """The headers LiveKit needs from the client: newer clients send the room token here."""
    return {"Authorization": headers["authorization"]} if "authorization" in headers else {}


def agent_only(request: Request) -> None:
    """The voice agent's endpoints need the LiveKit secret (it runs on this server, next to us),
    compared in constant time."""
    sent = request.headers.get("authorization", "").encode()
    if not configured() or not hmac.compare_digest(sent, f"Bearer {API_SECRET}".encode()):
        raise HTTPException(status_code=401, detail="voice agent only")


class VoiceRooms(dict):
    """LiveKit room -> (session id, conversation id), and which rooms are in use.

    Anyone can ask for rooms (no login), so a flood of new rooms must never unmap a live user's
    room (their speech would get 404 and the voice agent would go mute). Only rooms nobody uses
    are forgotten: first those whose conversation is gone, then those unused for
    VOICE_ROOM_GRACE_S, least recently used first. A room the voice agent follows (an open
    /voice/events stream) is never forgotten. Rooms are not reused (see RoomThrottle).
    """

    def __init__(self):
        super().__init__()
        self.used: dict[str, float] = {}  # room -> when it was created, spoken into or followed last
        self.live: Counter = Counter()  # room -> open /voice/events streams

    def add(self, room: str, owner: tuple[str, str], now: float) -> None:
        """Map a new room to its conversation."""
        self[room] = owner
        self.used[room] = now

    def touch(self, room: str, now: float) -> None:
        """Mark a room as used now."""
        if room in self:
            self.used[room] = now

    def forget(self, room: str) -> None:
        """Unmap a room (its token stops working for /voice/say and /voice/events)."""
        self.pop(room, None)
        self.used.pop(room, None)

    def unused(self, conversations, now: float) -> list[str]:
        """Rooms that may be forgotten, in that order: of a gone conversation, then idle ones."""
        gone, idle = [], []
        for room, (session_id, conversation_id) in self.items():
            if self.live[room]:
                continue
            conv = conversations.by_session.get(session_id)  # not find(): a check must not reorder the store
            if conv is None or conv.id != conversation_id:
                gone.append(room)
            elif now - self.used.get(room, 0) >= VOICE_ROOM_GRACE_S:
                idle.append(room)
        return gone + sorted(idle, key=lambda room: self.used.get(room, 0))

    def make_space(self, conversations, now: float) -> bool:
        """Forget unused rooms until one more fits under MAX_VOICE_ROOMS. Rooms in use may push
        the total up to twice that; beyond it there is no space (False: no new room for now)."""
        if len(self) >= MAX_VOICE_ROOMS:
            for room in self.unused(conversations, now):
                if len(self) < MAX_VOICE_ROOMS:
                    break
                self.forget(room)
        return len(self) < 2 * MAX_VOICE_ROOMS


class RoomThrottle:
    """Counts new voice rooms per conversation and per client address over the last minute.

    Every room starts a voice agent job (a process with speech recognition), so a loop of
    token requests must not open rooms without end. A room is never handed out twice: the
    voice agent leaves a room when the wallet disconnects, so a reused room could stay silent.
    """

    def __init__(self):
        self.recent: dict[object, deque] = {}  # owner (session, conversation) or client address -> times

    def _count(self, key, now: float) -> int:
        """New rooms for `key` in the last minute; a key with none is forgotten."""
        times = self.recent.get(key)
        if times is None:
            return 0
        while times and now - times[0] > 60:
            times.popleft()
        if not times:
            del self.recent[key]
        return len(times)

    def allow(self, owner: tuple[str, str], client: str, now: float) -> bool:
        """Count a new room and say yes, or say no if the conversation or the client has had enough."""
        if (self._count(owner, now) >= ROOMS_PER_CONVERSATION_PER_MIN
                or self._count(client, now) >= ROOMS_PER_CLIENT_PER_MIN):
            return False
        for key in (owner, client):
            self.recent.setdefault(key, deque()).append(now)
        if len(self.recent) > 2 * MAX_VOICE_ROOMS:  # forget keys with nothing in the last minute
            for key in list(self.recent):
                self._count(key, now)
        return True


@router.post("/voice/token")
async def voice_token(request: Request) -> dict:
    """A LiveKit token for a fresh room tied to this browser's conversation.

    429 if the conversation asked for more than ROOMS_PER_CONVERSATION_PER_MIN rooms in the
    last minute, or its client address for more than ROOMS_PER_CLIENT_PER_MIN (the wallet
    tries again later on its own), or if every room is in use (VoiceRooms.make_space).
    """
    if not configured():
        raise HTTPException(status_code=503, detail="voice is not configured")
    store, session_id = request.app.state.conversations, request.state.session_id
    current = store.find(session_id)  # throttle first: a refused request must not create a conversation
    owner = (session_id, current.id if current else store.first_id(session_id))
    client = request.client.host if request.client else "unknown"  # uvicorn takes it from nginx's header
    if not request.app.state.voice_throttle.allow(owner, client, time.monotonic()):
        raise HTTPException(status_code=429, detail="Too many voice connections. Please try again in a minute.",
                            headers={"Retry-After": "60"})
    rooms, now = request.app.state.voice_rooms, time.monotonic()
    if not rooms.make_space(store, now):
        raise HTTPException(status_code=429, detail="Voice is busy. Please try again in a minute.",
                            headers={"Retry-After": "60"})
    conv = store.get(session_id)
    room = f"tuttie-{secrets.token_urlsafe(12)}"
    rooms.add(room, (session_id, conv.id), now)
    token = (api.AccessToken(API_KEY, API_SECRET)
             .with_identity(f"user-{secrets.token_hex(4)}")
             .with_name("You")
             .with_ttl(timedelta(seconds=TOKEN_TTL_S))
             .with_grants(api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True,
                                             can_update_own_metadata=True))
             .to_jwt())
    return {"url": public_url(request), "token": token, "room": room}


class Said(BaseModel):
    room: str
    text: UserText


@router.post("/voice/say", status_code=202, dependencies=[Depends(agent_only)])
async def voice_say(said: Said, request: Request) -> dict:
    """What the user said, as a new turn in the room's conversation (like typing it).

    Spoken turns count towards the browser's turn count like typed ones, up to
    VOICE_TURNS_PER_SESSION_PER_MIN (429); exact card commands count only towards
    CARD_COMMANDS_PER_SESSION_PER_MIN.
    """
    conv = room_conversation(request, said.room)
    session_id = request.app.state.voice_rooms[said.room][0]
    request.app.state.voice_rooms.touch(said.room, time.monotonic())
    if card_choice(said.text):
        limits = {("card", session_id): CARD_COMMANDS_PER_SESSION_PER_MIN}
    else:
        limits = {("session", session_id): VOICE_TURNS_PER_SESSION_PER_MIN}
    wait = request.app.state.turn_throttle.wait(limits, time.monotonic())
    if wait:
        raise HTTPException(status_code=429, detail="too many turns", headers={"Retry-After": str(wait)})
    turn_id = conv.start(said.text, source="voice")
    return {"accepted": True, "turn_id": turn_id}


async def live_only(bus, rooms: VoiceRooms, room: str):
    """The bus's SSE frames without the replayed history: the voice agent speaks only what is new.

    While the stream is open the room counts as live (never forgotten by VoiceRooms)."""
    skip = len(bus.history)
    rooms.live[room] += 1
    try:
        async for frame in bus.stream():
            if skip and frame.startswith("event: message"):
                skip -= 1
                continue
            yield frame
    finally:
        rooms.live[room] -= 1
        if rooms.live[room] <= 0:
            del rooms.live[room]
        rooms.touch(room, time.monotonic())  # the grace period starts when the agent leaves


@router.get("/voice/events", dependencies=[Depends(agent_only)])
async def voice_events(room: str, request: Request) -> StreamingResponse:
    """New events of the room's conversation as Server-Sent Events, for the voice agent to speak from."""
    rooms = request.app.state.voice_rooms
    rooms.touch(room, time.monotonic())
    return StreamingResponse(live_only(room_conversation(request, room).bus, rooms, room), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


DIAG_MAX_BYTES = 2000


@router.post("/voice/diag", status_code=204)
async def voice_diag(request: Request) -> Response:
    """Log a wallet's voice connection report (lib/iceReport.js), cut to DIAG_MAX_BYTES."""
    body = (await request.body())[:DIAG_MAX_BYTES].decode(errors="replace")
    print(f"voice diag: {body}", flush=True)
    return Response(status_code=204)


@router.get("/rtc/validate")
async def rtc_validate(request: Request) -> Response:
    """LiveKit's connection check, passed to the local LiveKit server."""
    url = LIVEKIT_URL.replace("ws", "http", 1) + "/rtc/validate"
    async with httpx.AsyncClient(timeout=10) as http:
        upstream = await http.get(url, params=request.query_params, headers=passed_headers(request.headers))
    return Response(upstream.content, status_code=upstream.status_code, media_type=upstream.headers.get("content-type"))


@router.websocket("/rtc")
@router.websocket("/rtc/{rest:path}")
async def rtc_proxy(ws: WebSocket, rest: str = "") -> None:
    """LiveKit signaling: pass every frame between the wallet and the local LiveKit server."""
    await ws.accept()
    target = f"{LIVEKIT_URL}/rtc{'/' + rest if rest else ''}?{ws.url.query}"
    try:
        async with websockets.connect(target, max_size=None, additional_headers=passed_headers(ws.headers)) as upstream:
            async def to_livekit():
                while True:
                    message = await ws.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    await upstream.send(message["bytes"] if message.get("bytes") is not None else message["text"])

            async def to_wallet():
                async for frame in upstream:
                    await (ws.send_bytes(frame) if isinstance(frame, bytes) else ws.send_text(frame))

            done, pending = await asyncio.wait({asyncio.create_task(to_livekit()), asyncio.create_task(to_wallet())},
                                               return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
    except (OSError, websockets.WebSocketException, WebSocketDisconnect):
        pass
    finally:
        try:
            await ws.close()
        except (RuntimeError, OSError, WebSocketDisconnect):
            pass  # the wallet left first
