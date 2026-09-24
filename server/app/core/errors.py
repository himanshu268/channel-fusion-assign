"""Error type + envelope helpers shared by handlers and middleware."""

from __future__ import annotations

from typing import Any, Literal

from fastapi.responses import JSONResponse

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "NOT_FOUND",
    "UNSUPPORTED_MEDIA_TYPE",
    "PAYLOAD_TOO_LARGE",
    "RATE_LIMITED",
    "INTERNAL_ERROR",
]


class HttpError(Exception):
    def __init__(
        self,
        status: int,
        code: ErrorCode,
        message: str,
        details: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def error_body(code: ErrorCode, message: str, details: list[dict[str, str]] | None = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def error_response(
    status: int,
    code: ErrorCode,
    message: str,
    details: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(error_body(code, message, details), status_code=status, headers=headers)
