"""Where the internal services listen: the SERVICE_HOST setting.

The registry, the marketplace, the business nodes and the services (weather, trains) listen
on SERVICE_HOST, default "127.0.0.1": only Tuttie on the same machine reaches them, since the
demo keys are in the public repo and a reachable node would take forged calls. Set
SERVICE_HOST=0.0.0.0 in code/.env only for a setup that spans machines.
Tuttie itself (assistant/app.py, port 4040) always stays public.
"""

import os

DEFAULT_HOST = "127.0.0.1"


def service_host() -> str:
    """The address internal services bind to: SERVICE_HOST, or 127.0.0.1 when unset or blank."""
    return os.environ.get("SERVICE_HOST", "").strip() or DEFAULT_HOST
