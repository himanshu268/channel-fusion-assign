from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

URL = "/api/v1/books/stats"


def test_stats_all_zero_when_empty(client: TestClient) -> None:
    res = client.get(URL)
    assert res.status_code == 200
    assert res.json() == {"data": {"to-read": 0, "reading": 0, "done": 0, "total": 0}}


def test_stats_counts_by_status(client: TestClient, add_book: Callable[..., dict[str, Any]]) -> None:
    for s in ("to-read", "to-read", "to-read", "reading", "done", "done"):
        add_book(s, status=s)
    assert client.get(URL).json()["data"] == {"to-read": 3, "reading": 1, "done": 2, "total": 6}


def test_stats_keys_always_present(client: TestClient, add_book: Callable[..., dict[str, Any]]) -> None:
    add_book("A", status="done")
    assert client.get(URL).json()["data"] == {"to-read": 0, "reading": 0, "done": 1, "total": 1}


def test_stats_reflects_status_change(client: TestClient, add_book: Callable[..., dict[str, Any]]) -> None:
    book = add_book("A")
    client.patch(f"/api/v1/books/{book['id']}", json={"status": "done"})
    assert client.get(URL).json()["data"] == {"to-read": 0, "reading": 0, "done": 1, "total": 1}
