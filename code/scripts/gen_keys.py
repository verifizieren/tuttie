"""Generate Ed25519 keys for every authority, node, user agent (Tuttie) and the user, then publish
the authorities' public keys into data/authorities.json.

Existing key files are kept, so running this twice is safe.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aps.keys import generate_key_file, load_signing_key, public_key_b64  # noqa: E402

AUTHORITIES_PATH = ROOT / "data" / "authorities.json"
NODES_DIR = ROOT / "data" / "nodes"
AGENTS_DIR = ROOT / "data" / "agents"  # user agents like Tuttie: in the registry, but not node servers
SERVICES_DIR = ROOT / "data" / "services"  # public information services (weather, trains): services/server.py
USER_KEY_ID = "user"


def main() -> None:
    authorities = json.loads(AUTHORITIES_PATH.read_text())
    configs = sorted(NODES_DIR.glob("*.json")) + sorted(SERVICES_DIR.glob("*.json")) + sorted(AGENTS_DIR.glob("*.json"))
    node_ids = [json.loads(p.read_text())["node_id"] for p in configs]

    for key_id in [a["issuer"] for a in authorities] + node_ids + [USER_KEY_ID]:
        print("key:", generate_key_file(key_id).relative_to(ROOT))

    for authority in authorities:
        authority["public_key"] = public_key_b64(load_signing_key(authority["issuer"]))
    AUTHORITIES_PATH.write_text(json.dumps(authorities, indent=2) + "\n")
    print("updated:", AUTHORITIES_PATH.relative_to(ROOT))


if __name__ == "__main__":
    main()
