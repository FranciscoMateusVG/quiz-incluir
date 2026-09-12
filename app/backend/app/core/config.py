from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Quiz API"

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/quiz",
        description="Async database URL",
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def normalize_db_url(cls, v: str) -> str:
        """Ensure SQLAlchemy async engines get an async driver for Postgres.

        Render injects ``DATABASE_URL`` as ``postgresql://user:pass@host/db``
        (sync scheme). Rewrite it to the asyncpg scheme the app uses.
        """
        if v.startswith("postgres://") or v.startswith("postgresql://"):
            scheme = v.split("://", 1)[0]
            if "+" not in scheme:
                return "postgresql+asyncpg://" + v.split("://", 1)[1]
        return v

    MONOREPO_AUTH_URL: str = Field(
        default="http://localhost:3003",
        description="Base URL of the Programa Incluir monorepo's auth API (hono-app / BetterAuth). "
        "The quiz backend delegates all end-user authentication to this service.",
    )

    SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        description="Session-signing key for the SQLAdmin backoffice panel only.",
    )

    FRONTEND_URL: str = Field(default="http://localhost:3000", description="Frontend URL for CORS and OAuth redirects")

    ALL_CORS_ORIGINS: List[str] = Field(default=["*"], description="Allowed CORS origins")

    DEFAULT_USER_LEVEL: str = Field(default="B1", description="Default course level for new users")

    ADMIN_USERNAME: str = Field(default="admin", description="SQLAdmin panel username")
    ADMIN_PASSWORD: str = Field(default="change-me", description="SQLAdmin panel password")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# The monorepo's own e2e seed script (apps/hono-app/scripts/seed-e2e.ts)
# deliberately uses `@*.test` addresses — the RFC 2606 TLD reserved exactly
# for this purpose, so fixtures can never collide with a real domain.
# `email_validator` (which backs every `EmailStr` field here, including
# UserRead/AdminAttemptRow on read and UserCreate on write) rejects reserved
# TLDs by default, which meant `get_or_create_by_email` 422'd for every
# seeded account the moment a real login mirrored one in.
#
# This only ever relaxes validation for `.test`/`.example`/`.invalid`/
# `.localhost` — no real account can have one of those, so it's safe to leave
# on unconditionally rather than gating it behind an env var.
import email_validator  # noqa: E402

email_validator.TEST_ENVIRONMENT = True