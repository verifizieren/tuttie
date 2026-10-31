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


def test_voice_adds_livekit_and_the_agent_only_when_configured(monkeypatch, tmp_path):
    server = tmp_path / "livekit-server"
    server.write_text("")
    monkeypatch.setattr(run_all, "LIVEKIT_SERVER", server)
    keys = {"LIVEKIT_API_KEY": "k", "LIVEKIT_API_SECRET": "s", "LIVEKIT_NODE_IP": "1.2.3.4"}
    assert [n for n, _ in run_all.services(keys)][-1] == "livekit"
    assert [n for n, _ in run_all.services({**keys, "ELEVENLABS_KEY": "e"})][-2:] == ["livekit", "voice"]
    assert "--node-ip" in dict(run_all.services(keys))["livekit"]
    assert "livekit" not in dict(run_all.services({"ELEVENLABS_KEY": "e"}))  # no LiveKit keys: text only


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


def test_the_turn_relay_runs_and_is_handed_to_livekit_only_when_configured(monkeypatch, tmp_path):
    assert run_all.livekit_config({}) == ["--config", "voice/livekit.yaml"]
    turnserver = tmp_path / "usr" / "bin" / "turnserver"
    turnserver.parent.mkdir(parents=True)
    turnserver.touch()
    monkeypatch.setattr(run_all, "TURNSERVER", turnserver)
    voice = {"TURN_SECRET": "s3cret", "LIVEKIT_NODE_IP": "203.0.113.5"}
    flag, body = run_all.livekit_config(voice)
    assert flag == "--config-body" and "tcp_port: 4042" in body
    assert "turn_servers:\n    - host: 203.0.113.5\n      port: 4044\n      protocol: tcp" in body
    command = run_all.turn_command(voice)
    assert "--allowed-peer-ip" in command and command[command.index("--allowed-peer-ip") + 1] == "203.0.113.5"
