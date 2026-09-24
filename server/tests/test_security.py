from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.middleware.rate_limit import FixedWindowLimiter

ClientFactory = Callable[..., TestClient]


def test_security_headers_present(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {"data": {"status": "ok"}}
    h = res.headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "default-src 'none'" in h["content-security-policy"]
    assert h["referrer-policy"] == "no-referrer"
    assert "max-age" in h["strict-transport-security"]
    assert h["cache-control"] == "no-store"
    assert "x-powered-by" not in h
    assert "server" not in h


def test_health_supports_head(client: TestClient) -> None:
    res = client.head("/api/v1/health")
    assert res.status_code == 200
    assert res.headers["x-content-type-options"] == "nosniff"


def test_security_headers_on_error_responses(client: TestClient) -> None:
    res = client.get("/api/v1/nope")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-request-id"]


def test_request_id_generated_and_echoed(client: TestClient) -> None:
    assert len(client.get("/api/v1/health").headers["x-request-id"]) == 36
    assert client.get("/api/v1/health", headers={"X-Request-Id": "abc-123"}).headers["x-request-id"] == "abc-123"


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    rid = client.get("/api/v1/health", headers={"X-Request-Id": "evil\tinjected {log}"}).headers["x-request-id"]
    assert rid != "evil\tinjected {log}" and len(rid) == 36


def test_unknown_route_returns_json_404(client: TestClient) -> None:
    res = client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    assert res.json() == {"error": {"code": "NOT_FOUND", "message": "Route not found"}}


def test_unsupported_method_returns_json_404(client: TestClient) -> None:
    res = client.delete("/api/v1/books")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_body_over_limit_returns_413(client: TestClient) -> None:
    res = client.post("/api/v1/books", json={"title": "x", "author": "a" * 11_000})
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_chunked_body_over_limit_returns_413(client: TestClient) -> None:
    def gen():  # type: ignore[no-untyped-def]
        yield b'{"title": "' + b"x" * 6000
        yield b"x" * 6000 + b'"}'

    res = client.post("/api/v1/books", content=gen(), headers={"Content-Type": "application/json"})
    assert res.status_code == 413


def test_sql_injection_in_title_is_stored_as_text(client: TestClient) -> None:
    payload = "Robert'); DROP TABLE books;--"
    assert client.post("/api/v1/books", json={"title": payload}).status_code == 201
    data = client.get("/api/v1/books").json()["data"]
    assert [b["title"] for b in data] == [payload]


def test_internal_error_hides_details(client: TestClient) -> None:
    def boom() -> None:
        raise RuntimeError("secret db path /etc/passwd")

    client.app.state.book_service.stats = boom  # type: ignore[attr-defined]
    res = client.get("/api/v1/books/stats")
    assert res.status_code == 500
    assert res.json() == {"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong"}}
    assert "secret" not in res.text and "Traceback" not in res.text
    assert res.headers["x-content-type-options"] == "nosniff"


def test_cors_allows_configured_origin_only(client: TestClient) -> None:
    ok = client.options(
        "/api/v1/books",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "DELETE" not in ok.headers["access-control-allow-methods"]

    bad = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_cors_exposes_rate_limit_headers(client: TestClient) -> None:
    res = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    exposed = res.headers["access-control-expose-headers"].lower()
    assert "retry-after" in exposed and "ratelimit-remaining" in exposed


def test_docs_disabled_in_production(client_factory: ClientFactory) -> None:
    with client_factory(APP_ENV="production") as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 404


# ---- rate limiting ----


def test_global_rate_limit(client_factory: ClientFactory) -> None:
    with client_factory(RATE_LIMIT_DISABLED=False, RATE_LIMIT_MAX=3) as c:
        for remaining in (2, 1, 0):
            res = c.get("/api/v1/books")
            assert res.status_code == 200
            assert res.headers["ratelimit-limit"] == "3"
            assert res.headers["ratelimit-remaining"] == str(remaining)
            assert int(res.headers["ratelimit-reset"]) > 0
        res = c.get("/api/v1/books")
        assert res.status_code == 429
        assert int(res.headers["retry-after"]) > 0
        err = res.json()["error"]
        assert err["code"] == "RATE_LIMITED"
        assert err["message"] == f"Too many requests, try again in {res.headers['retry-after']} seconds"


def test_write_rate_limit_is_stricter_and_reads_still_work(client_factory: ClientFactory) -> None:
    with client_factory(RATE_LIMIT_DISABLED=False, RATE_LIMIT_MAX=100, WRITE_RATE_LIMIT_MAX=2) as c:
        assert c.post("/api/v1/books", json={"title": "a"}).status_code == 201
        assert c.post("/api/v1/books", json={"title": "b"}).status_code == 201
        blocked = c.post("/api/v1/books", json={"title": "c"})
        assert blocked.status_code == 429
        assert blocked.headers["ratelimit-limit"] == "2"
        assert c.patch("/api/v1/books/x", json={"status": "done"}).status_code == 429
        assert c.get("/api/v1/books").status_code == 200  # reads unaffected
        assert len(c.get("/api/v1/books").json()["data"]) == 2


def test_rate_limit_ignores_x_forwarded_for_by_default(client_factory: ClientFactory) -> None:
    with client_factory(RATE_LIMIT_DISABLED=False, RATE_LIMIT_MAX=1) as c:
        assert c.get("/api/v1/books", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        assert c.get("/api/v1/books", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429


def test_limiter_window_resets() -> None:
    now = [0.0]
    limiter = FixedWindowLimiter(limit=1, window_ms=1000, now=lambda: now[0])
    assert limiter.hit("ip").allowed
    assert not limiter.hit("ip").allowed
    assert limiter.hit("other-ip").allowed
    now[0] = 1.0
    assert limiter.hit("ip").allowed
