"""Tests for llm.py's provider choice and the Claude message conversion (no network)."""

import json

from llm import LLM, ClaudeLLM, to_claude, to_claude_tool


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
    assert system == "You are Tuttie."
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert [b["tool_use_id"] for b in messages[2]["content"]] == ["t1", "t2"]  # one user turn for both


def test_tool_schemas_are_converted():
    schema = {"type": "function", "function": {"name": "book", "description": "Book.",
                                               "parameters": {"type": "object", "properties": {}}}}
    assert to_claude_tool(schema) == {"name": "book", "description": "Book.",
                                      "input_schema": {"type": "object", "properties": {}}}
