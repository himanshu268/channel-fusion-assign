from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.connection import open_db
from app.main import create_app


class FakeClock:
    """Deterministic clock: each call advances 1s, so createdAt/updatedAt ordering is testable."""

    def __init__(self) -> None:
        self.t = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.t += timedelta(seconds=1)
        return self.t


def make_client(**overrides: Any) -> TestClient:
    base: dict[str, Any] = {"APP_ENV": "test", "LOG_LEVEL": "error", "RATE_LIMIT_DISABLED": True}
    settings = Settings(_env_file=None, **{**base, **overrides})  # type: ignore[call-arg]
    app = create_app(settings, open_db(":memory:"), FakeClock())
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with make_client() as c:
        yield c


@pytest.fixture
def client_factory() -> Callable[..., TestClient]:
    return make_client


@pytest.fixture
def add_book(client: TestClient) -> Callable[..., dict[str, Any]]:
    def _add(title: str = "Dune", **fields: Any) -> dict[str, Any]:
        res = client.post("/api/v1/books", json={"title": title, **fields})
        assert res.status_code == 201, res.text
        book: dict[str, Any] = res.json()["data"]
        return book

    return _add
