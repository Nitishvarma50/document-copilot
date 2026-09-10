"""Supabase chat persistence; writes use server-only transactional RPCs."""

import asyncio
import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import httpx
from app.auth.dependencies import CurrentUser
from app.chat.errors import ChatError
from app.chat.schemas import (
    MessageMetadata,
    MessagePage,
    StoredMessage,
    Thread,
    ThreadPage,
    Turn,
)
from app.config import settings
from postgrest.exceptions import APIError
from pydantic import ValidationError
from supabase import AsyncClient


class ChatStore(Protocol):
    async def create_thread(self, title: str) -> Thread: ...
    async def list_threads(self, limit: int, cursor: str | None) -> ThreadPage: ...
    async def messages(
        self, thread_id: UUID, limit: int, after_sequence: int
    ) -> MessagePage: ...
    async def accept(self, thread_id: UUID, message_id: UUID, text: str) -> Turn: ...
    async def complete(self, thread_id: UUID, turn: Turn, text: str) -> None: ...
    async def abandon(self, thread_id: UUID, turn: Turn) -> None: ...


def encode_cursor(thread: Thread) -> str:
    data = [thread.updated_at.isoformat(), str(thread.id)]
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        values = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if (
            not isinstance(values, list)
            or len(values) != 2
            or not all(isinstance(value, str) for value in values)
        ):
            raise ValueError
        timestamp = datetime.fromisoformat(values[0])
        if timestamp.tzinfo is None:
            raise ValueError
        return timestamp.astimezone(UTC).isoformat(), str(UUID(values[1]))
    except (ValueError, TypeError, binascii.Error, UnicodeError) as exc:
        raise ChatError(422, "Invalid thread cursor") from exc


async def execute(query: Any) -> Any:
    """Never expose database messages, SQL, or upstream response bodies."""
    try:
        async with asyncio.timeout(settings.supabase_request_timeout_seconds):
            return (await query.execute()).data
    except APIError as exc:
        safe_errors = {
            "PT404": (404, "Thread not found"),
            "PT409": (409, "Turn conflict; reload history before retrying"),
            "PT422": (422, "Invalid chat request"),
            "23505": (409, "Turn conflict; reload history before retrying"),
            "55P03": (409, "Thread is busy; reload history before retrying"),
            "57014": (503, "Chat storage unavailable"),
            "PGRST301": (401, "Invalid or expired token"),
            "PGRST303": (401, "Invalid or expired token"),
        }
        code, detail = safe_errors.get(
            exc.code or "", (502, "Chat storage unavailable")
        )
        raise ChatError(code, detail) from exc
    except (httpx.HTTPError, TimeoutError) as exc:
        raise ChatError(503, "Chat storage unavailable") from exc


def thread_from_row(row: dict[str, Any]) -> Thread:
    return Thread(
        **{key: row[key] for key in ("id", "title", "created_at", "updated_at")}
    )


class SupabaseChatStore:
    def __init__(
        self, reader: AsyncClient, writer: AsyncClient, user: CurrentUser
    ) -> None:
        self.reader, self.writer, self.user = reader, writer, user

    async def rpc(self, name: str, **params: Any) -> Any:
        return await execute(
            self.writer.rpc(
                name,
                {
                    "p_user_id": str(self.user.id),
                    **params,
                },
            )
        )

    async def create_thread(self, title: str) -> Thread:
        row = await self.rpc(
            "chat_create_thread", p_email=self.user.email, p_title=title
        )
        return thread_from_row(row)

    async def list_threads(self, limit: int, cursor: str | None) -> ThreadPage:
        query = (
            self.reader.table("chat_threads")
            .select("*")
            .eq("user_id", str(self.user.id))
        )
        if cursor:
            timestamp, thread_id = decode_cursor(cursor)
            query = query.or_(
                f"updated_at.lt.{timestamp},"
                f"and(updated_at.eq.{timestamp},id.lt.{thread_id})"
            )
        rows = await execute(
            query.order("updated_at", desc=True).order("id", desc=True).limit(limit + 1)
        )
        threads = [thread_from_row(row) for row in rows[:limit]]
        return ThreadPage(
            threads=threads,
            next_cursor=(encode_cursor(threads[-1]) if len(rows) > limit else None),
        )

    async def owned_thread(self, thread_id: UUID) -> Thread:
        rows = await execute(
            self.reader.table("chat_threads")
            .select("*")
            .eq("id", str(thread_id))
            .eq("user_id", str(self.user.id))
            .limit(1)
        )
        if not rows:
            raise ChatError(404, "Thread not found")
        return thread_from_row(rows[0])

    async def messages(
        self, thread_id: UUID, limit: int, after_sequence: int
    ) -> MessagePage:
        thread = await self.owned_thread(thread_id)
        rows = await execute(
            self.reader.table("chat_messages")
            .select("*")
            .eq("thread_id", str(thread_id))
            .gt("sequence", after_sequence)
            .order("sequence")
            .limit(limit + 1)
        )
        try:
            messages = [
                StoredMessage(
                    id=row["id"],
                    role=row["role"],
                    parts=row["parts"],
                    metadata=MessageMetadata(
                        sequence=row["sequence"], created_at=row["created_at"]
                    ),
                )
                for row in rows[:limit]
            ]
        except (KeyError, ValidationError) as exc:
            raise ChatError(502, "Stored history has an unsupported format") from exc
        return MessagePage(
            thread=thread,
            messages=messages,
            next_after_sequence=(
                messages[-1].metadata.sequence if len(rows) > limit else None
            ),
        )

    async def accept(self, thread_id: UUID, message_id: UUID, text: str) -> Turn:
        return Turn.model_validate(
            await self.rpc(
                "chat_accept_turn",
                p_thread_id=str(thread_id),
                p_message_id=str(message_id),
                p_text=text,
            )
        )

    async def complete(self, thread_id: UUID, turn: Turn, text: str) -> None:
        await self.rpc(
            "chat_complete_turn",
            p_thread_id=str(thread_id),
            p_assistant_id=str(turn.assistant_id),
            p_attempt_id=str(turn.attempt_id),
            p_text=text,
        )

    async def abandon(self, thread_id: UUID, turn: Turn) -> None:
        await self.rpc(
            "chat_abandon_turn",
            p_thread_id=str(thread_id),
            p_assistant_id=str(turn.assistant_id),
            p_attempt_id=str(turn.attempt_id),
        )
