from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from pathlib import Path
from typing import Mapping

import websockets

from acp_bridge.config import WorkerConfig, load_worker_config
from acp_bridge.process_runner import ProcessResult, ProcessRunner
from acp_bridge.protocol import (
    CancelRequestPayload,
    ErrorPayload,
    HelloPayload,
    Message,
    RunFinishedPayload,
    RunOutputPayload,
    RunRequestPayload,
    RunStartedPayload,
    decode_message,
    encode_message,
    utc_now_iso,
)
from acp_bridge.workspace import is_path_allowed


class Worker:
    def __init__(self, config: WorkerConfig) -> None:
        self.config = config
        self.runner = ProcessRunner()
        self._semaphore = asyncio.Semaphore(config.max_concurrent_runs)

    async def run_once(
        self,
        request: RunRequestPayload,
        *,
        base_env: Mapping[str, str] | None = None,
        output_callback=None,
    ) -> ProcessResult:
        if request.devbox_id != self.config.devbox_id:
            now = utc_now_iso()
            return ProcessResult(
                run_id=request.run_id,
                status="failed",
                stdout="",
                stderr=f"request targets {request.devbox_id}, worker is {self.config.devbox_id}",
                exit_code=None,
                started_at=now,
                ended_at=now,
            )
        if not is_path_allowed(request.cwd, self.config.allowed_workspaces):
            now = utc_now_iso()
            return ProcessResult(
                run_id=request.run_id,
                status="failed",
                stdout="",
                stderr=f"cwd is not allowed: {request.cwd}",
                exit_code=None,
                started_at=now,
                ended_at=now,
            )
        profile = self.config.agent_profiles.get(request.agent)
        if profile is None:
            now = utc_now_iso()
            return ProcessResult(
                run_id=request.run_id,
                status="failed",
                stdout="",
                stderr=f"unknown agent profile: {request.agent}",
                exit_code=None,
                started_at=now,
                ended_at=now,
            )
        command = profile.render_command(cwd=request.cwd, prompt=request.prompt)
        env = profile.render_env(base_env or os.environ)
        timeout = request.timeout_sec or profile.timeout_sec or self.config.default_timeout_sec
        async with self._semaphore:
            return await self.runner.run(
                command,
                cwd=request.cwd,
                env=env,
                timeout_sec=timeout,
                run_id=request.run_id,
                output_callback=output_callback,
            )

    async def connect_and_run(self) -> None:
        async with websockets.connect(
            self.config.relay_url,
            additional_headers={"Authorization": f"Bearer {self.config.token}"},
        ) as ws:
            await ws.send(
                encode_message(
                    Message(
                        type="hello",
                        payload=HelloPayload(role="worker", devbox_id=self.config.devbox_id),
                    )
                )
            )
            tasks: set[asyncio.Task[None]] = set()
            async for raw in ws:
                message = decode_message(raw)
                if message.type == "run_request" and isinstance(message.payload, RunRequestPayload):
                    task = asyncio.create_task(self._handle_run(ws, message))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                elif message.type == "cancel_request" and isinstance(message.payload, CancelRequestPayload):
                    await self.runner.cancel(message.payload.run_id)

    async def _handle_run(self, ws, message: Message) -> None:
        request = message.payload
        assert isinstance(request, RunRequestPayload)
        await ws.send(
            encode_message(
                Message(
                    type="run_started",
                    request_id=message.request_id,
                    payload=RunStartedPayload(run_id=request.run_id, started_at=utc_now_iso()),
                )
            )
        )

        async def send_output(stream: str, data: str) -> None:
            await ws.send(
                encode_message(
                    Message(
                        type="run_output",
                        request_id=message.request_id,
                        payload=RunOutputPayload(run_id=request.run_id, stream=stream, data=data),
                    )
                )
            )

        try:
            result = await self.run_once(request, output_callback=send_output)
            await ws.send(
                encode_message(
                    Message(
                        type="run_finished",
                        request_id=message.request_id,
                        payload=RunFinishedPayload(
                            run_id=request.run_id,
                            status=result.status,  # type: ignore[arg-type]
                            stdout=result.stdout,
                            stderr=result.stderr,
                            exit_code=result.exit_code,
                            started_at=result.started_at,
                            ended_at=result.ended_at,
                        ),
                    )
                )
            )
        except Exception as exc:
            await ws.send(
                encode_message(
                    Message(
                        type="error",
                        request_id=message.request_id,
                        payload=ErrorPayload(
                            code="worker_error",
                            message=str(exc),
                            run_id=request.run_id,
                            devbox_id=self.config.devbox_id,
                        ),
                    )
                )
            )

    def build_install_task_command(
        self,
        *,
        task_name: str = "ACP Bridge Worker",
        config_path: str | None = None,
    ) -> list[str]:
        config_arg = config_path or str(Path.home() / ".config" / "acp-bridge" / "worker.yaml")
        command = f'acp-bridge-worker --config "{config_arg}"'
        return [
            "schtasks",
            "/Create",
            "/TN",
            task_name,
            "/SC",
            "ONLOGON",
            "/TR",
            command,
            "/F",
        ]

    def build_uninstall_task_command(self, *, task_name: str = "ACP Bridge Worker") -> list[str]:
        return ["schtasks", "/Delete", "/TN", task_name, "/F"]


async def run_worker(config_path: Path | None = None) -> None:
    worker = Worker(load_worker_config(config_path))
    await worker.connect_and_run()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="acp-bridge-worker")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_worker(args.config))


if __name__ == "__main__":
    main()
