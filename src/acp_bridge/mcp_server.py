from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from acp_bridge.config import LocalConfig, load_local_config
from acp_bridge.local_client import LocalClient


def _load_config() -> LocalConfig:
    path = os.environ.get("ACP_BRIDGE_LOCAL_CONFIG")
    return load_local_config(Path(path) if path else None)


def _client() -> LocalClient:
    config = _load_config()
    return LocalClient(relay_url=config.relay_url, token=config.token)


def build_server() -> FastMCP:
    server = FastMCP("acp-bridge")

    @server.tool()
    def remote_agent_list() -> dict[str, Any]:
        """List locally configured remote agent defaults."""
        config = _load_config()
        return {
            "default_devbox_id": config.default_devbox_id,
            "default_agent": config.default_agent,
            "cwd_map": config.cwd_map,
        }

    @server.tool()
    def remote_agent_ping(devbox_id: str) -> dict[str, Any]:
        """Ping a remote devbox."""
        return asyncio.run(_client().ping(devbox_id))

    @server.tool()
    def remote_agent_run(
        devbox_id: str,
        agent: str,
        cwd: str,
        prompt: str,
        timeout_sec: float | None = None,
    ) -> dict[str, Any]:
        """Run a non-interactive remote CLI agent."""
        result = asyncio.run(
            _client().run(
                devbox_id=devbox_id,
                agent=agent,
                cwd=cwd,
                prompt=prompt,
                timeout_sec=timeout_sec,
            )
        )
        return result.model_dump()

    @server.tool()
    def remote_agent_cancel(run_id: str) -> dict[str, Any]:
        """Cancel a remote run."""
        asyncio.run(_client().cancel(run_id))
        return {"run_id": run_id, "status": "cancel_requested"}

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
