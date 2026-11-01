# APS — Agent Protocol Secure (goal 5, issue #10)

The only place where signatures are made or checked. Real Ed25519 (pynacl) over canonical
JSON (`sort_keys`, compact). Every other area only calls these functions; changes go through
the owner (dev member 2). Wire formats: `documentation/formats.md`.

| File | What |
| --- | --- |
| `canonical.py` | Canonical JSON and strict, canonical base64 (one text per signature), the bytes every signature covers. |
| `keys.py` | Key files in `keys/<id>.json` (demo keys committed on purpose; `keys/local/` private). |
| `envelope.py` | Signed envelopes `{node_id, timestamp, payload, signature}`; opt-in freshness (`max_age_s`, 60 s clock skew). |
| `uid.py` | Swiss business UIDs (CHE-xxx.xxx.xxx) with the mod-11 check digit. |
| `seals.py` | Seals from authorities; `evaluate_record` → tier gold / blue / grey / broken; only the commercial register verifies a UID. |
| `approval.py` | The user's signed decision for one action, payee and exact amount. |
| `delegation.py` | The user's signed scopes for an agent (`ask_agents`, `post_requests`, `negotiate`, `book`; never paying). |
| `call.py` | Signed MCP action calls (tool + args + nonce + time), `NonceBook` against replays. |
| `gate.py` | `ActionGate.check_action(call, Needs(...))`: the one check before `book` / `pay` runs; `commit` after it succeeded. |
| `mandate.py` | Payment mandates: the user pre-signs small payments (≤ CHF 10 each, one payee and purpose, gold/blue only). |

Which signature proves what:

| Signature | By | Proves |
| --- | --- | --- |
| Seal | an authority (handelsregister-bs, adobe, …) | who a node or agent *is* (and its UID) |
| Envelope | a node or agent | it said exactly this, at this time |
| Delegation | the user | this agent may act for me within these scopes |
| Signed call | the user's agent | this agent asks for exactly this action, once |
| Approval | the user | I agree to this action, this payee, this amount |
| Mandate | the user | small payments to this payee for this purpose are fine up to this total |
| Agreement (envelope) | the business | this negotiated price holds, once |

Rules: no signature, no action; keys come from the registry record, never from a message;
checks use nothing up, `commit` does, right after the check (no `await` in between).

Tests: `tests/test_aps.py`, `test_call.py`, `test_gate.py`, `test_mandate.py` (100 % coverage).
