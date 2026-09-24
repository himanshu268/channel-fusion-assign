"""Contract envelope on every path, routing corners, rate-limit interplay, config fail-fast, concurrency."""

from __future__ import annotations

import re
import threading
import uuid
import warnings
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings

URL = "/api/v1/books"
ClientFactory = Callable[..., TestClient]
AddBook = Callable[..., dict[str, Any]]
ERROR_CODES = {
    "VALIDATION_ERROR",
    "NOT_FOUND",
    "UNSUPPORTED_MEDIA_TYPE",
    "PAYLOAD_TOO_LARGE",
    "RATE_LIMITED",
    "INTERNAL_ERROR",
}


def assert_error_envelope(res: Any, status: int, code: str) -> None:
    assert res.status_code == status
    assert res.headers["content-type"].startswith("application/json")
    body = res.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert code in ERROR_CODES
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert set(body["error"]) <= {"code", "message", "details"}
    if code != "VALIDATION_ERROR":
        assert "details" not in body["error"]


# ---- envelope on every endpoint / error kind ----


@pytest.mark.parametrize(
    ("method", "path", "kwargs", "status", "code"),
    [
        ("post", URL, {"json": {"title": ""}}, 400, "VALIDATION_ERROR"),
        ("get", f"{URL}?status=x", {}, 400, "VALIDATION_ERROR"),
        ("patch", f"{URL}/{uuid.uuid4()}", {"json": {"status": "done"}}, 404, "NOT_FOUND"),
        ("post", URL, {"content": b"x", "headers": {"Content-Type": "text/plain"}}, 415, "UNSUPPORTED_MEDIA_TYPE"),
        ("post", URL, {"json": {"title": "x" * 20_000}}, 413, "PAYLOAD_TOO_LARGE"),
        ("get", f"{URL}/{uuid.uuid4()}", {}, 404, "NOT_FOUND"),
        ("put", URL, {"json": {}}, 404, "NOT_FOUND"),
        ("delete", f"{URL}/{uuid.uuid4()}", {}, 404, "NOT_FOUND"),
        ("get", "/api/v2/books", {}, 404, "NOT_FOUND"),
    ],
)
def test_error_envelope_shape(
    client: TestClient, method: str, path: str, kwargs: dict[str, Any], status: int, code: str
) -> None:
    res = getattr(client, method)(path, **kwargs)
    assert_error_envelope(res, status, code)
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-request-id"]


def test_success_envelopes(client: TestClient, add_book: AddBook) -> None:
    book = add_book()
    for res in (
        client.get("/api/v1/health"),
        client.get(URL),
        client.get(f"{URL}/stats"),
        client.patch(f"{URL}/{book['id']}", json={"status": "done"}),
    ):
        assert res.status_code == 200
        assert set(res.json()) == {"data"}
        assert res.headers["cache-control"] == "no-store"


def test_timestamps_are_utc_iso_and_ordered(client: TestClient, add_book: AddBook) -> None:
    book = add_book()
    updated = client.patch(f"{URL}/{book['id']}", json={"status": "done"}).json()["data"]
    for ts in (updated["createdAt"], updated["updatedAt"]):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", ts)
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert updated["updatedAt"] > updated["createdAt"]


def test_ids_are_unique_uuid4(client: TestClient, add_book: AddBook) -> None:
    ids = {add_book(str(i))["id"] for i in range(20)}
    assert len(ids) == 20
    assert all(uuid.UUID(i).version == 4 for i in ids)


def test_stats_total_equals_sum_and_list_length(client: TestClient, add_book: AddBook) -> None:
    for s in ("to-read", "reading", "reading", "done"):
        add_book(status=s)
    stats = client.get(f"{URL}/stats").json()["data"]
    assert stats["total"] == stats["to-read"] + stats["reading"] + stats["done"] == len(client.get(URL).json()["data"])
    for s in ("to-read", "reading", "done"):
        assert stats[s] == len(client.get(URL, params={"status": s}).json()["data"])


def test_stats_ignores_query_params(client: TestClient) -> None:
    assert client.get(f"{URL}/stats?status=done&x=1").status_code == 200


def test_request_id_length_boundary(client: TestClient) -> None:
    assert client.get("/api/v1/health", headers={"X-Request-Id": "a" * 64}).headers["x-request-id"] == "a" * 64
    replaced = client.get("/api/v1/health", headers={"X-Request-Id": "a" * 65}).headers["x-request-id"]
    assert replaced != "a" * 65 and len(replaced) == 36


