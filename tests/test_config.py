from pathlib import Path

import pytest

from acp_bridge.config import LocalConfig, RelayConfig, WorkerConfig, load_config_file


def test_worker_config_loads_agent_profiles_from_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "worker.yaml"
    config_file.write_text(
        """
relay_url: ws://relay:8765
token: secret
devbox_id: win-dev
allowed_workspaces:
  - C:\\Users\\dev\\repo
default_timeout_sec: 120
max_concurrent_runs: 1
agent_profiles:
  codex:
    executable: codex
    args:
      - exec
      - --cd
      - "{cwd}"
      - --ask-for-approval
      - never
      - --sandbox
      - danger-full-access
      - "{prompt}"
""",
        encoding="utf-8",
    )

    config = load_config_file(config_file, WorkerConfig)

    assert config.devbox_id == "win-dev"
    assert config.agent_profiles["codex"].args[-1] == "{prompt}"
    assert str(config.allowed_workspaces[0]) == "C:\\Users\\dev\\repo"


def test_worker_config_defaults_include_codex_and_claude_profiles() -> None:
    config = WorkerConfig(
        relay_url="ws://relay:8765",
        token="secret",
        devbox_id="win-dev",
        allowed_workspaces=["C:\\work"],
    )

    assert "codex" in config.agent_profiles
    assert "claude" in config.agent_profiles
    assert config.default_timeout_sec > 0


def test_local_config_requires_relay_and_token() -> None:
    with pytest.raises(ValueError):
        LocalConfig(relay_url="", token="")


def test_relay_config_accepts_token_list() -> None:
    config = RelayConfig(tokens=["one", "two"], host="0.0.0.0", port=8080)

    assert config.is_token_allowed("one")
    assert not config.is_token_allowed("three")


def test_load_config_file_rejects_unknown_extension(tmp_path: Path) -> None:
    config_file = tmp_path / "config.txt"
    config_file.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        load_config_file(config_file, LocalConfig)
