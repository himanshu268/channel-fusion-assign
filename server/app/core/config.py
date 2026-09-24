"""Typed, validated settings. Invalid env fails fast at startup."""

from __future__ import annotations

import re
from functools import cached_property
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SIZE_RE = re.compile(r"^\s*(\d+)\s*(b|kb|mb)?\s*$", re.IGNORECASE)
_UNITS = {"b": 1, "kb": 1024, "mb": 1024 * 1024}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    APP_ENV: Literal["development", "test", "production"] = "development"
    PORT: int = Field(4000, ge=1, le=65535)
    LOG_LEVEL: Literal["debug", "info", "warning", "error"] = "info"
    DB_PATH: str = "./data/books.db"
    CORS_ORIGIN: str = "http://localhost:5173"
    TRUST_PROXY: bool = False
    RATE_LIMIT_WINDOW_MS: int = Field(900_000, gt=0)
    RATE_LIMIT_MAX: int = Field(100, gt=0)
    WRITE_RATE_LIMIT_WINDOW_MS: int = Field(60_000, gt=0)
    WRITE_RATE_LIMIT_MAX: int = Field(20, gt=0)
    RATE_LIMIT_DISABLED: bool = False
    JSON_BODY_LIMIT: str = "10kb"

    @field_validator("JSON_BODY_LIMIT")
    @classmethod
    def _check_size(cls, v: str) -> str:
        if not _SIZE_RE.match(v):
            raise ValueError("JSON_BODY_LIMIT must look like '10kb', '1mb' or '2048'")
        return v

    @cached_property
    def body_limit_bytes(self) -> int:
        m = _SIZE_RE.match(self.JSON_BODY_LIMIT)
        assert m is not None
        return int(m.group(1)) * _UNITS[(m.group(2) or "b").lower()]

    @cached_property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGIN.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"