def test_request_id_on_every_error(client: TestClient) -> None:
    res = client.post(URL, content=b"x", headers={"Content-Type": "text/plain", "X-Request-Id": "trace-1"})
    assert res.headers["x-request-id"] == "trace-1"


def test_internal_error_on_write_hides_details(client: TestClient) -> None:
    def boom(*_: Any) -> None:
        raise RuntimeError("sqlite3.OperationalError: /var/data/books.db locked")

    client.app.state.book_service.create = boom  # type: ignore[attr-defined]
    res = client.post(URL, json={"title": "x"})
    assert_error_envelope(res, 500, "INTERNAL_ERROR")
    assert "sqlite" not in res.text and "/var" not in res.text


@pytest.mark.parametrize(
    ("method", "path"), [("get", f"{URL}/"), ("get", f"{URL}/stats/"), ("post", f"{URL}/"), ("get", "/api/v1/health/")]
)
def test_trailing_slash_is_json_404_not_redirect(client: TestClient, method: str, path: str) -> None:
    kwargs: dict[str, Any] = {"json": {"title": "x"}} if method == "post" else {}
    res = getattr(client, method)(path, follow_redirects=False, **kwargs)
    assert "location" not in res.headers
    assert_error_envelope(res, 404, "NOT_FOUND")


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        ({"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}, "Disallowed CORS origin"),
        ({"Origin": "http://localhost:5173", "Access-Control-Request-Method": "DELETE"}, "Disallowed CORS method"),
        (
            {"Origin": "https://evil.example", "Access-Control-Request-Method": "PUT"},
            "Disallowed CORS origin, method",
        ),
    ],
)
def test_rejected_preflight_is_json(client: TestClient, headers: dict[str, str], message: str) -> None:
    res = client.options(URL, headers=headers)
    assert_error_envelope(res, 400, "VALIDATION_ERROR")
    assert res.json()["error"]["message"] == message
    assert res.headers["x-content-type-options"] == "nosniff"
    if "origin" in message:
        assert "access-control-allow-origin" not in res.headers


# ---- CORS ----


