"""User's assistant service (port 4040): chat API, SSE timeline, phone approvals and the static apps.

Every browser gets its own conversation (assistant/conversations.py), recognised by a session
cookie: its own timeline, approvals and chat, so people using the app at the same time never see
each other's runs. A chat runs in the background (it may wait minutes for the approval); its
answer arrives as an "answer" event on that conversation's timeline stream.

Run from code/: python -m assistant.app
"""

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from assistant.conversations import Conversation, Conversations  # noqa: E402

APPS_DIR = Path(__file__).resolve().parent.parent / "apps"  # static apps and shared files (shared/)
# The wallet is a React app; serve its production build (`npm run build` in apps/wallet).
WALLET_DIST = APPS_DIR / "wallet" / "dist"
TUTTIE_ID = os.environ.get("TUTTIE_ID", "ch.tuttie.alex-muster")  # this user's agent, data/agents/
REGISTRY_URL = os.environ.get("REGISTRY_URL", f"http://localhost:{os.environ.get('REGISTRY_PORT', '4000')}")

SESSION_COOKIE = "tuttie_session"
SESSION_DAYS = 30


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Keep the conversations and one shared HTTP client for the service's lifetime."""
    async with httpx.AsyncClient(timeout=20) as http:
        app.state.conversations = Conversations(http, REGISTRY_URL)
        yield


app = FastAPI(title="APS assistant", lifespan=lifespan)


@app.middleware("http")
async def session_cookie(request: Request, call_next):
    """Give every browser a session id on its first request (the wallet page itself)."""
    session_id = request.cookies.get(SESSION_COOKIE)
    fresh = not session_id
    request.state.session_id = session_id or secrets.token_urlsafe(16)
    response = await call_next(request)
    if fresh:
        response.set_cookie(SESSION_COOKIE, request.state.session_id, max_age=SESSION_DAYS * 86400,
                            httponly=True, samesite="lax")
    return response


def conversation(request: Request) -> Conversation:
    """The calling browser's conversation."""
    return request.app.state.conversations.get(request.state.session_id)


class ChatRequest(BaseModel):
    message: str


class DecisionRequest(BaseModel):
    decision: str  # "approved" or "declined"
    allow_mandate: bool = False  # also sign the mandate the approval offered (e.g. for the city tax)


@app.post("/chat", status_code=202)
async def chat(req: ChatRequest, conv: Conversation = Depends(conversation)) -> dict:
    """Start answering a message; the answer arrives as an "answer" event."""
    conv.start(req.message)
    return {"accepted": True}


@app.post("/reset")
def reset(conv: Conversation = Depends(conversation)) -> dict:
    """Start this conversation over: stop its chats, decline its approvals, clear its timeline."""
    conv.reset()
    return {"ok": True}


@app.get("/identity")
async def identity(conv: Conversation = Depends(conversation)) -> dict:
    """Tuttie's own verified identity: its seals and the user's signed delegation."""
    return await conv.assistant.toolbox.identity(TUTTIE_ID)


@app.get("/approvals/pending")
def pending_approvals(conv: Conversation = Depends(conversation)) -> list[dict]:
    """Approvals waiting for this user's decision."""
    return list(conv.approvals.pending.values())


@app.post("/approvals/{approval_id}")
def decide(approval_id: str, req: DecisionRequest, conv: Conversation = Depends(conversation)) -> dict:
    """Record the user's decision; it is signed with the user's key and wakes the waiting chat."""
    if req.decision not in ("approved", "declined"):
        raise HTTPException(status_code=422, detail="decision must be approved or declined")
    decision = conv.approvals.decide(approval_id, req.decision, req.allow_mandate)
    if decision is None:
        raise HTTPException(status_code=404, detail="no such pending approval")
    return decision


@app.get("/history")
def history(conv: Conversation = Depends(conversation)) -> list[dict]:
    """This conversation's timeline so far, so the wallet can decide on opening whether to start fresh."""
    return conv.bus.history


@app.get("/events")
def events(conv: Conversation = Depends(conversation)) -> StreamingResponse:
    """This conversation's timeline as Server-Sent Events."""
    return StreamingResponse(conv.bus.stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/")
def home() -> RedirectResponse:
    """The wallet is the app."""
    return RedirectResponse("/wallet/")


if not WALLET_DIST.exists():
    print(f"warning: {WALLET_DIST} is missing; build the wallet with `npm run build` in apps/wallet")
app.mount("/wallet", StaticFiles(directory=WALLET_DIST, html=True, check_dir=False), name="wallet")
app.mount("/", StaticFiles(directory=APPS_DIR, html=True), name="apps")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("ASSISTANT_PORT", "4040")))
