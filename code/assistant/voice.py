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
import os
import secrets
from datetime import timedelta

import httpx
import websockets
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from livekit import api
from pydantic import BaseModel

LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880")
API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")
TOKEN_TTL_S = 2 * 60 * 60

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
    """The voice agent's endpoints need the LiveKit secret (it runs on this server, next to us)."""
    if not configured() or request.headers.get("authorization") != f"Bearer {API_SECRET}":
        raise HTTPException(status_code=401, detail="voice agent only")


@router.post("/voice/token")
def voice_token(request: Request) -> dict:
    """A LiveKit token for a fresh room tied to this browser's conversation."""
    if not configured():
        raise HTTPException(status_code=503, detail="voice is not configured")
    room = f"tuttie-{secrets.token_urlsafe(12)}"
    conv = request.app.state.conversations.get(request.state.session_id)
    request.app.state.voice_rooms[room] = (request.state.session_id, conv.id)
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
    text: str


@router.post("/voice/say", status_code=202, dependencies=[Depends(agent_only)])
async def voice_say(said: Said, request: Request) -> dict:
    """What the user said, as a new turn in the room's conversation (like typing it)."""
    turn_id = room_conversation(request, said.room).start(said.text, source="voice")
    return {"accepted": True, "turn_id": turn_id}


async def live_only(bus):
    """The bus's SSE frames without the replayed history: the voice agent speaks only what is new."""
    skip = len(bus.history)
    async for frame in bus.stream():
        if skip and frame.startswith("event: message"):
            skip -= 1
            continue
        yield frame


@router.get("/voice/events", dependencies=[Depends(agent_only)])
def voice_events(room: str, request: Request) -> StreamingResponse:
    """New events of the room's conversation as Server-Sent Events, for the voice agent to speak from."""
    return StreamingResponse(live_only(room_conversation(request, room).bus), media_type="text/event-stream",
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
