"""Build data/registry.json: one signed registry record per node config and user agent.

Each seal in a node config names its issuer and tier. The issuer's key signs it,
except where the config says "signed_by": "self" (the scam hotel forging a
government seal with its own key). "issuer": "self" means a self-signed grey seal.
The node's Swiss business number ("uid", optional) goes into the record and every seal,
like its name, kind and endpoint (see aps/seals.py seal_body). A node_id equal to an
authority's issuer id is refused.

User agents (data/agents/, e.g. Tuttie) also get a "delegation": the user's key signs
which scopes the agent may use for them (see aps/delegation.py).
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aps.delegation import sign_delegation  # noqa: E402
from aps.envelope import TIMESTAMP_FORMAT  # noqa: E402
from aps.keys import load_signing_key, public_key_b64  # noqa: E402
from aps.seals import issue_seal  # noqa: E402

NODES_DIR = ROOT / "data" / "nodes"
AGENTS_DIR = ROOT / "data" / "agents"
SERVICES_DIR = ROOT / "data" / "services"  # public information services (weather, trains): services/server.py
USER_KEY_ID = "user"
REGISTRY_PATH = ROOT / "data" / "registry.json"
AUTHORITIES_PATH = ROOT / "data" / "authorities.json"


def authority_ids() -> set[str]:
    """The issuer ids of the trusted authorities; no node may use one as its node_id."""
    return {a["issuer"] for a in json.loads(AUTHORITIES_PATH.read_text())}


def build_record(config: dict) -> dict:
    """The signed registry record for one node config."""
    node_id = config["node_id"]
    if node_id in authority_ids():
        raise ValueError(f"node_id {node_id!r} is an authority's issuer id; pick another node_id")
    record = {
        "node_id": node_id,
        "name": config["name"],
        "uid": config.get("uid"),
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
    record["seals"] = seals
    if "delegation" in config:
        valid_until = datetime.now(timezone.utc) + timedelta(days=config["delegation"]["valid_days"])
        record["delegation"] = sign_delegation(node_id, record["public_key"], config["delegation"]["scopes"],
                                               valid_until.strftime(TIMESTAMP_FORMAT),
                                               load_signing_key(USER_KEY_ID))
    return record


def main() -> None:
    configs = sorted(NODES_DIR.glob("*.json")) + sorted(SERVICES_DIR.glob("*.json")) + sorted(AGENTS_DIR.glob("*.json"))
    records = [build_record(json.loads(p.read_text())) for p in configs]
    REGISTRY_PATH.write_text(json.dumps(records, indent=2) + "\n")
    for record in records:
        print(f"{record['node_id']}: {[s['issuer'] + '/' + s['tier'] for s in record['seals']]}")
    print("written:", REGISTRY_PATH.relative_to(ROOT))


if __name__ == "__main__":
    main()
