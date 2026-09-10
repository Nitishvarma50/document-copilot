"""AI SDK UI-message SSE framing and bounded stub orchestration."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

import anyio
from app.chat.schemas import Turn
from app.config import settings
from app.Database.chats import ChatStore

logger = logging.getLogger(__name__)
STUB_RESPONSE = (
    "Stub response: chat streaming is connected. Retrieval is not enabled yet."
)
ERROR_TEXT = "Unable to complete this response. Please reload history and try again."


def event(kind: str, **data: object) -> str:
    return f"data: {json.dumps({'type': kind, **data}, ensure_ascii=False)}\n\n"


async def stream_turn(
    store: ChatStore,
    thread_id: UUID,
    turn: Turn,
) -> AsyncIterator[str]:
    committed = turn.replay
    try:
        async with asyncio.timeout(settings.chat_turn_timeout_seconds):
            text = turn.content if turn.replay else STUB_RESPONSE
            if not text:
                raise ValueError("Completed turn has no stored answer")
            yield event("start", messageId=str(turn.assistant_id))
            yield event("text-start", id="text-1")
            # Short asynchronous chunks exercise the real streaming UI, not an LLM.
            for start in range(0, len(text), 12):
                await asyncio.sleep(0 if turn.replay else 0.03)
                yield event("text-delta", id="text-1", delta=text[start : start + 12])
            if not turn.replay:
                await store.complete(thread_id, turn, text)
                committed = True
            yield event("text-end", id="text-1")
            yield event("finish", finishReason="stop")
            yield "data: [DONE]\n\n"
    except asyncio.CancelledError:
        # The client is gone: do not try to send another frame.
        raise
    except Exception:
        logger.warning("Chat turn did not complete")
        yield event("error", errorText=ERROR_TEXT)
        yield "data: [DONE]\n\n"
    finally:
        if not committed:
            # Cancellation must not interrupt releasing the reservation. A DB lease
            # also recovers from worker death or a storage outage during cleanup.
            with anyio.move_on_after(2, shield=True):
                try:
                    await store.abandon(thread_id, turn)
                except Exception:
                    logger.warning("Chat reservation cleanup deferred to lease expiry")
