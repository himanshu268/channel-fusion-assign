"""Validation edge cases beyond the happy-path create/update suites: boundaries, types, unicode, media types."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

URL = "/api/v1/books"
AddBook = Callable[..., dict[str, Any]]
STATUS_MSG = "Status must be one of: to-read, reading, done"
JSON = {"Content-Type": "application/json"}


def details(res):  # type: ignore[no-untyped-def]
    return {d["path"]: d["message"] for d in res.json()["error"]["details"]}


# ---- create: title / author boundaries ----


@pytest.mark.parametrize("n", [1, 199, 200])
def test_title_length_within_bounds_accepted(client: TestClient, n: int) -> None:
    res = client.post(URL, json={"title": "t" * n})
    assert res.status_code == 201
    assert len(res.json()["data"]["title"]) == n


def test_title_length_measured_after_trim(client: TestClient) -> None:
    res = client.post(URL, json={"title": "  " + "t" * 200 + "  "})
    assert res.status_code == 201
    assert res.json()["data"]["title"] == "t" * 200


def test_title_length_counts_characters_not_bytes(client: TestClient) -> None:
    assert client.post(URL, json={"title": "\U0001f600" * 200}).status_code == 201
    res = client.post(URL, json={"title": "\U0001f600" * 201})
    assert res.status_code == 400
    assert details(res)["title"] == "Title must be at most 200 characters"


@pytest.mark.parametrize("n", [0, 200])
def test_author_length_within_bounds_accepted(client: TestClient, n: int) -> None:
    res = client.post(URL, json={"title": "ok", "author": "a" * n})
    assert res.status_code == 201
    assert res.json()["data"]["author"] == "a" * n


def test_author_over_200_has_exact_message(client: TestClient) -> None:
    res = client.post(URL, json={"title": "ok", "author": "a" * 201})
    assert details(res) == {"author": "Author must be at most 200 characters"}


def test_author_whitespace_only_becomes_empty(client: TestClient) -> None:
    res = client.post(URL, json={"title": "ok", "author": "   \t "})
    assert res.status_code == 201
    assert res.json()["data"]["author"] == ""


@pytest.mark.parametrize(
    "title", [chr(0xA0), "\t\n\r", "\x00\x01", " " + chr(0x3000) + " "], ids=["nbsp", "ws", "ctrl", "ideo"]
)
def test_title_blank_after_cleaning_is_required(client: TestClient, title: str) -> None:
    res = client.post(URL, json={"title": title})
    assert res.status_code == 400
    assert details(res)["title"] == "Title is required"


# ---- create: wrong JSON types ----


@pytest.mark.parametrize(
    "value", [True, 0, 1.5, [], {}, ["Dune"]], ids=["bool", "int", "float", "list", "obj", "list-str"]
)
def test_title_wrong_type(client: TestClient, value: object) -> None:
    res = client.post(URL, json={"title": value})
    assert res.status_code == 400
    assert details(res)["title"] == "Title must be a string"


@pytest.mark.parametrize("value", [5, False, [], {}], ids=["int", "bool", "list", "obj"])
def test_author_wrong_type(client: TestClient, value: object) -> None:
    res = client.post(URL, json={"title": "ok", "author": value})
    assert res.status_code == 400
    assert details(res)["author"] == "Author must be a string"


@pytest.mark.parametrize("status", [["done"], {"v": "done"}, True, " reading", "reading ", "Reading", "to_read"])
def test_status_must_match_literal_exactly(client: TestClient, status: object) -> None:
    res = client.post(URL, json={"title": "ok", "status": status})
    assert res.status_code == 400
    assert details(res)["status"] == STATUS_MSG


@pytest.mark.parametrize("status", ["to-read", "reading", "done"])
def test_each_valid_status_accepted_on_create(client: TestClient, status: str) -> None:
    res = client.post(URL, json={"title": "ok", "status": status})
    assert res.status_code == 201
    assert res.json()["data"]["status"] == status


def test_nan_title_rejected(client: TestClient) -> None:
    res = client.post(URL, content=b'{"title": NaN}', headers=JSON)
    assert res.status_code == 400


def test_unknown_field_rejected_even_when_otherwise_valid(client: TestClient) -> None:
    res = client.post(URL, json={"title": "ok", "updatedAt": "x", "status": "done"})
    assert res.status_code == 400
    assert details(res) == {"updatedAt": "Unknown field"}
    assert client.get(URL).json()["data"] == []  # nothing persisted on failure


def test_failed_validation_persists_nothing(client: TestClient) -> None:
    client.post(URL, json={"title": ""})
    client.post(URL, json={"title": "ok", "status": "nope"})
    assert client.get(f"{URL}/stats").json()["data"]["total"] == 0


# ---- create: body presence / media type ----


def test_post_without_body_returns_body_required(client: TestClient) -> None:
    res = client.post(URL)
    assert res.status_code == 400
    assert res.json()["error"]["details"] == [{"path": "", "message": "Request body is required"}]


def test_post_empty_json_body_returns_body_required(client: TestClient) -> None:
    res = client.post(URL, content=b"", headers=JSON)
    assert res.status_code == 400
    assert details(res) == {"": "Request body is required"}


@pytest.mark.parametrize("raw", [b'"Dune"', b"[1,2]", b"null", b"42"])
def test_non_object_json_message(client: TestClient, raw: bytes) -> None:
    res = client.post(URL, content=raw, headers=JSON)
    assert res.status_code == 400
    assert res.json()["error"]["details"][0]["path"] == ""


@pytest.mark.parametrize(
    "ctype",
    ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data", "application/merge-patch+json", ""],
)
def test_non_json_content_types_rejected_415(client: TestClient, ctype: str) -> None:
    res = client.post(URL, content=b'{"title":"x"}', headers={"Content-Type": ctype})
    assert res.status_code == 415
    assert res.json() == {
        "error": {"code": "UNSUPPORTED_MEDIA_TYPE", "message": "Content-Type must be application/json"}
    }
    assert client.get(URL).json()["data"] == []


def test_content_type_is_case_insensitive(client: TestClient) -> None:
    res = client.post(URL, content=b'{"title":"x"}', headers={"Content-Type": "Application/JSON"})
    assert res.status_code == 201


def test_malformed_json_on_patch(client: TestClient, add_book: AddBook) -> None:
    book = add_book()
    res = client.patch(f"{URL}/{book['id']}", content=b'{"status":', headers=JSON)
    assert res.status_code == 400
    assert res.json()["error"]["message"] == "Malformed JSON"


def test_patch_non_json_content_type_rejected_415(client: TestClient, add_book: AddBook) -> None:
    book = add_book()
    res = client.patch(f"{URL}/{book['id']}", content=b"status=done", headers={"Content-Type": "text/plain"})
    assert res.status_code == 415
    assert client.get(URL).json()["data"][0]["status"] == "to-read"


# ---- body size boundary ----


def _body_of_size(n: int) -> bytes:
    # padding goes into author, which is then rejected by length validation (400), not by size (413)
    skeleton = json.dumps({"title": "x", "author": ""}).encode()
    pad = n - len(skeleton)
    return json.dumps({"title": "x", "author": "a" * pad}).encode()


def test_body_exactly_at_limit_passes_size_guard(client: TestClient) -> None:
    body = _body_of_size(10 * 1024)
    assert len(body) == 10 * 1024
    res = client.post(URL, content=body, headers=JSON)
    assert res.status_code == 400  # reached validation, i.e. not blocked by size guard


def test_body_one_byte_over_limit_is_413(client: TestClient) -> None:
    body = _body_of_size(10 * 1024 + 1)
    res = client.post(URL, content=body, headers=JSON)
    assert res.status_code == 413
    assert res.json() == {"error": {"code": "PAYLOAD_TOO_LARGE", "message": "Request body must be at most 10240 bytes"}}


def test_body_limit_is_configurable(client_factory: Callable[..., TestClient]) -> None:
    with client_factory(JSON_BODY_LIMIT="64") as c:
        assert c.post(URL, json={"title": "x" * 80}).status_code == 413
        assert c.post(URL, json={"title": "short"}).status_code == 201


def test_oversized_patch_is_413(client: TestClient, add_book: AddBook) -> None:
    book = add_book()
    res = client.patch(f"{URL}/{book['id']}", json={"status": "done", "pad": "x" * 11_000})
    assert res.status_code == 413


# ---- list query ----


def test_list_filter_preserves_newest_first(client: TestClient, add_book: AddBook) -> None:
    a = add_book("A", status="done")
    add_book("B", status="reading")
    c = add_book("C", status="done")
    data = client.get(URL, params={"status": "done"}).json()["data"]
    assert [b["id"] for b in data] == [c["id"], a["id"]]


def test_list_items_have_exact_book_shape(client: TestClient, add_book: AddBook) -> None:
    add_book("A", author="X", status="reading")
    for item in client.get(URL).json()["data"]:
        assert set(item) == {"id", "title", "author", "status", "createdAt", "updatedAt"}


@pytest.mark.parametrize("bad", ["%00", "reading%00", "reading;done", "*", "1"])
def test_list_rejects_tricky_status_values(client: TestClient, bad: str) -> None:
    res = client.get(f"{URL}?status={bad}")
    assert res.status_code == 400
    assert res.json()["error"]["message"] == "Invalid query parameters"


# ---- patch ----


@pytest.mark.parametrize("status", ["to-read", "reading", "done"])
def test_patch_to_each_status(client: TestClient, add_book: AddBook, status: str) -> None:
    book = add_book(status="reading" if status != "reading" else "done")
    res = client.patch(f"{URL}/{book['id']}", json={"status": status})
    assert res.status_code == 200
    assert res.json()["data"]["status"] == status


def test_patch_same_status_is_ok(client: TestClient, add_book: AddBook) -> None:
    book = add_book(status="done")
    res = client.patch(f"{URL}/{book['id']}", json={"status": "done"})
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "done"


def test_patch_accepts_uppercase_uuid(client: TestClient, add_book: AddBook) -> None:
    book = add_book()
    res = client.patch(f"{URL}/{book['id'].upper()}", json={"status": "done"})
    assert res.status_code == 200
    assert res.json()["data"]["id"] == book["id"]


@pytest.mark.parametrize("fmt", ["braces", "hex", "urn"])
def test_patch_non_canonical_uuid_forms_are_404(client: TestClient, add_book: AddBook, fmt: str) -> None:
    bid = add_book()["id"]
    bad = {"braces": f"{{{bid}}}", "hex": bid.replace("-", ""), "urn": f"urn:uuid:{bid}"}[fmt]
    res = client.patch(f"{URL}/{bad}", json={"status": "done"})
    assert res.status_code == 404
    assert res.json() == {"error": {"code": "NOT_FOUND", "message": "Book not found"}}


def test_patch_stats_path_is_not_a_book(client: TestClient) -> None:
    res = client.patch(f"{URL}/stats", json={"status": "done"})
    assert res.status_code == 404


@pytest.mark.parametrize("value", [None, "", 1, ["done"], "DONE"])
def test_patch_invalid_status_values(client: TestClient, add_book: AddBook, value: object) -> None:
    book = add_book()
    res = client.patch(f"{URL}/{book['id']}", json={"status": value})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get(URL).json()["data"][0]["status"] == "to-read"  # unchanged


def test_patch_rejected_does_not_bump_updated_at(client: TestClient, add_book: AddBook) -> None:
    book = add_book()
    client.patch(f"{URL}/{book['id']}", json={"status": "nope"})
    assert client.get(URL).json()["data"][0]["updatedAt"] == book["updatedAt"]


def test_patch_unknown_uuid_does_not_create(client: TestClient) -> None:
    client.patch(f"{URL}/{uuid.uuid4()}", json={"status": "done"})
    assert client.get(f"{URL}/stats").json()["data"]["total"] == 0


# ---- unicode hardening (regressions for BUG-01 / BUG-02) ----

INVISIBLE = {  # built with chr() so formatters never turn escapes into literal invisible chars
    "nel": chr(0x85),
    "csi": chr(0x9B),
    "line-sep": chr(0x2028),
    "para-sep": chr(0x2029),
    "zwsp": chr(0x200B),
    "lrm": chr(0x200E),
    "rlo": chr(0x202E),
    "lri": chr(0x2066),
    "bom": chr(0xFEFF),
}


@pytest.mark.parametrize("ch", INVISIBLE.values(), ids=INVISIBLE.keys())
def test_unicode_control_and_invisible_chars_stripped(client: TestClient, ch: str) -> None:
    res = client.post(URL, json={"title": f"Du{ch}ne", "author": f"A{ch}B"})
    assert res.status_code == 201
    assert res.json()["data"]["title"] == "Dune"
    assert res.json()["data"]["author"] == "AB"


@pytest.mark.parametrize(
    "title",
    [chr(0x200B), chr(0x200B) + chr(0x200C) + chr(0x200D), chr(0xFEFF), chr(0x202E), " " + chr(0x200D) + " "],
    ids=["zwsp", "zw-mix", "bom", "rlo", "lone-zwj"],
)
def test_invisible_only_title_is_required(client: TestClient, title: str) -> None:
    res = client.post(URL, json={"title": title})
    assert res.status_code == 400
    assert details(res)["title"] == "Title is required"


def test_invisible_only_author_becomes_empty(client: TestClient) -> None:
    res = client.post(URL, json={"title": "ok", "author": chr(0x200B) + chr(0x200D)})
    assert res.status_code == 201
    assert res.json()["data"]["author"] == ""


def test_zwj_inside_text_is_preserved(client: TestClient) -> None:
    family = chr(0x1F468) + chr(0x200D) + chr(0x1F469) + chr(0x200D) + chr(0x1F467)  # one emoji glyph
    res = client.post(URL, json={"title": family})
    assert res.status_code == 201
    assert res.json()["data"]["title"] == family


def test_non_latin_titles_accepted(client: TestClient) -> None:
    for title in ("\u0926\u094d\u200d\u0935", "\u0645\u0631\u062d\u0628\u0627", "\u6771\u4eac"):
        assert client.post(URL, json={"title": title}).status_code == 201


# ---- repeated ?status= (regression for BUG-03) ----


@pytest.mark.parametrize("qs", ["status=zzz&status=reading", "status=reading&status=zzz"])
def test_list_rejects_repeated_status_with_any_invalid_value(client: TestClient, qs: str) -> None:
    res = client.get(f"{URL}?{qs}")
    assert res.status_code == 400
    assert res.json()["error"]["details"] == [{"path": "status", "message": STATUS_MSG}]


def test_list_rejects_conflicting_repeated_status(client: TestClient) -> None:
    res = client.get(f"{URL}?status=reading&status=done")
    assert res.status_code == 400
    assert res.json()["error"]["details"] == [{"path": "status", "message": "Status must be given once"}]


def test_list_allows_same_status_repeated(client: TestClient, add_book: AddBook) -> None:
    add_book(status="done")
    add_book(status="reading")
    data = client.get(f"{URL}?status=done&status=done").json()["data"]
    assert [b["status"] for b in data] == ["done"]
