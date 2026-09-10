"""Bound chat bodies before FastAPI buffers or validates their JSON."""

import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_CHAT_BODY_BYTES = 128 * 1024


class ChatBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] not in ("/chat/stream", "/threads")
        ):
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        total = 0
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    total += len(chunk)
                    if total > MAX_CHAT_BODY_BYTES:
                        await JSONResponse(
                            {"detail": "Request body too large"}, status_code=413
                        )(scope, receive, send)
                        return
                    chunks.append(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await JSONResponse({"detail": "Request body timeout"}, status_code=408)(
                scope, receive, send
            )
            return
        body: bytes | None = b"".join(chunks)

        async def buffered_receive() -> Message:
            nonlocal body
            if body is not None:
                result = {"type": "http.request", "body": body, "more_body": False}
                body = None
                return result
            return await receive()

        await self.app(scope, buffered_receive, send)
