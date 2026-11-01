"""APS trust bindings: what a seal binds (name, kind, endpoint) and who can pose as an authority.

Regression tests for the round 4b red team findings (all failed before the fix)."""

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from nacl.signing import SigningKey

from aps import evaluate_record, issue_seal, load_signing_key, public_key_b64, sign_envelope
from marketplace import market as market_mod
from aps.delegation import sign_delegation, verify_delegation
from aps.keys import load_public_key
from node.server import requester_problem
from scripts.issue_seals import build_record

CODE = Path(__file__).resolve().parent if (Path(__file__).parent / "aps").exists() else Path.cwd()
AUTHS = {a["issuer"]: a for a in json.loads((CODE / "data/authorities.json").read_text())}
REGISTRY = {r["node_id"]: r for r in json.loads((CODE / "data/registry.json").read_text())}


def self_sealed(node_id, capabilities, uid=None):
    """A grey record whose only seal is its own, as anybody can make."""
    key = SigningKey.generate()
    record = {"node_id": node_id, "name": "Advokatur Muster", "kind": "agent", "uid": uid,
              "public_key": public_key_b64(key), "capabilities": capabilities, "tags": ["basel"],
              "endpoint": "http://localhost:4005"}
    record["seals"] = [issue_seal(record, node_id, "grey", key)]
    return record


def test_a_self_seal_named_after_the_bar_association_does_not_license():
    """The fake lawyer only renames its node_id to the authority's issuer id."""
    verdict = evaluate_record(self_sealed("bar-association-ch", ["licensed_legal_ch"]), AUTHS)
    assert verdict["tier"] == "grey"
    assert "licensed_legal_ch" not in verdict["capabilities"]  # FAILS: granted


def test_a_self_seal_named_after_the_register_does_not_vouch_for_a_uid():
    verdict = evaluate_record(self_sealed("handelsregister-bs", ["can_book"], uid="CHE-526.018.151"), AUTHS)
    assert verdict["tier"] == "grey"
    assert verdict["uid"] is None  # FAILS: Rheinblick's UID shown as register-vouched on a grey node
