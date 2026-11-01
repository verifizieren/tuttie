"""Tests for llm.py's provider choice and the Claude message conversion (no network)."""

import json

from llm import CACHE, LLM, ClaudeLLM, to_claude, to_claude_tool, with_notes


def test_claude_model_names_pick_the_anthropic_client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert isinstance(LLM("claude-haiku-5-5"), ClaudeLLM)
    assert not isinstance(LLM("gpt-5.1"), ClaudeLLM)


def test_chat_messages_become_messages_api_turns_with_grouped_tool_results():
    call = {"type": "tool_use", "id": "t1", "name": "recall_context", "input": {}}
    system, messages, notes = to_claude([
        {"role": "system", "content": "You are Tuttie."},
        {"role": "user", "content": "Book me a hotel"},
        {"role": "assistant", "content": None, "provider_items": [call, {**call, "id": "t2"}]},
        {"role": "tool", "tool_call_id": "t1", "content": json.dumps({"ok": 1})},
        {"role": "tool", "tool_call_id": "t2", "content": json.dumps({"ok": 2})},
    ])
    assert [b["text"] for b in system] == ["You are Tuttie."] and notes == ""
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert [b["tool_use_id"] for b in messages[2]["content"]] == ["t1", "t2"]  # one user turn for both


def test_tool_schemas_are_converted():
    schema = {"type": "function", "function": {"name": "book", "description": "Book.",
                                               "parameters": {"type": "object", "properties": {}}}}
    assert to_claude_tool(schema) == {"name": "book", "description": "Book.",
                                      "input_schema": {"type": "object", "properties": {}}}


def test_both_providers_time_out_instead_of_hanging(monkeypatch):
    import llm
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    for client in (llm.LLM("gpt-4.1").client, llm.LLM("claude-haiku-5-5").client):
        assert client.timeout == llm.TIMEOUT_S <= 60 and client.max_retries == llm.MAX_RETRIES


def test_fixed_prompt_and_history_are_cached_and_round_notes_come_after_them():
    """The prompt (with the tools) and the chat are a stable prefix for prompt caching; the notes
    that change every round (date, deal data) go after it, never into the cached part."""
    system, chat, notes = to_claude([
        {"role": "system", "content": "You are Tuttie."},
        {"role": "system", "content": "Today is Sunday."},
        {"role": "system", "content": "Deal data: {}"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "Book me a hotel"},
    ])
    assert system == [{"type": "text", "text": "You are Tuttie.", "cache_control": CACHE}]
    assert notes == "Today is Sunday.\n\nDeal data: {}"
    assert chat[-1]["content"] == [{"type": "text", "text": "Book me a hotel", "cache_control": CACHE}]
    assert chat[0]["content"] == "hi"  # only the last message carries a breakpoint
    sent_system, sent_chat = with_notes(system, chat, notes, inline=False)
    assert sent_system == system and sent_chat[-1] == {"role": "system", "content": notes}
    inline_system, inline_chat = with_notes(system, chat, notes, inline=True)
    assert inline_chat == chat and inline_system[-1] == {"type": "text", "text": notes}


def test_cache_breakpoint_goes_on_the_last_tool_result():
    call = {"type": "tool_use", "id": "t1", "name": "recall_context", "input": {}}
    _, chat, _ = to_claude([
        {"role": "system", "content": "You are Tuttie."},
        {"role": "user", "content": "Book me a hotel"},
        {"role": "assistant", "content": None, "provider_items": [call, {**call, "id": "t2"}]},
        {"role": "tool", "tool_call_id": "t1", "content": "{}"},
        {"role": "tool", "tool_call_id": "t2", "content": "{}"},
    ])
    assert "cache_control" not in chat[-1]["content"][0]
    assert chat[-1]["content"][1]["cache_control"] == CACHE


def test_a_model_without_chat_system_messages_falls_back_to_inline_notes(monkeypatch):
    """A 400 about the system role switches to notes in the system blocks, once, and remembers."""
    import asyncio
    import httpx
    from anthropic import BadRequestError
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    llm = ClaudeLLM("claude-haiku-5-5")
    sent = []

    class Block:
        def model_dump(self, exclude_none=True):
            return {"type": "text", "text": "Hi!"}

    class Response:
        content = [Block()]

    async def create(**request):
        sent.append(request)
        if any(m["role"] == "system" for m in request["messages"]):
            response = httpx.Response(400, request=httpx.Request("POST", "https://x"))
            raise BadRequestError("role 'system' is not supported on this model", response=response, body=None)
        return Response()

    monkeypatch.setattr(llm.client.messages, "create", create)
    messages = [{"role": "system", "content": "P"}, {"role": "system", "content": "N"},
                {"role": "user", "content": "hi"}]
    assert asyncio.run(llm.complete(messages, []))["content"] == "Hi!"
    assert asyncio.run(llm.complete(messages, []))["content"] == "Hi!"
    assert len(sent) == 3 and llm.inline_notes  # the second call went inline straight away
    assert sent[-1]["system"][-1] == {"type": "text", "text": "N"}
