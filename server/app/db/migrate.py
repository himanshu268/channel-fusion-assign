from __future__ import annotations

import sqlite3

# DB-level CHECK constraints are defence in depth behind Pydantic validation.
SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
  id          TEXT PRIMARY KEY,
  title       TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
  author      TEXT NOT NULL DEFAULT '' CHECK (length(author) <= 200),
  status      TEXT NOT NULL CHECK (status IN ('to-read','reading','done')),
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_books_status ON books(status);
CREATE INDEX IF NOT EXISTS idx_books_created_at ON books(created_at DESC);
"""


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
