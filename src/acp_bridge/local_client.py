from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import websockets

from acp_bridge.protocol import (
    CancelRequestPayload,
    ErrorPayload,
    HelloPayload,
    Message,
    RunFinishedPayload,
    RunOutputPayload,
    RunRequestPayload,
    decode_message,
    encode_message,
)


class LocalClient:
    def __init__(
        self,
        *,
        relay_url: str,
        token: str,
        websocket_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.relay_url = relay_url
        self.token = token
        self.websocket_factory = websocket_factory

    async def _connect(self):
        if self.websocket_factory is not None:
            return self.websocket_factory()
        return await websockets.connect(
            self.relay_url,
            additional_headers={"Authorization": f"Bearer {self.token}"},
        )

    async def run(
        self,
        devbox_id: str,
        agent: str,
        cwd: str,
        prompt: str,
        *,
        timeout_sec: float | None = None,
        run_id: str | None = None,
        stream_callback: Callable[[RunOutputPayload], None] | None = None,
    ) -> RunFinishedPayload:
        run_id = run_id or str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        ws = await self._connect()
        close = getattr(ws, "close", None)
        try:
            await ws.send(encode_message(Message(type="hello", payload=HelloPayload(role="local"))))
            await ws.send(
                encode_message(
                    Message(
                        type="run_request",
                        request_id=request_id,
                        payload=RunRequestPayload(
                            run_id=run_id,
                            devbox_id=devbox_id,
                            agent=agent,
                            cwd=cwd,
                            prompt=prompt,
                            timeout_sec=timeout_sec,
                        ),
                    )
                )
            )
            while True:
                message = decode_message(await ws.recv())
                if message.type == "run_output" and isinstance(message.payload, RunOutputPayload):
                    if stream_callback:
                        stream_callback(message.payload)
                    continue
                if message.type == "run_finished" and isinstance(message.payload, RunFinishedPayload):
                    return message.payload
                if message.type == "error" and isinstance(message.payload, ErrorPayload):
                    raise RuntimeError(message.payload.message)
        finally:
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result

    async def cancel(self, run_id: str, devbox_id: str | None = None) -> None:
        ws = await self._connect()
        close = getattr(ws, "close", None)
        try:
            await ws.send(encode_message(Message(type="hello", payload=HelloPayload(role="local"))))
            await ws.send(
                encode_message(
                    Message(
                        type="cancel_request",
                        payload=CancelRequestPayload(run_id=run_id, devbox_id=devbox_id),
                    )
                )
            )
        finally:
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result

    async def ping(self, devbox_id: str) -> dict[str, str]:
        try:
            result = await self.run(
                devbox_id=devbox_id,
                agent="codex",
                cwd=".",
                prompt="",
                timeout_sec=1,
                run_id=f"ping-{uuid.uuid4()}",
            )
        except RuntimeError as exc:
            return {"devbox_id": devbox_id, "status": "unavailable", "message": str(exc)}
        return {"devbox_id": devbox_id, "status": result.status}
