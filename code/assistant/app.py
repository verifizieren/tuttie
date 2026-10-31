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
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from apidocs import api_docs  # noqa: E402
from assistant.conversations import Conversation, Conversations  # noqa: E402
from assistant.inputs import UserText  # noqa: E402
from assistant.voice import router as voice_router  # noqa: E402

APPS_DIR = Path(__file__).resolve().parent.parent / "apps"  # static apps and shared files (shared/)
# The wallet is a React app; serve its production build (`npm run build` in apps/wallet).
WALLET_DIST = APPS_DIR / "wallet" / "dist"
OWNER_DIST = APPS_DIR / "owner" / "dist"  # the owner view, also a React app (apps/owner)
TUTTIE_ID = os.environ.get("TUTTIE_ID", "ch.tuttie.alex-muster")  # this user's agent, data/agents/
REGISTRY_URL = os.environ.get("REGISTRY_URL", f"http://localhost:{os.environ.get('REGISTRY_PORT', '4000')}")

SESSION_COOKIE = "tuttie_session"
SESSION_DAYS = 30


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Keep the conversations and one shared HTTP client for the service's lifetime."""
    async with httpx.AsyncClient(timeout=20) as http:
        app.state.conversations = Conversations(http, REGISTRY_URL)
        app.state.voice_rooms = {}  # LiveKit room -> (session id, conversation id)
        yield


app = FastAPI(title="APS assistant", lifespan=lifespan, **api_docs())


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
    """422 without echoing the input: it may be huge or not encodable (a lone surrogate gave a 500)."""
    return JSONResponse(status_code=422, content={"detail": [
        {"type": e.get("type"), "loc": list(e.get("loc", ())), "msg": e.get("msg")} for e in error.errors()]})


@app.middleware("http")
async def session_cookie(request: Request, call_next):
    """Give every browser a session id on its first request (the wallet page itself)."""
    session_id = request.cookies.get(SESSION_COOKIE)
    fresh = not session_id
    request.state.session_id = session_id or secrets.token_urlsafe(16)
    response = await call_next(request)
    if fresh:
        response.set_cookie(SESSION_COOKIE, request.state.session_id, max_age=SESSION_DAYS * 86400,
                            httponly=True, samesite="lax", secure=over_https(request))
    return response


def over_https(request: Request) -> bool:
    """Whether the browser reached us over https: directly, or through nginx (X-Forwarded-Proto).

    Only then is the session cookie marked Secure; plain-http local development keeps working.
    """
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


async def conversation(request: Request) -> Conversation:
    """The calling browser's conversation.

    Async on purpose, like every route that touches conversations: FastAPI runs plain `def`
    dependencies and routes in worker threads, where two first requests of one browser could
    each create a conversation (one silently lost), and approvals or cancels would wake the
    event loop from a foreign thread.
    """
    return request.app.state.conversations.get(request.state.session_id)


async def existing_conversation(request: Request) -> Conversation | None:
    """The calling browser's conversation, or None: endpoints that only read never create one."""
    return request.app.state.conversations.find(request.state.session_id)


# Steps the wallet may fix for a message: after swiping the cards, Tuttie books the liked deal.
FIRST_TOOLS = {"book", "negotiate"}


class ChatRequest(BaseModel):
    message: UserText
    first_tool: str | None = None  # one of FIRST_TOOLS
    conversation_id: str | None = None
    said: UserText | None = None  # what the user sees as their message, if not the message itself


class DecisionRequest(BaseModel):
    decision: str  # "approved" or "declined"
    allow_mandate: bool = False  # also sign the mandate the approval offered (e.g. for the city tax)


@app.post("/chat", status_code=202)
async def chat(req: ChatRequest, conv: Conversation = Depends(conversation)) -> dict:
    """Start answering a message as a new turn; its events and answer carry the returned turn id."""
    if req.conversation_id is not None and req.conversation_id != conv.id:
        raise HTTPException(status_code=409, detail="The active chat changed. Reload the wallet before continuing.")
    if req.first_tool is not None and req.first_tool not in FIRST_TOOLS:
        raise HTTPException(status_code=422, detail=f"first_tool must be one of {sorted(FIRST_TOOLS)}")
    turn_id = conv.start(req.message, req.first_tool, said=req.said)
    return {"accepted": True, "turn_id": turn_id}


