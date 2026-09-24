"""Pure-ASGI guard: 415 for non-JSON bodies, 413 for oversized bodies (OWASP A04/A05).

Buffers at most `limit` bytes and replays them downstream, so chunked uploads without
Content-Length are capped too.
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_response

BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class BodyGuardMiddleware:
    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in BODY_METHODS:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        has_body = "transfer-encoding" in headers or (content_length not in (None, "", "0"))

        if has_body:
            media_type = headers.get("content-type", "").split(";")[0].strip().lower()
            if media_type != "application/json":
                await error_response(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type must be application/json")(
                    scope, receive, send
                )
                return

        if content_length is not None:
            try:
                too_big = int(content_length) > self.limit
            except ValueError:
                too_big = True
            if too_big:
                await self._too_large(scope, receive, send)
                return

        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.limit:
                await self._too_large(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        sent = False

        async def replay() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def _too_large(self, scope: Scope, receive: Receive, send: Send) -> None:
        await error_response(413, "PAYLOAD_TOO_LARGE", f"Request body must be at most {self.limit} bytes")(
            scope, receive, send
        )
