"""Request schemas + contract types (see TECHNICAL_SPEC.md section 2.2)."""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

BookStatus = Literal["to-read", "reading", "done"]
BOOK_STATUSES: tuple[str, ...] = get_args(BookStatus)
STATUS_MESSAGE = f"Status must be one of: {', '.join(BOOK_STATUSES)}"
MAX_LEN = 200

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class Book(TypedDict):
    id: str
    title: str
    author: str
    status: BookStatus
    createdAt: str
    updatedAt: str


BookStats = TypedDict("BookStats", {"to-read": int, "reading": int, "done": int, "total": int})


def _clean(value: str) -> str:
    return _CONTROL_CHARS.sub("", value).strip()


def parse_status(value: Any) -> BookStatus:
    if not isinstance(value, str) or value not in BOOK_STATUSES:
        raise PydanticCustomError("invalid_status", STATUS_MESSAGE)
    return value  # type: ignore[return-value]


class CreateBookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # default None + validate_default so a missing title hits our validator and custom message
    title: str = Field(default=None, validate_default=True)
    author: str = ""
    status: BookStatus = "to-read"

    @field_validator("title", mode="before")
    @classmethod
    def _title(cls, v: Any) -> str:
        if v is None:
            raise PydanticCustomError("title_required", "Title is required")
        if not isinstance(v, str):
            raise PydanticCustomError("title_type", "Title must be a string")
        title = _clean(v)
        if not title:
            raise PydanticCustomError("title_required", "Title is required")
        if len(title) > MAX_LEN:
            raise PydanticCustomError("title_length", f"Title must be at most {MAX_LEN} characters")
        return title

    @field_validator("author", mode="before")
    @classmethod
    def _author(cls, v: Any) -> str:
        if v is None:
            return ""
        if not isinstance(v, str):
            raise PydanticCustomError("author_type", "Author must be a string")
        author = _clean(v)
        if len(author) > MAX_LEN:
            raise PydanticCustomError("author_length", f"Author must be at most {MAX_LEN} characters")
        return author

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: Any) -> BookStatus:
        return parse_status(v)


class UpdateStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: BookStatus = Field(default=None, validate_default=True)

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: Any) -> BookStatus:
        if v is None:
            raise PydanticCustomError("status_required", "Status is required")
        return parse_status(v)
