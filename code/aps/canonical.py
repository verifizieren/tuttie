"""Canonical JSON encoding: the exact bytes every APS signature is computed over."""

import base64
import json


def canonical(obj) -> bytes:
    """Encode obj as canonical JSON (sorted keys, no whitespace, UTF-8)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def b64encode(data: bytes) -> str:
    """Bytes -> base64 text (keys and signatures travel as base64)."""
    return base64.b64encode(data).decode()


def b64decode(text: str) -> bytes:
    """Base64 text -> bytes; rejects anything that is not strict base64."""
    return base64.b64decode(text.encode(), validate=True)
