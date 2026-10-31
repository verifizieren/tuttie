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
        for p in processes:
            p.terminate()
        for p in processes:
            p.wait()


if __name__ == "__main__":
    main()
