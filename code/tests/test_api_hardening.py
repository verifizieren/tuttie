"""Tests that the assistant's HTTP API stays consistent under odd or concurrent requests (assistant/app.py)."""

import inspect
import os

os.environ.setdefault("OPENAI_API_KEY", "test")  # the app builds an LLM client; these tests never call it

from assistant import app as app_module  # noqa: E402
from assistant import voice  # noqa: E402


def test_routes_touching_conversations_run_on_the_event_loop():
    # A plain `def` runs in a worker thread: two first requests of one browser then each created
    # a conversation (seen live: 4 ids for 6 parallel /history calls), and decisions or resets
    # woke the event loop from a foreign thread.
    handlers = [app_module.conversation, app_module.chat, app_module.reset, app_module.pending_approvals,
                app_module.decide, app_module.history, app_module.events,
                voice.voice_token, voice.voice_say, voice.voice_events]
    assert [h.__name__ for h in handlers if not inspect.iscoroutinefunction(h)] == []
