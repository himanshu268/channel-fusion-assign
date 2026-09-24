from __future__ import annotations

import sqlite3
from pathlib import Path


def open_db(path: str) -> sqlite3.Connection:
    """Open SQLite. ':memory:' for tests. One shared connection; repository serialises access."""
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
