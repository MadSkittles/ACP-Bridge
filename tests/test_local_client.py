import pytest

from acp_bridge.local_client import LocalClient
from acp_bridge.protocol import HelloPayload, Message, RunFinishedPayload, decode_message, encode_message


class FakeWebSocket:
    def __init__(self, incoming):
        self.incoming = list(incoming)
        self.sent = []

    async def send(self, message: str) -> None:
        self.sent.append(decode_message(message))

    async def recv(self) -> str:
        return self.incoming.pop(0)


@pytest.mark.asyncio
async def test_local_client_sends_hello_and_run_request() -> None:
    ws = FakeWebSocket(
        [
            encode_message(
                Message(
                    type="run_finished",
                    request_id="req-1",
                    payload=RunFinishedPayload(
                        run_id="run-1",
                        status="succeeded",
                        stdout="ok",
                        stderr="",
                        exit_code=0,
                        started_at="2026-01-01T00:00:00Z",
                        ended_at="2026-01-01T00:00:01Z",
                    ),
                )
            )
        ]
    )
    client = LocalClient(relay_url="ws://relay", token="secret", websocket_factory=lambda: ws)

    result = await client.run("win", "codex", r"C:\repo", "hello", run_id="run-1")

    assert ws.sent[0].type == "hello"
    assert isinstance(ws.sent[0].payload, HelloPayload)
    assert ws.sent[1].type == "run_request"
    assert result.stdout == "ok"
