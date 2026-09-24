"""App factory. No server start here, so tests build the app in-process."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app.core.config import Settings
from app.core.errors import HttpError, error_response
from app.core.logging import configure_logging
from app.db.connection import open_db
from app.db.migrate import migrate
from app.middleware.body_guard import BodyGuardMiddleware
from app.middleware.core import CoreMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.modules.books.repository import SqliteBookRepository
from app.modules.books.router import router as books_router
from app.modules.books.service import BookService, Clock, utc_now

API_PREFIX = "/api/v1"


def _validation_details(exc: RequestValidationError) -> tuple[str, list[dict[str, str]]]:
    message = "Invalid request body"
    details: list[dict[str, str]] = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p != "body"]
        path = ".".join(loc)
        kind = err.get("type", "")
        if kind == "json_invalid":
            message, msg = "Malformed JSON", "Malformed JSON"
        elif kind == "extra_forbidden":
            msg = "Unknown field"
        elif kind == "missing" and not path:
            msg = "Request body is required"
        elif kind in ("model_attributes_type", "dict_type") and not path:
            msg = "Request body must be a JSON object"
        else:
            msg = str(err.get("msg", "Invalid value"))
        details.append({"path": path, "message": msg})
    return message, details


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HttpError)
    async def _http_error(_: Request, exc: HttpError) -> Response:
        return error_response(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> Response:
        message, details = _validation_details(exc)
        return error_response(400, "VALIDATION_ERROR", message, details)

    @app.exception_handler(StarletteHTTPException)
    async def _starlette_error(_: Request, exc: StarletteHTTPException) -> Response:
        # 404 and 405 both mean "no such route" for this API - JSON envelope, never HTML.
        if exc.status_code in (404, 405):
            return error_response(404, "NOT_FOUND", "Route not found")
        if exc.status_code == 400:
            return error_response(400, "VALIDATION_ERROR", "Malformed request")
        return error_response(500, "INTERNAL_ERROR", "Something went wrong")


def create_app(
    settings: Settings | None = None,
    conn: sqlite3.Connection | None = None,
    clock: Clock = utc_now,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.LOG_LEVEL)
    conn = conn or open_db(settings.DB_PATH)
    migrate(conn)

    docs = not settings.is_production  # no public schema/docs in prod (OWASP A05)
    app = FastAPI(
        title="Books API",
        version="1.0.0",
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.settings = settings
    app.state.book_service = BookService(SqliteBookRepository(conn), clock)

    register_error_handlers(app)

    @app.api_route(f"{API_PREFIX}/health", methods=["GET", "HEAD"], tags=["health"])
    def health() -> dict[str, Any]:
        return {"data": {"status": "ok"}}

    app.include_router(books_router, prefix=API_PREFIX)

    # add_middleware: last added = outermost. Effective order (outer -> inner):
    # Core -> CORS -> RateLimit -> BodyGuard -> routes
    app.add_middleware(BodyGuardMiddleware, limit=settings.body_limit_bytes)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-Request-Id"],
        expose_headers=["RateLimit-Limit", "RateLimit-Remaining", "RateLimit-Reset", "Retry-After", "X-Request-Id"],
        allow_credentials=False,
        max_age=600,
    )
    app.add_middleware(CoreMiddleware)
    return app
