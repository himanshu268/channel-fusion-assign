from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

URL = "/api/v1/books"
AddBook = Callable[..., dict[str, Any]]


def test_list_empty(client: TestClient) -> None:
    res = client.get(URL)
    assert res.status_code == 200
    assert res.json() == {"data": []}


def test_list_returns_all_newest_first(client: TestClient, add_book: AddBook) -> None:
    a = add_book("A")
    b = add_book("B", status="done")
    c = add_book("C", status="reading")
    data = client.get(URL).json()["data"]
    assert [x["id"] for x in data] == [c["id"], b["id"], a["id"]]


def test_list_filters_by_status(client: TestClient, add_book: AddBook) -> None:
    add_book("A", status="reading")
    add_book("B", status="done")
    add_book("C", status="reading")
    res = client.get(f"{URL}?status=reading")
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) == 2
    assert all(b["status"] == "reading" for b in data)
