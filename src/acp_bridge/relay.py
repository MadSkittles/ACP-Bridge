from __future__ import annotations

import argparse
import asyncio
import contextlib
import http
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from acp_bridge.config import RelayConfig, load_relay_config
from acp_bridge.protocol import (
    ErrorPayload,
    HelloPayload,
    Message,
    RunRequestPayload,
    decode_message,
    encode_message,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Peer:
    websocket: Any
    role: str
    devbox_id: str | None = None


class RelayServer:
    def __init__(
        self,
        *,
        tokens: set[str],
        host: str = "0.0.0.0",
        port: int = 8765,
        max_message_size: int = 1024 * 1024,
    ) -> None:
        self.tokens = tokens
        self.host = host
        self.port = port
        self.max_message_size = max_message_size
        self.workers: dict[str, Peer] = {}
        self.locals: dict[str, Peer] = {}
        self.run_routes: dict[str, Peer] = {}

    @classmethod
    def from_config(cls, config: RelayConfig) -> "RelayServer":
        return cls(
            tokens=config.tokens,
            host=config.host,
            port=config.port,
            max_message_size=config.max_message_size,
        )

    async def start(self):
        return await websockets.serve(
            self._handler,
            self.host,
            self.port,
            max_size=self.max_message_size,
            process_request=self._process_request,
        )

    def _extract_token(self, headers: Any) -> str | None:
        if hasattr(headers, "headers"):
            headers = headers.headers
        auth = headers.get("Authorization") if headers else None
        if not auth or not auth.startswith("Bearer "):
            return None
        return auth.removeprefix("Bearer ").strip()

    def _process_request(self, connection_or_path: Any, request_headers: Any = None):
        headers = request_headers or getattr(connection_or_path, "headers", None)
        token = self._extract_token(headers)
        if token not in self.tokens:
            return http.HTTPStatus.UNAUTHORIZED, [], b"unauthorized\n"
        return None

    async def _handler(self, websocket: Any, path: str | None = None) -> None:
        peer: Peer | None = None
        try:
            first = decode_message(await websocket.recv())
            if first.type != "hello" or not isinstance(first.payload, HelloPayload):
                await websocket.send(
                    encode_message(
                        Message(
                            type="error",
                            payload=ErrorPayload(code="expected_hello", message="first message must be hello"),
                        )
                    )
                )
                return
            peer = Peer(
                websocket=websocket,
                role=first.payload.role,
                devbox_id=first.payload.devbox_id,
            )
            self._register(peer)
            async for raw in websocket:
                message = decode_message(raw)
                await self._route(peer, message)
        except ConnectionClosed:
            pass
        finally:
            if peer is not None:
                self._unregister(peer)

    def _register(self, peer: Peer) -> None:
        key = str(id(peer.websocket))
        if peer.role == "worker":
            if not peer.devbox_id:
                raise ValueError("worker hello requires devbox_id")
            self.workers[peer.devbox_id] = peer
        elif peer.role == "local":
            self.locals[key] = peer
        else:
            raise ValueError(f"unsupported role: {peer.role}")

    def _unregister(self, peer: Peer) -> None:
        key = str(id(peer.websocket))
        if peer.role == "worker" and peer.devbox_id:
            self.workers.pop(peer.devbox_id, None)
        if peer.role == "local":
            self.locals.pop(key, None)
        for run_id, local in list(self.run_routes.items()):
            if local is peer:
                self.run_routes.pop(run_id, None)

    async def _route(self, peer: Peer, message: Message) -> None:
        if message.type == "run_request" and isinstance(message.payload, RunRequestPayload):
            worker = self.workers.get(message.payload.devbox_id)
            if worker is None:
                await peer.websocket.send(
                    encode_message(
                        Message(
                            type="error",
                            request_id=message.request_id,
                            payload=ErrorPayload(
                                code="worker_unavailable",
                                message=f"no worker registered for {message.payload.devbox_id}",
                                run_id=message.payload.run_id,
                                devbox_id=message.payload.devbox_id,
                            ),
                        )
                    )
                )
                return
            self.run_routes[message.payload.run_id] = peer
            await worker.websocket.send(encode_message(message))
            return
        if message.type == "cancel_request":
            devbox_id = getattr(message.payload, "devbox_id", None)
            worker = self.workers.get(devbox_id) if devbox_id else None
            if worker is None:
                for candidate in self.workers.values():
                    worker = candidate
                    break
            if worker is None:
                await peer.websocket.send(
                    encode_message(
                        Message(
                            type="error",
                            request_id=message.request_id,
                            payload=ErrorPayload(code="worker_unavailable", message="no worker registered"),
                        )
                    )
                )
                return
            await worker.websocket.send(encode_message(message))
            return
        run_id = getattr(message.payload, "run_id", None)
        if run_id and run_id in self.run_routes:
            await self.run_routes[run_id].websocket.send(encode_message(message))

    async def serve_forever(self) -> None:
        server = await self.start()
        async with server:
            await asyncio.Future()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="acp-bridge-relay")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    config = load_relay_config(args.config)
    logging.basicConfig(level=logging.DEBUG if config.debug else logging.INFO)
    relay = RelayServer.from_config(config)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(relay.serve_forever())


if __name__ == "__main__":
    main()