@app.post("/reset")
async def reset(conv: Conversation | None = Depends(existing_conversation)) -> dict:
    """Start this conversation over: stop its chats, decline its approvals, clear its timeline."""
    if conv is not None:
        conv.reset()
    return {"ok": True}


def switch_conversation(request: Request, conversation_id: str | None = None) -> dict:
    """Select only a conversation owned by the caller; expired history stays read-only."""
    try:
        conv = request.app.state.conversations.switch(request.state.session_id, conversation_id)
    except KeyError:
        raise HTTPException(status_code=410, detail="This conversation has expired. Start a new request to check current offers.") from None
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    return {"id": conv.id, "events": list(conv.bus.history)}


@app.post("/conversations")
async def new_conversation(request: Request) -> dict:
    """Keep the previous assistant and its verified facts available for resuming."""
    return switch_conversation(request)


@app.post("/conversations/{conversation_id}/resume")
async def resume_conversation(conversation_id: str, request: Request) -> dict:
    """Restore the assistant, toolbox, approvals and timeline together."""
    return switch_conversation(request, conversation_id)


@app.get("/identity")
async def identity(request: Request) -> dict:
    """Tuttie's own verified identity: its seals and the user's signed delegation."""
    return await request.app.state.conversations.identity_toolbox().identity(TUTTIE_ID)


@app.get("/approvals/pending")
async def pending_approvals(conv: Conversation | None = Depends(existing_conversation)) -> list[dict]:
    """Approvals waiting for this user's decision."""
    return list(conv.approvals.pending.values()) if conv else []


@app.post("/approvals/{approval_id}")
async def decide(approval_id: str, req: DecisionRequest,
                 conv: Conversation | None = Depends(existing_conversation)) -> dict:
    """Record the user's decision; it is signed with the user's key and wakes the waiting chat."""
    if req.decision not in ("approved", "declined"):
        raise HTTPException(status_code=422, detail="decision must be approved or declined")
    decision = conv.approvals.decide(approval_id, req.decision, req.allow_mandate) if conv else None
    if decision is None:
        raise HTTPException(status_code=404, detail="no such pending approval")
    return decision


@app.get("/history")
async def history(request: Request, response: Response) -> list[dict]:
    """This conversation's timeline so far, so the wallet can decide on opening whether to start fresh.

    A browser without a conversation gets an empty timeline and the id its first one will have.
    """
    store = request.app.state.conversations
    conv = store.find(request.state.session_id)
    response.headers["X-Conversation-ID"] = conv.id if conv else store.first_id(request.state.session_id)
    return conv.bus.history if conv else []


@app.get("/events")
async def events(request: Request, conversation_id: str | None = None) -> StreamingResponse:
    """This conversation's timeline as Server-Sent Events.

    The wallet follows the id GET /history named before its first message, which starts the
    browser's first conversation; without a conversation any other id is refused.
    """
    store, session_id = request.app.state.conversations, request.state.session_id
    conv = store.find(session_id)
    if conv is None:
        if conversation_id != store.first_id(session_id):
            raise HTTPException(status_code=409, detail="The active chat changed. Reload the wallet before continuing.")
        conv = store.get(session_id)
    if conversation_id is not None and conversation_id != conv.id:
        raise HTTPException(status_code=409, detail="The active chat changed. Reload the wallet before continuing.")
    return StreamingResponse(conv.bus.stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.include_router(voice_router)


@app.get("/")
def home() -> RedirectResponse:
    """The wallet is the app."""
    return RedirectResponse("/wallet/")


if not WALLET_DIST.exists():
    print(f"warning: {WALLET_DIST} is missing; build the wallet with `npm run build` in apps/wallet")
app.mount("/wallet", StaticFiles(directory=WALLET_DIST, html=True, check_dir=False), name="wallet")
app.mount("/owner", StaticFiles(directory=OWNER_DIST, html=True, check_dir=False), name="owner")
app.mount("/", StaticFiles(directory=APPS_DIR, html=True), name="apps")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("ASSISTANT_PORT", "4040")))
