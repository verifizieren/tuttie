# Demo keys

These Ed25519 keys are **demo-only** and committed on purpose, so everyone on the
team signs and verifies against the same registry. They protect nothing.
Format: `{"key_id", "public_key", "private_key"}`, both base64 (private key = 32-byte seed).

Regenerate a key by deleting its file and running `scripts/gen_keys.py` followed by
`scripts/issue_seals.py`.
