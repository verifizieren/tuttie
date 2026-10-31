"""APS (Agent Protocol Secure): canonical JSON, Ed25519 keys, signed envelopes, seals and Swiss UIDs."""

from aps.canonical import canonical
from aps.envelope import sign_envelope, utc_now, verify_envelope
from aps.keys import generate_key_file, load_signing_key, public_key_b64
from aps.seals import evaluate_record, issue_seal
from aps.uid import is_valid_uid

__all__ = [
    "canonical",
    "evaluate_record",
    "generate_key_file",
    "is_valid_uid",
    "issue_seal",
    "load_signing_key",
    "public_key_b64",
    "sign_envelope",
    "utc_now",
    "verify_envelope",
]
