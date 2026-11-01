"""The demo user's name (Handan): one user, whichever source names her, and never a crash."""

import os
import subprocess
import sys

import assistant.tools as tools
from tests.test_tools import make_toolbox


def test_own_name_is_not_a_private_term_even_if_env_and_context_differ(monkeypatch):
    """GUEST_NAME and the user context's "user" both name the user: neither becomes 'private'."""
    monkeypatch.setattr(tools, "GUEST_FIRST_NAME", "Alex")
    toolbox, _, _ = make_toolbox()
    assert "handan" not in toolbox.private_terms()
    assert toolbox.public_needs(["quiet", "Handan arrives late"]) == ["quiet", "Handan arrives late"]


def test_empty_guest_name_falls_back_instead_of_crashing():
    """GUEST_NAME= (empty) in .env must not break the assistant's start."""
    env = dict(os.environ, GUEST_NAME="")
    code = "import assistant.agent as a, assistant.tools as t; print(a.GUEST_NAME, t.GUEST_FIRST_NAME)"
    run = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-300:]
    assert run.stdout.split() == ["Handan", "Handan"]
