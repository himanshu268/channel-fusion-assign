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
