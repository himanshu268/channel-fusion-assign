"""SQLite repository. Parameterised SQL only - never interpolate values (OWASP A03)."""

from __future__ import annotations

import sqlite3
import threading
from typing import Protocol

from .schemas import Book, BookStatus


class BookRepository(Protocol):
    def insert(self, book: Book) -> Book: ...
    def find_all(self, status: BookStatus | None = None) -> list[Book]: ...
    def find_by_id(self, book_id: str) -> Book | None: ...
    def update_status(self, book_id: str, status: BookStatus, updated_at: str) -> Book | None: ...
    def count_by_status(self) -> dict[BookStatus, int]: ...


def _row_to_book(row: sqlite3.Row) -> Book:
    return {
        "id": row["id"],
        "title": row["title"],
        "author": row["author"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


class SqliteBookRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()  # one shared connection across FastAPI's threadpool

    def insert(self, book: Book) -> Book:
        with self._lock:
            self._conn.execute(
                "INSERT INTO books (id, title, author, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (book["id"], book["title"], book["author"], book["status"], book["createdAt"], book["updatedAt"]),
            )
        return book

    def find_all(self, status: BookStatus | None = None) -> list[Book]:
        # rowid tie-break keeps order stable when two rows share a millisecond
        sql = "SELECT * FROM books"
        params: tuple[str, ...] = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY created_at DESC, rowid DESC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_book(r) for r in rows]

    def find_by_id(self, book_id: str) -> Book | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return _row_to_book(row) if row else None

    def update_status(self, book_id: str, status: BookStatus, updated_at: str) -> Book | None:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE books SET status = ?, updated_at = ? WHERE id = ?", (status, updated_at, book_id)
            )
            if cur.rowcount == 0:
                return None
            row = self._conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return _row_to_book(row)

    def count_by_status(self) -> dict[BookStatus, int]:
        with self._lock:
            rows = self._conn.execute("SELECT status, COUNT(*) AS n FROM books GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}
