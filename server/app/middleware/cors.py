"""CORSMiddleware whose rejected preflights use the JSON error envelope instead of Starlette's text/plain."""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.core.errors import error_response

_BODY_HEADERS = frozenset({"content-type", "content-length"})


class JsonCORSMiddleware(CORSMiddleware):
    def preflight_response(self, request_headers: Headers) -> Response:
        response = super().preflight_response(request_headers)
        if response.status_code != 400:
            return response
        # keep Vary / Access-Control-* headers, swap only the body
        headers = {k: v for k, v in response.headers.items() if k.lower() not in _BODY_HEADERS}
        message = bytes(response.body).decode()  # e.g. "Disallowed CORS origin, method"
        return error_response(400, "VALIDATION_ERROR", message, headers=headers)
