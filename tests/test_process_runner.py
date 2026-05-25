import os
import sys

import pytest

from acp_bridge.process_runner import ProcessRunner


@pytest.mark.asyncio
async def test_process_runner_captures_stdout_stderr_and_exit_code(tmp_path) -> None:
    runner = ProcessRunner()

    result = await runner.run(
        [
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr)",
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_sec=5,
    )

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert "out" in result.stdout
    assert "err" in result.stderr


@pytest.mark.asyncio
async def test_process_runner_maps_nonzero_exit_to_failed(tmp_path) -> None:
    runner = ProcessRunner()

    result = await runner.run(
        [sys.executable, "-c", "import sys; sys.exit(7)"],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_sec=5,
    )

    assert result.status == "failed"
    assert result.exit_code == 7


@pytest.mark.asyncio
async def test_process_runner_times_out_long_process(tmp_path) -> None:
    runner = ProcessRunner()

    result = await runner.run(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_sec=0.1,
    )

    assert result.status == "timeout"
    assert result.exit_code is None


@pytest.mark.asyncio
async def test_process_runner_can_cancel_running_process(tmp_path) -> None:
    runner = ProcessRunner()
    task = runner.create_run(
        run_id="run-cancel",
        command=[sys.executable, "-c", "import time; time.sleep(5)"],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_sec=5,
    )

    await runner.cancel("run-cancel")
    result = await task

    assert result.status == "cancelled"
