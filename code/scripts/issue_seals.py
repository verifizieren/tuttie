"""Build data/registry.json: one signed registry record per node config.

Each seal in a node config names its issuer and tier. The issuer's key signs it,
except where the config says "signed_by": "self" (the scam hotel forging a
government seal with its own key). "issuer": "self" means a self-signed grey seal.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aps.keys import load_signing_key, public_key_b64  # noqa: E402
from aps.seals import issue_seal  # noqa: E402

NODES_DIR = ROOT / "data" / "nodes"
REGISTRY_PATH = ROOT / "data" / "registry.json"


def build_record(config: dict) -> dict:
    """The signed registry record for one node config."""
    node_id = config["node_id"]
    record = {
        "node_id": node_id,
        "name": config["name"],
        "public_key": public_key_b64(load_signing_key(node_id)),
        "endpoint": f"http://localhost:{config['port']}",
        "kind": config["kind"],
        "capabilities": config["capabilities"],
        "tags": config["tags"],
    }
    seals = []
    for claim in config["seals"]:
        issuer = node_id if claim["issuer"] == "self" else claim["issuer"]
        signer = node_id if claim.get("signed_by") == "self" else issuer
        seals.append(issue_seal(record, issuer, claim["tier"], load_signing_key(signer)))
    return {**record, "seals": seals}


def main() -> None:
    records = [build_record(json.loads(p.read_text())) for p in sorted(NODES_DIR.glob("*.json"))]
    REGISTRY_PATH.write_text(json.dumps(records, indent=2) + "\n")
    for record in records:
        print(f"{record['node_id']}: {[s['issuer'] + '/' + s['tier'] for s in record['seals']]}")
    print("written:", REGISTRY_PATH.relative_to(ROOT))


if __name__ == "__main__":
    main()
