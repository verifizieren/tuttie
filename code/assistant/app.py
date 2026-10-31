"""User's assistant service (port 4040): chat API, SSE timeline and the static UI.

Run from code/: python -m assistant.app
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from assistant.agent import Assistant  # noqa: E402
from assistant.events import EventBus  # noqa: E402
from assistant.tools import Toolbox  # noqa: E402
from llm import LLM  # noqa: E402

UI_DIR = Path(__file__).resolve().parent.parent / "ui"
REGISTRY_URL = os.environ.get("REGISTRY_URL", f"http://localhost:{os.environ.get('REGISTRY_PORT', '4000')}")

bus = EventBus()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=20) as http:
        app.state.assistant = Assistant(LLM(), Toolbox(http, REGISTRY_URL, bus), bus)
        yield


app = FastAPI(title="APS assistant", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
async def chat(req: ChatRequest) -> dict:
    return {"answer": await app.state.assistant.chat(req.message)}


@app.post("/reset")
def reset() -> dict:
    app.state.assistant.reset()
    bus.reset()
    return {"ok": True}


@app.get("/events")
def events() -> StreamingResponse:
    return StreamingResponse(bus.stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("ASSISTANT_PORT", "4040")))
