"""Start the registry, the marketplace, one node server per config and the assistant; Ctrl+C stops them all."""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    commands = [[sys.executable, "-m", "registry.app"], [sys.executable, "-m", "marketplace.app"]]
    commands += [
        [sys.executable, "-m", "node.server", "--config", str(path.relative_to(ROOT))]
        for path in sorted((ROOT / "data" / "nodes").glob("*.json"))
    ]
    commands.append([sys.executable, "-m", "assistant.app"])
    processes = [subprocess.Popen(cmd, cwd=ROOT) for cmd in commands]
    try:
        while all(p.poll() is None for p in processes):
            time.sleep(0.5)
        print("a service exited, stopping the others", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        stop(processes)


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
