"""The local launcher (scripts/run_all.py): service names, the missing-key warning, prefixed output.

Uses temporary .env files only; the real code/.env is never read here.
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import run_all  # noqa: E402


def test_every_service_gets_a_short_unique_name():
    names = [name for name, _ in run_all.services()]
    assert names[:2] == ["registry", "marketplace"] and names[-1] == "tuttie"
    assert "rheinblick" in names and "guesthouse-am-rhein" in names
    assert len(names) == len(set(names))


def test_no_warning_with_a_key_in_env_file_or_environment(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test-123\n")
    assert run_all.key_warning(env_file, environ={}) is None
    assert run_all.key_warning(tmp_path / "missing", environ={"OPENAI_API_KEY": "sk-test"}) is None


def test_warns_without_a_key_or_with_the_example_placeholder(tmp_path):
    missing = run_all.key_warning(tmp_path / ".env", environ={})
    assert "cp .env.example .env" in missing and "Tuttie cannot answer" in missing
    placeholder = tmp_path / ".env"
    placeholder.write_text("OPENAI_API_KEY=sk-...\nLLM_MODEL=x\n")
    assert "no OPENAI_API_KEY in code/.env." in run_all.key_warning(placeholder, environ={})
    placeholder.write_text("OPENAI_API_KEY=\n")
    assert run_all.key_warning(placeholder, environ={}) is not None


def test_the_warning_never_contains_the_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-...\n")
    assert "sk-" not in run_all.key_warning(env_file, environ={}).replace("sk-...", "")


def test_output_lines_are_prefixed_with_the_service_name(monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr(run_all.sys, "stdout", out)
    run_all.prefix_output("tuttie", io.StringIO("INFO: started\nready\n"), None, width=11)
    assert out.getvalue() == "[tuttie]      INFO: started\n[tuttie]      ready\n"
    coloured = io.StringIO()
    monkeypatch.setattr(run_all.sys, "stdout", coloured)
    run_all.prefix_output("tuttie", io.StringIO("x\n"), 32, width=6)
    assert coloured.getvalue() == "\033[32m[tuttie]\033[0m x\n"
