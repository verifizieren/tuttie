"""Tests for llm.py's provider choice and the Claude message conversion (no network)."""

import json

from llm import CACHE, LLM, ClaudeLLM, to_claude, to_claude_tool


def test_claude_model_names_pick_the_anthropic_client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert isinstance(LLM("claude-haiku-5-5"), ClaudeLLM)
    assert not isinstance(LLM("gpt-5.1"), ClaudeLLM)


def test_chat_messages_become_messages_api_turns_with_grouped_tool_results():
    call = {"type": "tool_use", "id": "t1", "name": "recall_context", "input": {}}
    system, messages = to_claude([
        {"role": "system", "content": "You are Tuttie."},
        {"role": "user", "content": "Book me a hotel"},
        {"role": "assistant", "content": None, "provider_items": [call, {**call, "id": "t2"}]},
        {"role": "tool", "tool_call_id": "t1", "content": json.dumps({"ok": 1})},
        {"role": "tool", "tool_call_id": "t2", "content": json.dumps({"ok": 2})},
    ])
    assert [b["text"] for b in system] == ["You are Tuttie."]
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


def test_fixed_prompt_is_cached_and_round_notes_follow_it_uncached():
    """The prompt (with the tools before it) is a stable prefix for prompt caching; the notes that
    change every round (date, deal data) come after it as their own block, never cached."""
    system, chat = to_claude([
        {"role": "system", "content": "You are Tuttie."},
        {"role": "system", "content": "Today is Sunday."},
        {"role": "system", "content": "Deal data: {}"},
        {"role": "user", "content": "Book me a hotel"},
    ])
    assert system == [{"type": "text", "text": "You are Tuttie.", "cache_control": CACHE},
                      {"type": "text", "text": "Today is Sunday.\n\nDeal data: {}"}]
    assert chat == [{"role": "user", "content": "Book me a hotel"}]
