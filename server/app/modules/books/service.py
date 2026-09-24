from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.core.errors import HttpError

from .repository import BookRepository
from .schemas import BOOK_STATUSES, Book, BookStats, BookStatus, CreateBookIn

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _is_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value.lower()
    except ValueError:
        return False


class BookService:
    def __init__(self, repo: BookRepository, clock: Clock = utc_now) -> None:
        self._repo = repo
        self._clock = clock

    def create(self, data: CreateBookIn) -> Book:
        now = iso(self._clock())
        book: Book = {
            "id": str(uuid.uuid4()),  # server-generated id; client cannot choose (OWASP A04)
            "title": data.title,
            "author": data.author,
            "status": data.status,
            "createdAt": now,
            "updatedAt": now,
        }
        return self._repo.insert(book)

    def list(self, status: BookStatus | None = None) -> list[Book]:
        return self._repo.find_all(status)

    def update_status(self, book_id: str, status: BookStatus) -> Book:
        if not _is_uuid(book_id):
            raise HttpError(404, "NOT_FOUND", "Book not found")
        book = self._repo.update_status(book_id.lower(), status, iso(self._clock()))
        if book is None:
            raise HttpError(404, "NOT_FOUND", "Book not found")
        return book

    def stats(self) -> BookStats:
        counts = self._repo.count_by_status()
        stats: BookStats = {"to-read": 0, "reading": 0, "done": 0, "total": 0}
        for s in BOOK_STATUSES:
            stats[s] = counts.get(s, 0)  # type: ignore[literal-required]
        stats["total"] = sum(counts.values())
        return stats
