from __future__ import annotations

import re
import uuid

import pytest
from fastapi.testclient import TestClient

URL = "/api/v1/books"
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def details(res):  # type: ignore[no-untyped-def]
    return {d["path"]: d["message"] for d in res.json()["error"]["details"]}


def test_create_returns_201_with_full_book(client: TestClient) -> None:
    res = client.post(URL, json={"title": "Dune", "author": "Frank Herbert", "status": "reading"})
    assert res.status_code == 201
    book = res.json()["data"]
    assert set(book) == {"id", "title", "author", "status", "createdAt", "updatedAt"}
    assert uuid.UUID(book["id"]).version == 4
    assert book["title"] == "Dune"
    assert book["author"] == "Frank Herbert"
    assert book["status"] == "reading"
    assert ISO.match(book["createdAt"]) and book["createdAt"] == book["updatedAt"]


def test_create_defaults_status_and_author(client: TestClient) -> None:
    book = client.post(URL, json={"title": "Dune"}).json()["data"]
    assert book["status"] == "to-read"
    assert book["author"] == ""


def test_create_trims_and_strips_control_chars(client: TestClient) -> None:
    book = client.post(URL, json={"title": "  Du\u0000ne\n ", "author": " Frank "}).json()["data"]
    assert book["title"] == "Dune"
    assert book["author"] == "Frank"


def test_created_book_is_persisted(client: TestClient) -> None:
    created = client.post(URL, json={"title": "Dune"}).json()["data"]
    assert client.get(URL).json()["data"] == [created]


@pytest.mark.parametrize(
    "payload",
    [{}, {"title": ""}, {"title": "   "}, {"title": None}, {"author": "x"}],
    ids=["missing", "empty", "whitespace", "null", "author-only"],
)
def test_create_requires_title(client: TestClient, payload: dict) -> None:  # type: ignore[type-arg]
    res = client.post(URL, json=payload)
    assert res.status_code == 400
    body = res.json()["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "Invalid request body"
    assert details(res)["title"] == "Title is required"


def test_create_rejects_title_over_200_chars(client: TestClient) -> None:
    res = client.post(URL, json={"title": "x" * 201})
    assert res.status_code == 400
    assert details(res)["title"] == "Title must be at most 200 characters"
    assert client.post(URL, json={"title": "x" * 200}).status_code == 201


def test_create_rejects_non_string_title(client: TestClient) -> None:
    res = client.post(URL, json={"title": 123})
    assert res.status_code == 400
    assert details(res)["title"] == "Title must be a string"


def test_create_rejects_author_over_200_chars(client: TestClient) -> None:
    res = client.post(URL, json={"title": "ok", "author": "a" * 201})
    assert res.status_code == 400
    assert "author" in details(res)


@pytest.mark.parametrize("status", ["finished", "TO-READ", "", 1, None])
def test_create_rejects_invalid_status(client: TestClient, status: object) -> None:
    res = client.post(URL, json={"title": "Dune", "status": status})
    assert res.status_code == 400
    assert details(res)["status"] == "Status must be one of: to-read, reading, done"


def test_create_reports_all_field_errors_at_once(client: TestClient) -> None:
    res = client.post(URL, json={"title": "   ", "status": "finished"})
    assert res.status_code == 400
    assert details(res) == {
        "title": "Title is required",
        "status": "Status must be one of: to-read, reading, done",
    }


def test_create_rejects_unknown_fields(client: TestClient) -> None:
    # mass-assignment protection: client cannot set id/createdAt
    res = client.post(URL, json={"title": "Dune", "id": "hacked", "createdAt": "1970"})
    assert res.status_code == 400
    assert details(res) == {"id": "Unknown field", "createdAt": "Unknown field"}


def test_create_rejects_malformed_json(client: TestClient) -> None:
    res = client.post(URL, content=b'{"title": "Dune"', headers={"Content-Type": "application/json"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert res.json()["error"]["message"] == "Malformed JSON"


@pytest.mark.parametrize("raw", [b'"Dune"', b"[1,2]", b"null"])
def test_create_rejects_non_object_json(client: TestClient, raw: bytes) -> None:
    res = client.post(URL, content=raw, headers={"Content-Type": "application/json"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_rejects_non_json_content_type(client: TestClient) -> None:
    res = client.post(URL, content=b"title=Dune", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert res.status_code == 415
    assert res.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_create_accepts_json_with_charset(client: TestClient) -> None:
    res = client.post(URL, content=b'{"title":"Dune"}', headers={"Content-Type": "application/json; charset=utf-8"})
    assert res.status_code == 201
