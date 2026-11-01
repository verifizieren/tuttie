"""Where the internal services listen: the SERVICE_HOST setting.

The registry, the marketplace, the business nodes and the services (weather, trains) listen
on SERVICE_HOST, default "0.0.0.0" (every interface, as before). On a server whose ports are
public, set SERVICE_HOST=127.0.0.1 in code/.env so only Tuttie on the same machine reaches
them: the demo keys are in the public repo, so a reachable node would take forged calls.
Tuttie itself (assistant/app.py, port 4040) always stays public.
"""

import os

DEFAULT_HOST = "0.0.0.0"


def service_host() -> str:
    """The address internal services bind to: SERVICE_HOST, or 0.0.0.0 when unset or blank."""
    return os.environ.get("SERVICE_HOST", "").strip() or DEFAULT_HOST
