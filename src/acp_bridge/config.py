from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from acp_bridge.agent_profiles import AgentProfile, default_agent_profiles

ConfigT = TypeVar("ConfigT", bound=BaseModel)


class LocalConfig(BaseModel):
    relay_url: str
    token: str
    default_devbox_id: str | None = None
    default_agent: str | None = None
    cwd_map: dict[str, str] = Field(default_factory=dict)

    @field_validator("relay_url", "token")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("value must not be empty")
        return value


class WorkerConfig(BaseModel):
    relay_url: str
    token: str
    devbox_id: str
    allowed_workspaces: list[str]
    agent_profiles: dict[str, AgentProfile] = Field(default_factory=default_agent_profiles)
    default_timeout_sec: float = 1800
    max_concurrent_runs: int = 1

    @field_validator("relay_url", "token", "devbox_id")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("allowed_workspaces")
    @classmethod
    def _allowed_workspaces_required(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("at least one allowed workspace is required")
        return value

    @model_validator(mode="after")
    def _merge_default_profiles(self) -> "WorkerConfig":
        merged = default_agent_profiles()
        merged.update(self.agent_profiles)
        self.agent_profiles = merged
        return self


class RelayConfig(BaseModel):
    token: str | None = None
    tokens: set[str] = Field(default_factory=set)
    host: str = "0.0.0.0"
    port: int = 8765
    heartbeat_timeout_sec: float = 30
    max_message_size: int = 1024 * 1024
    debug: bool = False

    @model_validator(mode="after")
    def _normalize_tokens(self) -> "RelayConfig":
        if self.token:
            self.tokens.add(self.token)
        if not self.tokens:
            raise ValueError("at least one token is required")
        return self

    def is_token_allowed(self, token: str) -> bool:
        return token in self.tokens


def default_config_path(kind: str) -> Path:
    base = Path(os.environ.get("ACP_BRIDGE_CONFIG_DIR", Path.home() / ".config" / "acp-bridge"))
    return base / f"{kind}.yaml"


def load_config_file(path: Path | str, config_type: type[ConfigT]) -> ConfigT:
    config_path = Path(path)
    suffix = config_path.suffix.lower()
    raw = config_path.read_text(encoding="utf-8")
    if suffix in {".yaml", ".yml"}:
        data: dict[str, Any] = yaml.safe_load(raw) or {}
    elif suffix == ".json":
        data = json.loads(raw)
    else:
        raise ValueError(f"unsupported config extension: {config_path.suffix}")
    return config_type.model_validate(data)


def load_local_config(path: Path | None = None) -> LocalConfig:
    return load_config_file(path or default_config_path("local"), LocalConfig)


def load_worker_config(path: Path | None = None) -> WorkerConfig:
    return load_config_file(path or default_config_path("worker"), WorkerConfig)


def load_relay_config(path: Path | None = None) -> RelayConfig:
    return load_config_file(path or default_config_path("relay"), RelayConfig)
