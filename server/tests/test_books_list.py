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


def test_list_filter_each_status(client: TestClient, add_book: AddBook) -> None:
    for status in ("to-read", "reading", "done", "done"):
        add_book(status, status=status)
    for status, expected in (("to-read", 1), ("reading", 1), ("done", 2)):
        data = client.get(URL, params={"status": status}).json()["data"]
        assert len(data) == expected
        assert {b["status"] for b in data} == {status}


def test_list_filter_with_no_matches_returns_empty(client: TestClient, add_book: AddBook) -> None:
    add_book("A", status="reading")
    assert client.get(URL, params={"status": "done"}).json() == {"data": []}


def test_list_rejects_invalid_status_filter(client: TestClient) -> None:
    for bad in ("finished", "", "READING", "' OR 1=1 --"):
        res = client.get(URL, params={"status": bad})
        assert res.status_code == 400, bad
        err = res.json()["error"]
        assert err["code"] == "VALIDATION_ERROR"
        assert err["details"] == [{"path": "status", "message": "Status must be one of: to-read, reading, done"}]


def test_list_ignores_unknown_query_params(client: TestClient, add_book: AddBook) -> None:
    add_book("A")
    assert len(client.get(URL, params={"foo": "bar"}).json()["data"]) == 1
