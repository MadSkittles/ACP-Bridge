from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, Field


class AgentProfile(BaseModel):
    """Configuration for rendering an agent subprocess command."""

    executable: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_sec: float | None = None
    extra_flags: list[str] = Field(default_factory=list)

    def render_command(self, *, cwd: str, prompt: str) -> list[str]:
        command = [self.executable]
        for arg in self.args:
            if arg == "{extra_flags}":
                command.extend(self.extra_flags)
                continue
            command.append(arg.format(cwd=cwd, prompt=prompt))
        return command

    def render_env(self, base_env: Mapping[str, str]) -> dict[str, str]:
        rendered = dict(base_env)
        rendered.update(self.env)
        return rendered


def default_agent_profiles() -> dict[str, AgentProfile]:
    return {
        "codex": AgentProfile(
            executable="codex",
            args=[
                "exec",
                "--cd",
                "{cwd}",
                "--ask-for-approval",
                "never",
                "--sandbox",
                "danger-full-access",
                "{extra_flags}",
                "{prompt}",
            ],
        ),
        "claude": AgentProfile(
            executable="claude",
            args=[
                "--print",
                "--permission-mode",
                "bypassPermissions",
                "{extra_flags}",
                "{prompt}",
            ],
        ),
    }