def test_preflight_rejects_disallowed_method_and_header(client: TestClient) -> None:
    origin = {"Origin": "http://localhost:5173"}
    bad_method = client.options(URL, headers={**origin, "Access-Control-Request-Method": "DELETE"})
    assert bad_method.status_code == 400
    bad_header = client.options(
        URL,
        headers={**origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Authorization"},
    )
    assert bad_header.status_code == 400


def test_cors_never_allows_credentials(client: TestClient) -> None:
    res = client.options(URL, headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-credentials" not in res.headers
    assert res.headers["access-control-allow-origin"] != "*"


def test_cors_multiple_origins(client_factory: ClientFactory) -> None:
    with client_factory(CORS_ORIGIN="https://a.example, https://b.example") as c:
        for o in ("https://a.example", "https://b.example"):
            assert c.get("/api/v1/health", headers={"Origin": o}).headers["access-control-allow-origin"] == o
        assert (
            "access-control-allow-origin"
            not in c.get("/api/v1/health", headers={"Origin": "https://c.example"}).headers
        )


def test_docs_available_outside_production(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 200


# ---- rate limiting interplay ----


def test_429_carries_security_cors_and_request_id(client_factory: ClientFactory) -> None:
    with client_factory(RATE_LIMIT_DISABLED=False, RATE_LIMIT_MAX=1) as c:
        c.get(URL)
        res = c.get(URL, headers={"Origin": "http://localhost:5173", "X-Request-Id": "rl-1"})
        assert_error_envelope(res, 429, "RATE_LIMITED")
        assert res.headers["ratelimit-remaining"] == "0"
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert res.headers["x-request-id"] == "rl-1"


def test_rate_limit_headers_on_every_api_response(client_factory: ClientFactory) -> None:
    with client_factory(RATE_LIMIT_DISABLED=False) as c:
        for res in (
            c.get(URL),
            c.post(URL, json={"title": ""}),
            c.post(URL, content=b"x", headers={"Content-Type": "text/plain"}),
            c.get("/api/v1/nope"),
        ):
            assert {"ratelimit-limit", "ratelimit-remaining", "ratelimit-reset"} <= set(res.headers)


def test_write_responses_report_write_limiter(client_factory: ClientFactory) -> None:
    with client_factory(RATE_LIMIT_DISABLED=False, RATE_LIMIT_MAX=50, WRITE_RATE_LIMIT_MAX=5) as c:
        res = c.post(URL, json={"title": "x"})
        assert res.headers["ratelimit-limit"] == "5"
        assert res.headers["ratelimit-remaining"] == "4"
        assert int(res.headers["ratelimit-reset"]) <= 60
        assert c.get(URL).headers["ratelimit-limit"] == "50"


def test_remaining_never_negative(client_factory: ClientFactory) -> None:
    with client_factory(RATE_LIMIT_DISABLED=False, RATE_LIMIT_MAX=2) as c:
        for _ in range(5):
            assert int(c.get(URL).headers["ratelimit-remaining"]) >= 0


def test_preflight_and_non_api_paths_not_limited(client_factory: ClientFactory) -> None:
    with client_factory(RATE_LIMIT_DISABLED=False, RATE_LIMIT_MAX=1) as c:
        c.get(URL)
        assert c.get(URL).status_code == 429
        pre = c.options(URL, headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
        assert pre.status_code == 200
        assert c.get("/openapi.json").status_code == 200


def test_trusted_proxy_keys_on_last_xff_entry(client_factory: ClientFactory) -> None:
    with client_factory(RATE_LIMIT_DISABLED=False, RATE_LIMIT_MAX=1, TRUST_PROXY=True) as c:
        assert c.get(URL, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        assert c.get(URL, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
        # client-controlled left-most entries must not buy a new bucket
        assert c.get(URL, headers={"X-Forwarded-For": "9.9.9.9, 2.2.2.2"}).status_code == 429


def test_rate_limited_write_is_not_persisted(client_factory: ClientFactory) -> None:
    with client_factory(RATE_LIMIT_DISABLED=False, WRITE_RATE_LIMIT_MAX=1) as c:
        c.post(URL, json={"title": "a"})
        assert c.post(URL, json={"title": "b"}).status_code == 429
        assert [b["title"] for b in c.get(URL).json()["data"]] == ["a"]


def test_health_not_rate_limited(client_factory: ClientFactory) -> None:
    with client_factory(RATE_LIMIT_DISABLED=False, RATE_LIMIT_MAX=1) as c:
        c.get(URL)
        for _ in range(5):
            assert c.get("/api/v1/health").status_code == 200
            assert c.head("/api/v1/health").status_code == 200
        assert c.get(URL).status_code == 429  # health calls neither consumed nor bypassed the books budget


def test_openapi_has_unique_operation_ids(client: TestClient) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # FastAPI warns on duplicate operationId (BUG-07)
        schema = client.app.openapi()  # type: ignore[attr-defined]
    ops = [op["operationId"] for item in schema["paths"].values() for op in item.values()]
    assert len(ops) == len(set(ops))
    assert "head" not in schema["paths"]["/api/v1/health"]


# ---- config fail-fast ----


@pytest.mark.parametrize(
    "bad",
    [
        {"APP_ENV": "prod"},
        {"PORT": 0},
        {"PORT": 70000},
        {"LOG_LEVEL": "trace"},
        {"RATE_LIMIT_MAX": 0},
        {"WRITE_RATE_LIMIT_WINDOW_MS": -1},
        {"JSON_BODY_LIMIT": "1gb"},
        {"JSON_BODY_LIMIT": "ten kb"},
        {"TRUST_PROXY": "maybe"},
    ],
)
def test_invalid_config_fails_fast(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **bad)  # type: ignore[call-arg]


@pytest.mark.parametrize(("raw", "expected"), [("2048", 2048), ("10kb", 10240), ("1MB", 1048576), (" 5 b ", 5)])
def test_body_limit_parsing(raw: str, expected: int) -> None:
    assert Settings(_env_file=None, JSON_BODY_LIMIT=raw).body_limit_bytes == expected  # type: ignore[call-arg]


def test_cors_origin_list_parsing() -> None:
    s = Settings(_env_file=None, CORS_ORIGIN=" https://a.example , ,https://b.example")  # type: ignore[call-arg]
    assert s.cors_origins == ["https://a.example", "https://b.example"]


# ---- concurrency (shared sqlite connection across threadpool) ----


def test_concurrent_creates_and_updates_are_consistent(client: TestClient) -> None:
    errors: list[int] = []

    def writer() -> None:
        for _ in range(25):
            res = client.post(URL, json={"title": "t"})
            if res.status_code != 201:
                errors.append(res.status_code)
                continue
            upd = client.patch(f"{URL}/{res.json()['data']['id']}", json={"status": "done"})
            if upd.status_code != 200:
                errors.append(upd.status_code)

    threads = [threading.Thread(target=writer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert client.get(f"{URL}/stats").json()["data"] == {"to-read": 0, "reading": 0, "done": 200, "total": 200}
    assert len({b["id"] for b in client.get(URL).json()["data"]}) == 200
