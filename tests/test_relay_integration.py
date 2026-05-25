import asyncio
import sys

import pytest

from acp_bridge.agent_profiles import AgentProfile
from acp_bridge.config import WorkerConfig
from acp_bridge.local_client import LocalClient
from acp_bridge.protocol import (
    HelloPayload,
    Message,
    RunFinishedPayload,
    RunRequestPayload,
    decode_message,
    encode_message,
    utc_now_iso,
)
from acp_bridge.relay import RelayServer
from acp_bridge.worker import Worker


async def wait_for_registered_worker(relay: RelayServer, devbox_id: str) -> None:
    for _ in range(50):
        if devbox_id in relay.workers:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"worker did not register: {devbox_id}")


@pytest.mark.asyncio
async def test_relay_routes_run_request_to_worker_and_result_to_local(unused_tcp_port: int) -> None:
    relay = RelayServer(tokens={"secret"}, host="127.0.0.1", port=unused_tcp_port)
    server = await relay.start()
    uri = f"ws://127.0.0.1:{unused_tcp_port}"

    try:
        import websockets

        async with (
            websockets.connect(uri, additional_headers={"Authorization": "Bearer secret"}) as local,
            websockets.connect(uri, additional_headers={"Authorization": "Bearer secret"}) as worker,
        ):
            await local.send(encode_message(Message(type="hello", payload=HelloPayload(role="local"))))
            await worker.send(
                encode_message(
                    Message(
                        type="hello",
                        payload=HelloPayload(role="worker", devbox_id="win-dev"),
                    )
                )
            )
            await wait_for_registered_worker(relay, "win-dev")

            await local.send(
                encode_message(
                    Message(
                        type="run_request",
                        request_id="req-1",
                        payload=RunRequestPayload(
                            run_id="run-1",
                            devbox_id="win-dev",
                            agent="codex",
                            cwd=r"C:\repo",
                            prompt="hello",
                        ),
                    )
                )
            )
            routed = decode_message(await asyncio.wait_for(worker.recv(), timeout=2))
            assert routed.type == "run_request"
            assert isinstance(routed.payload, RunRequestPayload)
            assert routed.payload.prompt == "hello"

            await worker.send(
                encode_message(
                    Message(
                        type="run_finished",
                        request_id="req-1",
                        payload=RunFinishedPayload(
                            run_id="run-1",
                            status="succeeded",
                            stdout="done",
                            stderr="",
                            exit_code=0,
                            started_at=utc_now_iso(),
                            ended_at=utc_now_iso(),
                        ),
                    )
                )
            )
            result = decode_message(await asyncio.wait_for(local.recv(), timeout=2))
            assert result.type == "run_finished"
            assert isinstance(result.payload, RunFinishedPayload)
            assert result.payload.stdout == "done"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_relay_rejects_unauthorized_token(unused_tcp_port: int) -> None:
    relay = RelayServer(tokens={"secret"}, host="127.0.0.1", port=unused_tcp_port)
    server = await relay.start()

    try:
        import websockets

        with pytest.raises(Exception):
            async with websockets.connect(
                f"ws://127.0.0.1:{unused_tcp_port}",
                additional_headers={"Authorization": "Bearer wrong"},
            ) as ws:
                await ws.send("{}")
                await asyncio.wait_for(ws.recv(), timeout=0.2)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_local_client_runs_fake_agent_through_relay_and_worker(
    unused_tcp_port: int,
    tmp_path,
) -> None:
    relay = RelayServer(tokens={"secret"}, host="127.0.0.1", port=unused_tcp_port)
    server = await relay.start()
    allowed = tmp_path / "repo"
    allowed.mkdir()
    worker = Worker(
        WorkerConfig(
            relay_url=f"ws://127.0.0.1:{unused_tcp_port}",
            token="secret",
            devbox_id="win-dev",
            allowed_workspaces=[str(allowed)],
            agent_profiles={
                "fake": AgentProfile(executable=sys.executable, args=["-c", "{prompt}"])
            },
        )
    )
    worker_task = asyncio.create_task(worker.connect_and_run())
    client = LocalClient(relay_url=f"ws://127.0.0.1:{unused_tcp_port}", token="secret")

    try:
        await wait_for_registered_worker(relay, "win-dev")
        result = await client.run(
            "win-dev",
            "fake",
            str(allowed),
            "import os; print(os.getcwd())",
            timeout_sec=5,
        )

        assert result.status == "succeeded"
        assert result.exit_code == 0
        assert result.stdout.strip() == str(allowed)
    finally:
        worker_task.cancel()
        server.close()
        await server.wait_closed()
        await asyncio.gather(worker_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_local_client_can_cancel_worker_run_through_relay(
    unused_tcp_port: int,
    tmp_path,
) -> None:
    relay = RelayServer(tokens={"secret"}, host="127.0.0.1", port=unused_tcp_port)
    server = await relay.start()
    allowed = tmp_path / "repo"
    allowed.mkdir()
    worker = Worker(
        WorkerConfig(
            relay_url=f"ws://127.0.0.1:{unused_tcp_port}",
            token="secret",
            devbox_id="win-dev",
            allowed_workspaces=[str(allowed)],
            agent_profiles={
                "fake": AgentProfile(executable=sys.executable, args=["-c", "{prompt}"])
            },
        )
    )
    worker_task = asyncio.create_task(worker.connect_and_run())
    client = LocalClient(relay_url=f"ws://127.0.0.1:{unused_tcp_port}", token="secret")

    try:
        await wait_for_registered_worker(relay, "win-dev")
        run_task = asyncio.create_task(
            client.run(
                "win-dev",
                "fake",
                str(allowed),
                "import time; time.sleep(5)",
                timeout_sec=10,
                run_id="run-cancel",
            )
        )
        await asyncio.sleep(0.2)
        await client.cancel("run-cancel", devbox_id="win-dev")
        result = await run_task

        assert result.status == "cancelled"
    finally:
        worker_task.cancel()
        server.close()
        await server.wait_closed()
        await asyncio.gather(worker_task, return_exceptions=True)
