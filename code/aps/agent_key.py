"""The deployment's agent key: who may make a business's agent think.

A business's agent runs an LLM on the business's account for every question, session
message and wake-up, so on a public server those doors must not be open to anyone. The
services of one deployment (marketplace, Tuttie, the businesses) share a random key in
AGENT_WEB_KEY and send it in the X-Agent-Web-Key header; scripts/run_all.py makes one per
run unless code/.env sets it. Without the variable (tests, local experiments) the doors stay
open. Signed answers and signed actions do not depend on it: it only guards the LLM.
"""

import hmac
import os

ENV = "AGENT_WEB_KEY"
HEADER = "X-Agent-Web-Key"


def current() -> str:
    """The key, read at call time (nodes load code/.env after import)."""
    return os.environ.get(ENV, "")


def headers() -> dict:
    """The header to send to a business's agent, or none if no key is set."""
    key = current()
    return {HEADER: key} if key else {}


def allowed(value: str | None) -> bool:
    """Whether a request carrying `value` in HEADER may reach the agent."""
    key = current()
    return not key or (value is not None and hmac.compare_digest(value.encode(), key.encode()))
