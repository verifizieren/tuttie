"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def no_real_deployments(tmp_path, monkeypatch):
    """Every test starts from the committed node configs, never from settings an owner deployed
    on this machine (code/data/deployments/, see node/deployments.py)."""
    monkeypatch.setenv("OWNER_DATA_DIR", str(tmp_path / "no-deployments"))
