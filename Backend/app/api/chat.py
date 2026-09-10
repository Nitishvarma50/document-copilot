"""Authenticated thread APIs and the text-only streamed stub endpoint."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from app.auth.dependencies import CurrentUser, get_access_token, get_current_user
from app.chat.schemas import (
    CreateThread,
    MessagePage,
    StreamRequest,
    Thread,
    ThreadPage,
)
from app.chat.streaming import stream_turn
from app.Database.chats import ChatStore, SupabaseChatStore
from app.Database.supabase import managed_client
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["chat"])


async def get_chat_store(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    token: Annotated[str, Depends(get_access_token)],
) -> AsyncIterator[ChatStore]:
    async with managed_client(access_token=token) as reader:
        async with managed_client(privileged=True) as writer:
            yield SupabaseChatStore(reader, writer, user)


Store = Annotated[ChatStore, Depends(get_chat_store)]


@router.post("/threads", response_model=Thread, status_code=201)
async def create_thread(body: CreateThread, store: Store) -> Thread:
    return await store.create_thread(body.title)


@router.get("/threads", response_model=ThreadPage)
async def list_threads(
    store: Store,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
) -> ThreadPage:
    return await store.list_threads(limit, cursor)


@router.get("/threads/{thread_id}/messages", response_model=MessagePage)
async def messages(
    thread_id: UUID,
    store: Store,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    after_sequence: Annotated[int, Query(alias="afterSequence", ge=0)] = 0,
) -> MessagePage:
    return await store.messages(thread_id, limit, after_sequence)


@router.post("/chat/stream")
async def chat_stream(body: StreamRequest, store: Store) -> StreamingResponse:
    message = body.messages[0]
    turn = await store.accept(body.thread_id, message.id, message.parts[0].text)
    return StreamingResponse(
        stream_turn(store, body.thread_id, turn),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "x-vercel-ai-ui-message-stream": "v1",
            "X-Accel-Buffering": "no",
        },
    )
