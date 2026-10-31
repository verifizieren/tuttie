"""APS seals: issuing them and turning a registry record into a trust verdict.

A seal counts only if its issuer is a trusted authority (data/authorities.json)
with the claimed tier and the signature verifies. A seal whose issuer is the node
itself is a self-signed grey seal. A node without any seal is unsigned and also grey
(untrusted, but it claims nothing false). Any claimed seal that fails makes the node broken.
"""

from nacl.signing import SigningKey

from aps.envelope import sign_bytes, verify_bytes

TIER_RANK = {"broken": 0, "grey": 1, "blue": 2, "gold": 3}
# Capabilities that grey nodes never get, whatever they claim.
PAYMENT_CAPABILITIES = {"can_take_payment"}


def seal_body(record: dict, issuer: str, tier: str) -> dict:
    """The fields a seal signs: who the node is, its key and what it may do, plus issuer and tier."""
    return {
        "node_id": record["node_id"],
        "public_key": record["public_key"],
        "capabilities": record["capabilities"],
        "issuer": issuer,
        "tier": tier,
    }


def issue_seal(record: dict, issuer: str, tier: str, signing_key: SigningKey) -> dict:
    """Seal `record` as `issuer` at `tier`, signed with the issuer's key."""
    return {"issuer": issuer, "tier": tier, "signature": sign_bytes(signing_key, seal_body(record, issuer, tier))}


def check_seal(record: dict, seal: dict, authorities: dict) -> bool:
    """Verify one seal of a record. authorities maps issuer id -> authority entry."""
    issuer, tier = seal.get("issuer"), seal.get("tier")
    if issuer == record["node_id"]:
        if tier != "grey":
            return False
        public_key = record["public_key"]
    elif issuer in authorities and authorities[issuer]["tier"] == tier:
        public_key = authorities[issuer]["public_key"]
    else:
        return False
    return verify_bytes(public_key, seal_body(record, issuer, tier), seal.get("signature", ""))


def evaluate_record(record: dict, authorities: dict) -> dict:
    """Return the trust verdict for a registry record.

    {"tier": "gold|blue|grey|broken", "seals": [{issuer, tier, valid}], "capabilities": [granted]}
    """
    seals = [
        {"issuer": s.get("issuer"), "tier": s.get("tier"), "valid": check_seal(record, s, authorities)}
        for s in record.get("seals", [])
    ]
    if not all(s["valid"] for s in seals):
        return {"tier": "broken", "seals": seals, "capabilities": []}

    tier = max((s["tier"] for s in seals), key=TIER_RANK.__getitem__, default="grey")
    licensed = {}  # capability -> issuers that are allowed to license it
    for issuer_id, authority in authorities.items():
        for capability in authority.get("licenses", []):
            licensed.setdefault(capability, set()).add(issuer_id)
    issuers = {s["issuer"] for s in seals}

    granted = []
    for capability in record.get("capabilities", []):
        if capability in licensed:
            if issuers & licensed[capability]:
                granted.append(capability)
        elif capability in PAYMENT_CAPABILITIES:
            if TIER_RANK[tier] >= TIER_RANK["blue"]:
                granted.append(capability)
        else:
            granted.append(capability)
    return {"tier": tier, "seals": seals, "capabilities": granted}
