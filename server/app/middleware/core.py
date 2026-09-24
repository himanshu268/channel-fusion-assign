"""Outermost middleware: request id, security headers (helmet equivalent), 500 boundary, access log."""

from __future__ import annotations

import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import error_response
from app.core.logging import logger

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")  # blocks log injection via header

# Equivalent of helmet() defaults, tightened for a JSON-only API (OWASP A05).
API_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=15552000; includeSubDomains",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-DNS-Prefetch-Control": "off",
    "X-Permitted-Cross-Domain-Policies": "none",
    "Cache-Control": "no-store",
}
# Swagger UI (dev only) needs its CDN assets, so it gets the baseline without the strict CSP.
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class CoreMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            # Full error logged server-side only; client gets a generic envelope, never a stack.
            logger.exception("unhandled error", extra={"request_id": request_id, "path": request.url.path})
            response = error_response(500, "INTERNAL_ERROR", "Something went wrong")

        headers = API_SECURITY_HEADERS
        if request.url.path.startswith(DOCS_PATHS):
            headers = {k: v for k, v in headers.items() if k != "Content-Security-Policy"}
        for k, v in headers.items():
            response.headers.setdefault(k, v)
        response.headers["X-Request-Id"] = request_id

        status = response.status_code
        level = 40 if status >= 500 else 30 if status in (400, 413, 415, 429) else 20
        logger.log(
            level,
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                "ip": getattr(request.state, "client_ip", request.client.host if request.client else None),
            },
        )
        return response
