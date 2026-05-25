from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from acp_bridge.protocol import utc_now_iso

OutputCallback = Callable[[str, str], Awaitable[None]]


@dataclass(slots=True)
class ProcessResult:
    run_id: str | None
    status: str
    stdout: str
    stderr: str
    exit_code: int | None
    started_at: str
    ended_at: str


class ProcessRunner:
    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._cancelled: set[str] = set()

    async def run(
        self,
        command: list[str],
        *,
        cwd: str | Path,
        env: Mapping[str, str],
        timeout_sec: float,
        run_id: str | None = None,
        output_callback: OutputCallback | None = None,
    ) -> ProcessResult:
        run_key = run_id or ""
        started_at = utc_now_iso()
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            env=dict(env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=(os.name != "nt"),
        )
        if run_id:
            self._processes[run_id] = proc
            if run_id in self._cancelled:
                await self._terminate(proc)

        async def consume(stream: asyncio.StreamReader | None, name: str, chunks: list[str]) -> None:
            if stream is None:
                return
            while True:
                data = await stream.readline()
                if not data:
                    break
                text = data.decode(errors="replace")
                chunks.append(text)
                if output_callback:
                    await output_callback(name, text)

        stdout_task = asyncio.create_task(consume(proc.stdout, "stdout", stdout_chunks))
        stderr_task = asyncio.create_task(consume(proc.stderr, "stderr", stderr_chunks))
        status: str
        exit_code: int | None
        try:
            exit_code = await asyncio.wait_for(proc.wait(), timeout=timeout_sec)
            await asyncio.gather(stdout_task, stderr_task)
            if run_id and run_id in self._cancelled:
                status = "cancelled"
                exit_code = None
            else:
                status = "succeeded" if exit_code == 0 else "failed"
        except TimeoutError:
            status = "timeout"
            exit_code = None
            await self._terminate(proc)
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        finally:
            if run_id:
                self._processes.pop(run_id, None)
                self._cancelled.discard(run_id)
        return ProcessResult(
            run_id=run_id,
            status=status,
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            exit_code=exit_code,
            started_at=started_at,
            ended_at=utc_now_iso(),
        )

    def create_run(
        self,
        *,
        run_id: str,
        command: list[str],
        cwd: str | Path,
        env: Mapping[str, str],
        timeout_sec: float,
        output_callback: OutputCallback | None = None,
    ) -> asyncio.Task[ProcessResult]:
        return asyncio.create_task(
            self.run(
                command,
                cwd=cwd,
                env=env,
                timeout_sec=timeout_sec,
                run_id=run_id,
                output_callback=output_callback,
            )
        )

    async def cancel(self, run_id: str) -> bool:
        proc = self._processes.get(run_id)
        if proc is None:
            self._cancelled.add(run_id)
            return False
        self._cancelled.add(run_id)
        await self._terminate(proc)
        return True

    async def _terminate(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        if os.name == "nt":
            proc.terminate()
        else:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except TimeoutError:
            if proc.returncode is None:
                if os.name == "nt":
                    proc.kill()
                else:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        return
                await proc.wait()
