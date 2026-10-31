"""User's assistant service (port 4040): chat API, SSE timeline, phone approvals and the static apps.

A chat runs in the background (it may wait minutes for the phone); its answer arrives as an
"answer" event on the timeline stream.

Run from code/: python -m assistant.app
"""

import asyncio
import io
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import qrcode
import qrcode.image.svg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from assistant.agent import Assistant  # noqa: E402
from assistant.approvals import ApprovalBook  # noqa: E402
from assistant.events import EventBus  # noqa: E402
from assistant.tools import Toolbox  # noqa: E402
from llm import LLM  # noqa: E402

APPS_DIR = Path(__file__).resolve().parent.parent / "apps"  # wallet/, shared/, old/ (first prototype), ...
REGISTRY_URL = os.environ.get("REGISTRY_URL", f"http://localhost:{os.environ.get('REGISTRY_PORT', '4000')}")

bus = EventBus()
approvals = ApprovalBook()
chats: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=20) as http:
        app.state.assistant = Assistant(LLM(), Toolbox(http, REGISTRY_URL, bus, approvals), bus)
        yield


app = FastAPI(title="APS assistant", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


class DecisionRequest(BaseModel):
    decision: str  # "approved" or "declined"


async def run_chat(message: str) -> None:
    try:
        await app.state.assistant.chat(message)
    except asyncio.CancelledError:
        raise
    except Exception as error:  # surface any failure on screen instead of hanging the demo
        bus.emit("answer", "broken", f"Sorry, something went wrong: {type(error).__name__}")


@app.post("/chat", status_code=202)
async def chat(req: ChatRequest) -> dict:
    task = asyncio.create_task(run_chat(req.message))
    chats.add(task)
    task.add_done_callback(chats.discard)
    return {"accepted": True}


@app.post("/reset")
def reset() -> dict:
    for task in list(chats):
        task.cancel()
    approvals.clear()
    app.state.assistant.reset()
    bus.reset()
    return {"ok": True}


@app.get("/approvals/pending")
def pending_approvals() -> list[dict]:
    return list(approvals.pending.values())


@app.post("/approvals/{approval_id}")
def decide(approval_id: str, req: DecisionRequest) -> dict:
    if req.decision not in ("approved", "declined"):
        raise HTTPException(status_code=422, detail="decision must be approved or declined")
    decision = approvals.decide(approval_id, req.decision)
    if decision is None:
        raise HTTPException(status_code=404, detail="no such pending approval")
    return decision


@app.get("/phone-qr.svg")
def phone_qr(request: Request) -> Response:
    """QR code of the phone page URL, as seen by the browser (works behind the reverse proxy)."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    url = os.environ.get("PHONE_URL", f"{scheme}://{host}/old/wallet/")
    buffer = io.BytesIO()
    qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=2).save(buffer)
    return Response(buffer.getvalue(), media_type="image/svg+xml", headers={"X-Phone-Url": url})


@app.get("/events")
def events() -> StreamingResponse:
    return StreamingResponse(bus.stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/")
def home() -> RedirectResponse:
    return RedirectResponse("/wallet/")


@app.get("/phone.html")
def old_phone_link() -> RedirectResponse:
    """Links and QR codes from the first prototype."""
    return RedirectResponse("/old/wallet/")


app.mount("/", StaticFiles(directory=APPS_DIR, html=True), name="apps")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("ASSISTANT_PORT", "4040")))
