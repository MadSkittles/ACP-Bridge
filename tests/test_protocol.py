from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from acp_bridge.protocol import (
    ErrorPayload,
    HelloPayload,
    Message,
    RunFinishedPayload,
    decode_message,
    encode_message,
    utc_now_iso,
)


def test_protocol_roundtrip_preserves_type_and_payload() -> None:
    message = Message(
        type="hello",
        request_id="req-1",
        payload=HelloPayload(role="worker", devbox_id="win-dev"),
    )

    decoded = decode_message(encode_message(message))

    assert decoded.type == "hello"
    assert decoded.request_id == "req-1"
    assert isinstance(decoded.payload, HelloPayload)
    assert decoded.payload.role == "worker"
    assert decoded.payload.devbox_id == "win-dev"


def test_protocol_rejects_unknown_message_type() -> None:
    with pytest.raises(ValidationError):
        decode_message('{"type":"bogus","payload":{}}')


def test_run_finished_payload_accepts_terminal_status_and_timing() -> None:
    payload = RunFinishedPayload(
        run_id="run-1",
        status="succeeded",
        stdout="ok",
        stderr="",
        exit_code=0,
        started_at=utc_now_iso(),
        ended_at=utc_now_iso(),
    )

    assert payload.exit_code == 0
    assert payload.status == "succeeded"


def test_error_payload_does_not_require_prompt_body() -> None:
    payload = ErrorPayload(code="worker_unavailable", message="No worker registered")

    assert payload.code == "worker_unavailable"
    assert "prompt" not in payload.model_dump()


def test_utc_now_iso_is_timezone_aware() -> None:
    parsed = datetime.fromisoformat(utc_now_iso().replace("Z", "+00:00"))

    assert parsed.tzinfo == UTC
