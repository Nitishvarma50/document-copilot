"""Text-only AI SDK wire models for the first chat slice."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class WireModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )


class TextPart(WireModel):
    type: Literal["text"] = "text"
    text: str = Field(strict=True, min_length=1, max_length=16_000)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank")
        return value


class NewMessage(WireModel):
    id: UUID
    role: Literal["user"]
    parts: list[TextPart] = Field(min_length=1, max_length=1)


class StreamRequest(WireModel):
    thread_id: UUID
    trigger: Literal["submit-message"]
    messages: list[NewMessage] = Field(min_length=1, max_length=1)


class CreateThread(WireModel):
    title: str = Field(default="New chat", strict=True, min_length=1, max_length=225)

    @field_validator("title")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Title must not be blank")
        return value.strip()


class Thread(WireModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ThreadPage(WireModel):
    threads: list[Thread]
    next_cursor: str | None = None


class MessageMetadata(WireModel):
    sequence: int
    created_at: datetime


class StoredMessage(WireModel):
    id: UUID
    role: Literal["user", "assistant"]
    parts: list[TextPart]
    metadata: MessageMetadata


class MessagePage(WireModel):
    thread: Thread
    messages: list[StoredMessage]
    next_after_sequence: int | None = None


class Turn(WireModel):
    assistant_id: UUID
    attempt_id: UUID
    replay: bool = False
    content: str | None = None
