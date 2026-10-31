"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def no_real_deployments(tmp_path, monkeypatch):
    """Every test starts from the committed node configs, never from settings an owner deployed
    on this machine (code/data/deployments/, see node/deployments.py)."""
    monkeypatch.setenv("OWNER_DATA_DIR", str(tmp_path / "no-deployments"))


@pytest.fixture(autouse=True)
def no_agent_key(monkeypatch):
    """Agent doors start open (aps/agent_key.py), whatever key the shell running the tests has."""
    monkeypatch.delenv("AGENT_WEB_KEY", raising=False)
