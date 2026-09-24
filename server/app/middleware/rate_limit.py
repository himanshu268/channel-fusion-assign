"""Per-IP fixed-window rate limiting: global + stricter write limiter (OWASP A04).

In-memory store is fine for a single process. For multiple instances, swap FixedWindowLimiter
for a Redis-backed implementation with the same `hit()` signature.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import Settings
from app.core.errors import error_response

WRITE_METHODS = frozenset({"POST", "PATCH"})
# Liveness probes from LBs/orchestrators must never be throttled into a false "unhealthy".
EXEMPT_PATHS = frozenset({"/api/v1/health"})


@dataclass(frozen=True)
class HitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


class FixedWindowLimiter:
    def __init__(self, limit: int, window_ms: int, now: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.window = window_ms / 1000
        self._now = now
        self._hits: dict[str, tuple[float, int]] = {}  # key -> (window_start, count)
        self._lock = threading.Lock()

    def hit(self, key: str) -> HitResult:
        now = self._now()
        with self._lock:
            if len(self._hits) > 10_000:  # bound memory: drop expired windows
                self._hits = {k: v for k, v in self._hits.items() if now - v[0] < self.window}
            start, count = self._hits.get(key, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            count += 1
            self._hits[key] = (start, count)
        reset = max(1, math.ceil(start + self.window - now))
        return HitResult(count <= self.limit, self.limit, max(0, self.limit - count), reset)


def client_ip(request: Request, trust_proxy: bool) -> str:
    # Only trust X-Forwarded-For behind a known proxy, else it is trivially spoofed to dodge limits.
    if trust_proxy:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[-1].strip()  # entry appended by our (single) proxy
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self.disabled = settings.RATE_LIMIT_DISABLED
        self.trust_proxy = settings.TRUST_PROXY
        self.global_limiter = FixedWindowLimiter(settings.RATE_LIMIT_MAX, settings.RATE_LIMIT_WINDOW_MS)
        self.write_limiter = FixedWindowLimiter(settings.WRITE_RATE_LIMIT_MAX, settings.WRITE_RATE_LIMIT_WINDOW_MS)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        ip = client_ip(request, self.trust_proxy)
        request.state.client_ip = ip
        path = request.url.path
        if self.disabled or not path.startswith("/api") or path in EXEMPT_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        result = self.global_limiter.hit(ip)
        if result.allowed and request.method in WRITE_METHODS:
            result = self.write_limiter.hit(ip)  # stricter limiter's headers win on writes

        headers = {
            "RateLimit-Limit": str(result.limit),
            "RateLimit-Remaining": str(result.remaining),
            "RateLimit-Reset": str(result.reset_seconds),
        }
        if not result.allowed:
            headers["Retry-After"] = str(result.reset_seconds)
            return error_response(
                429,
                "RATE_LIMITED",
                f"Too many requests, try again in {result.reset_seconds} seconds",
                headers=headers,
            )

        response = await call_next(request)
        response.headers.update(headers)
        return response
