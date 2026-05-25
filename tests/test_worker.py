import os
import sys

import pytest

from acp_bridge.agent_profiles import AgentProfile
from acp_bridge.config import WorkerConfig
from acp_bridge.protocol import RunRequestPayload
from acp_bridge.worker import Worker


@pytest.mark.asyncio
async def test_worker_rejects_disallowed_cwd_before_launch(tmp_path) -> None:
    config = WorkerConfig(
        relay_url="ws://relay",
        token="secret",
        devbox_id="win",
        allowed_workspaces=[str(tmp_path / "allowed")],
        agent_profiles={"codex": AgentProfile(executable=sys.executable, args=["-c", "{prompt}"])},
    )
    worker = Worker(config)

    result = await worker.run_once(
        RunRequestPayload(
            run_id="run-1",
            devbox_id="win",
            agent="codex",
            cwd=str(tmp_path / "other"),
            prompt="print('should not run')",
        ),
        base_env=os.environ.copy(),
    )

    assert result.status == "failed"
    assert result.exit_code is None
    assert "not allowed" in result.stderr


@pytest.mark.asyncio
async def test_worker_runs_configured_agent_in_allowed_cwd(tmp_path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    config = WorkerConfig(
        relay_url="ws://relay",
        token="secret",
        devbox_id="win",
        allowed_workspaces=[str(allowed)],
        agent_profiles={"codex": AgentProfile(executable=sys.executable, args=["-c", "{prompt}"])},
    )
    worker = Worker(config)

    result = await worker.run_once(
        RunRequestPayload(
            run_id="run-1",
            devbox_id="win",
            agent="codex",
            cwd=str(allowed),
            prompt="print('ok')",
        ),
        base_env=os.environ.copy(),
    )

    assert result.status == "succeeded"
    assert result.stdout.strip() == "ok"


def test_task_scheduler_install_command_contains_logon_trigger() -> None:
    config = WorkerConfig(
        relay_url="ws://relay",
        token="secret",
        devbox_id="win",
        allowed_workspaces=[r"C:\repo"],
    )
    worker = Worker(config)

    command = worker.build_install_task_command(task_name="ACP Bridge Worker", config_path=r"C:\cfg.yaml")

    assert "/SC" in command
    assert "ONLOGON" in command
    assert "acp-bridge-worker" in " ".join(command)
