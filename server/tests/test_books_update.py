from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

AddBook = Callable[..., dict[str, Any]]


def url(book_id: str) -> str:
    return f"/api/v1/books/{book_id}"


def test_update_status_changes_status_and_bumps_updated_at(client: TestClient, add_book: AddBook) -> None:
    book = add_book("Dune")
    res = client.patch(url(book["id"]), json={"status": "reading"})
    assert res.status_code == 200
    updated = res.json()["data"]
    assert updated["status"] == "reading"
    assert updated["id"] == book["id"]
    assert updated["title"] == book["title"]
    assert updated["createdAt"] == book["createdAt"]
    assert updated["updatedAt"] > book["updatedAt"]
    assert client.get("/api/v1/books", params={"status": "reading"}).json()["data"] == [updated]


def test_update_unknown_id_returns_404(client: TestClient) -> None:
    res = client.patch(url(str(uuid.uuid4())), json={"status": "done"})
    assert res.status_code == 404
    assert res.json() == {"error": {"code": "NOT_FOUND", "message": "Book not found"}}


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "1", "stats-x", "' OR 1=1 --"])
def test_update_malformed_id_returns_404(client: TestClient, bad_id: str) -> None:
    res = client.patch(url(bad_id), json={"status": "done"})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_update_rejects_invalid_status(client: TestClient, add_book: AddBook) -> None:
    book = add_book()
    res = client.patch(url(book["id"]), json={"status": "finished"})
    assert res.status_code == 400
    assert res.json()["error"]["details"] == [
        {"path": "status", "message": "Status must be one of: to-read, reading, done"}
    ]


def test_update_requires_status(client: TestClient, add_book: AddBook) -> None:
    book = add_book()
    res = client.patch(url(book["id"]), json={})
    assert res.status_code == 400
    assert res.json()["error"]["details"] == [{"path": "status", "message": "Status is required"}]


def test_update_rejects_other_fields(client: TestClient, add_book: AddBook) -> None:
    book = add_book()
    res = client.patch(url(book["id"]), json={"status": "done", "title": "changed"})
    assert res.status_code == 400
    assert client.get("/api/v1/books").json()["data"][0]["title"] == book["title"]


def test_update_without_body_returns_400(client: TestClient, add_book: AddBook) -> None:
    book = add_book()
    res = client.patch(url(book["id"]))
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
