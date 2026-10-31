"""Ed25519 key generation and the on-disk key file format (keys/<key_id>.json)."""

import json
from pathlib import Path

from nacl.signing import SigningKey, VerifyKey

from aps.canonical import b64decode, b64encode

KEYS_DIR = Path(__file__).resolve().parent.parent / "keys"


def generate_key_file(key_id: str, keys_dir: Path = KEYS_DIR) -> Path:
    """Create keys/<key_id>.json with a fresh key pair, unless it already exists."""
    path = keys_dir / f"{key_id}.json"
    if path.exists():
        return path
    signing_key = SigningKey.generate()
    keys_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "key_id": key_id,
        "public_key": public_key_b64(signing_key),
        "private_key": b64encode(bytes(signing_key)),
    }, indent=2) + "\n")
    return path


def load_signing_key(key_id: str, keys_dir: Path = KEYS_DIR) -> SigningKey:
    data = json.loads((keys_dir / f"{key_id}.json").read_text())
    return SigningKey(b64decode(data["private_key"]))


def public_key_b64(signing_key: SigningKey) -> str:
    return b64encode(bytes(signing_key.verify_key))


def verify_key_from_b64(public_key: str) -> VerifyKey:
    return VerifyKey(b64decode(public_key))
