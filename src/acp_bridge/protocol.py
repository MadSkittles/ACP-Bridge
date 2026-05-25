from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class HelloPayload(BaseModel):
    role: Literal["local", "worker"]
    devbox_id: str | None = None


class RunRequestPayload(BaseModel):
    run_id: str
    devbox_id: str
    agent: str
    cwd: str
    prompt: str
    timeout_sec: float | None = None


class RunStartedPayload(BaseModel):
    run_id: str
    started_at: str


class RunOutputPayload(BaseModel):
    run_id: str
    stream: Literal["stdout", "stderr"]
    data: str


class RunFinishedPayload(BaseModel):
    run_id: str
    status: Literal["succeeded", "failed", "timeout", "cancelled"]
    stdout: str
    stderr: str
    exit_code: int | None
    started_at: str
    ended_at: str


class CancelRequestPayload(BaseModel):
    run_id: str
    devbox_id: str | None = None


class HeartbeatPayload(BaseModel):
    timestamp: str = Field(default_factory=utc_now_iso)


class ErrorPayload(BaseModel):
    code: str
    message: str
    run_id: str | None = None
    devbox_id: str | None = None


Payload = Annotated[
    Union[
        HelloPayload,
        RunRequestPayload,
        RunStartedPayload,
        RunOutputPayload,
        RunFinishedPayload,
        CancelRequestPayload,
        HeartbeatPayload,
        ErrorPayload,
    ],
    Field(discriminator=None),
]


PAYLOAD_TYPES = {
    "hello": HelloPayload,
    "run_request": RunRequestPayload,
    "run_started": RunStartedPayload,
    "run_output": RunOutputPayload,
    "run_finished": RunFinishedPayload,
    "cancel_request": CancelRequestPayload,
    "heartbeat": HeartbeatPayload,
    "error": ErrorPayload,
}


class Message(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    type: Literal[
        "hello",
        "run_request",
        "run_started",
        "run_output",
        "run_finished",
        "cancel_request",
        "heartbeat",
        "error",
    ]
    request_id: str | None = None
    payload: Payload

    @classmethod
    def from_wire(cls, data: str | bytes) -> "Message":
        raw = json.loads(data)
        message_type = raw.get("type")
        payload_type = PAYLOAD_TYPES.get(message_type)
        if payload_type is None:
            return cls.model_validate(raw)
        raw["payload"] = payload_type.model_validate(raw.get("payload", {}))
        return cls.model_validate(raw)


def encode_message(message: Message) -> str:
    return message.model_dump_json()


def decode_message(data: str | bytes) -> Message:
    return Message.from_wire(data)
