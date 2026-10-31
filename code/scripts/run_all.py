"""Start the registry, the marketplace, one node server per config and the assistant; Ctrl+C stops them all.

With voice configured in code/.env (LiveKit keys, ELEVENLABS_KEY), it also starts the
self-hosted LiveKit server (code/voice/livekit.yaml) and Tuttie's voice agent (voice/agent.py).

Every line a service prints is prefixed with its name (`[registry]`, `[gaestehaus-am-rhein]`,
`[tuttie]`, ...), coloured in a terminal, so twelve services in one window stay readable.
Before starting, it warns if there is no OpenAI key: everything starts without one, but Tuttie
cannot answer, and nothing else would say so.
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
LIVEKIT_SERVER = Path(os.environ.get("LIVEKIT_SERVER", Path.home() / ".local" / "livekit" / "livekit-server"))
COLOURS = [31, 32, 33, 34, 35, 36, 91, 92, 93, 94, 95, 96]  # ANSI foreground colours


def services(voice: dict | None = None) -> list[tuple[str, list[str]]]:
    """(name, command) for every service, in start order.

    `voice` holds the voice settings (from code/.env); with LiveKit keys and an installed
    LiveKit server it adds the LiveKit server, and with an ElevenLabs key the voice agent.
    """
    found = [("registry", [sys.executable, "-m", "registry.app"]),
             ("marketplace", [sys.executable, "-m", "marketplace.app"])]
    for path in sorted((ROOT / "data" / "nodes").glob("*.json")):
        name = path.stem.removeprefix("hotel-").removeprefix("basel-")
        found.append((name, [sys.executable, "-m", "node.server", "--config", str(path.relative_to(ROOT))]))
    found.append(("tuttie", [sys.executable, "-m", "assistant.app"]))
    voice = voice or {}
    if voice.get("LIVEKIT_API_KEY") and voice.get("LIVEKIT_API_SECRET") and LIVEKIT_SERVER.exists():
        command = [str(LIVEKIT_SERVER), *livekit_config(voice)]
        if voice.get("LIVEKIT_NODE_IP"):
            command += ["--node-ip", voice["LIVEKIT_NODE_IP"]]
        found.append(("livekit", command))
        if voice.get("ELEVENLABS_KEY"):
            found.append(("voice", [sys.executable, "-m", "voice.agent", "start"]))
    return found


TURN_TLS_PORT = 4044  # in the team server's open range; TCP, so it gets through where UDP does not


def livekit_config(voice: dict) -> list[str]:
    """LiveKit's config arguments: voice/livekit.yaml, plus the TURN relay when a certificate is set.

    Phones often can't reach the media ports directly (the team server lets no UDP through, and
    iPhones don't fall back to plain TCP); TURN over TLS on TURN_TLS_PORT relays their audio.
    It needs a certificate for LIVEKIT_TURN_DOMAIN (scripts/get_cert.sh).
    """
    config = (ROOT / "voice" / "livekit.yaml").read_text()
    if not all(voice.get(k) for k in ("LIVEKIT_TURN_DOMAIN", "LIVEKIT_TURN_CERT", "LIVEKIT_TURN_KEY")):
        return ["--config", "voice/livekit.yaml"]
    turn = (f"turn:\n  enabled: true\n  domain: {voice['LIVEKIT_TURN_DOMAIN']}\n  tls_port: {TURN_TLS_PORT}\n"
            f"  cert_file: {voice['LIVEKIT_TURN_CERT']}\n  key_file: {voice['LIVEKIT_TURN_KEY']}\n")
    return ["--config-body", config + turn]


def key_warning(env_file: Path = ROOT / ".env", environ=os.environ) -> str | None:
    """A warning if no usable OpenAI key is set (in the environment or in .env), else None.

    Only checks that a key is there and is not the example placeholder; the key itself is
    never printed.
    """
    key = environ.get("OPENAI_API_KEY") or (dotenv_values(env_file).get("OPENAI_API_KEY") if env_file.exists() else None)
    if not key or key.strip() in {"", "sk-..."}:
        where = "code/.env" if env_file.exists() else "code/.env (missing: cp .env.example .env)"
        return (f"warning: no OPENAI_API_KEY in {where}. Everything starts, but Tuttie cannot "
                "answer in the wallet. Tests and scripts/bargain_preview.py work without it.")
    return None


def prefix_output(name: str, stream, colour: int | None, width: int) -> None:
    """Copy a service's output line by line, each line prefixed with the service's name."""
    label = f"[{name}]".ljust(width + 2)
    if colour is not None:
        label = f"\033[{colour}m{label}\033[0m"
    for line in stream:
        sys.stdout.write(f"{label} {line}")
        sys.stdout.flush()


def main() -> None:
    """Start all services, show their output with names, stop all of them on Ctrl+C or when one exits."""
    if warning := key_warning():
        print(warning, file=sys.stderr)
    settings = {**(dotenv_values(ROOT / ".env") if (ROOT / ".env").exists() else {}), **os.environ}
    to_start = services(settings)
    width = max(len(name) for name, _ in to_start)
    colourful = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}  # lines appear when printed, not when a buffer fills
    if settings.get("LIVEKIT_API_KEY"):  # the LiveKit server takes its key pair from the environment
        env["LIVEKIT_KEYS"] = f"{settings['LIVEKIT_API_KEY']}: {settings['LIVEKIT_API_SECRET']}"
    processes: list[tuple[str, subprocess.Popen]] = []
    for index, (name, cmd) in enumerate(to_start):
        process = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1)
        colour = COLOURS[index % len(COLOURS)] if colourful else None
        threading.Thread(target=prefix_output, args=(name, process.stdout, colour, width), daemon=True).start()
        processes.append((name, process))
    try:
        while all(p.poll() is None for _, p in processes):
            time.sleep(0.5)
        exited = [name for name, p in processes if p.poll() is not None]
        print(f"{', '.join(exited)} exited, stopping the others", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        stop([p for _, p in processes])


def stop(processes: list[subprocess.Popen], grace_s: float = 3) -> None:
    """Stop every service: politely first, then for good after `grace_s`.

    Why the deadline: on Ctrl+C uvicorn shuts down gracefully and waits until all open
    connections close, and the wallet's live event stream (`GET /events` on the assistant)
    never closes by itself. Without a deadline the launcher hung until a second Ctrl+C.
    """
    for p in processes:
        if p.poll() is None:
            p.terminate()
    deadline = time.monotonic() + grace_s
    for p in processes:
        try:
            p.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            p.kill()  # still waiting for an open connection (e.g. the event stream)
            p.wait()


if __name__ == "__main__":
    main()
