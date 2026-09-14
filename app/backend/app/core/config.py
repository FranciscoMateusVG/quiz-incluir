from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.client_ip import parse_trusted_proxy_cidrs


_ALLOWED_MONOREPO_AUTH_URLS = {
    "http://hono-app:3003",
    "http://quiz-staging-hono:3003",
    "http://127.0.0.1:4503",
}

_REJECTED_SECRET_KEYS = {"your-secret-key-change-in-production"}
_REJECTED_ADMIN_PASSWORDS = {"change-me"}


def _require_non_placeholder(
    value: str,
    *,
    field_name: str,
    rejected: set[str],
) -> str:
    if value != value.strip() or not value.strip():
        raise ValueError(f"{field_name} must be nonblank without outer whitespace")
    if value.casefold() in rejected:
        raise ValueError(f"{field_name} uses a shipped placeholder")
    return value


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
        default="http://hono-app:3003",
        description="Base URL of the Programa Incluir monorepo's auth API (hono-app / BetterAuth). "
        "The quiz backend delegates all end-user authentication to this service.",
    )

    @field_validator("MONOREPO_AUTH_URL")
    @classmethod
    def require_private_auth_url(cls, v: str) -> str:
        if v not in _ALLOWED_MONOREPO_AUTH_URLS:
            raise ValueError("MONOREPO_AUTH_URL is not an approved auth service origin")
        return v

    TRUSTED_PROXY_CIDRS: str = Field(
        default="",
        description="Comma-separated exact /32 or /128 public reverse-proxy peers whose "
        "X-Forwarded-For chains may be interpreted. Empty trusts no proxies.",
    )

    @field_validator("TRUSTED_PROXY_CIDRS")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, v: str) -> str:
        # Parse during settings construction so malformed or wildcard trust
        # fails startup rather than silently changing rate-limit attribution.
        parse_trusted_proxy_cidrs(v)
        return v

    @property
    def trusted_proxy_networks(self) -> tuple[IPv4Network | IPv6Network, ...]:
        return parse_trusted_proxy_cidrs(self.TRUSTED_PROXY_CIDRS)

    FLET_SESSION_TIMEOUT_SECONDS: int = Field(
        default=3600,
        ge=1,
        le=3600,
        description="Disconnected Flet session retention. Production default/max is one hour.",
    )

    SECRET_KEY: str = Field(
        min_length=32,
        max_length=256,
        description="Session-signing key for the SQLAdmin backoffice panel only.",
    )

    @field_validator("SECRET_KEY")
    @classmethod
    def require_private_secret_key(cls, v: str) -> str:
        return _require_non_placeholder(
            v,
            field_name="SECRET_KEY",
            rejected=_REJECTED_SECRET_KEYS,
        )

    FRONTEND_URL: str = Field(
        default="http://localhost:3000",
        description="Frontend URL for CORS and OAuth redirects",
    )

    ALL_CORS_ORIGINS: list[str] = Field(
        default_factory=list,
        description="Exact credentialed CORS origins; empty keeps same-origin only.",
    )

    @field_validator("ALL_CORS_ORIGINS")
    @classmethod
    def require_exact_cors_origins(cls, origins: list[str]) -> list[str]:
        if len(origins) > 8:
            raise ValueError("ALL_CORS_ORIGINS supports at most 8 exact origins")
        if len(set(origins)) != len(origins):
            raise ValueError("ALL_CORS_ORIGINS contains a duplicate origin")

        for origin in origins:
            if origin == "*":
                raise ValueError("credentialed CORS cannot use a wildcard origin")
            if origin != origin.strip() or not origin:
                raise ValueError("CORS origins must be nonblank without whitespace")
            parsed = urlsplit(origin)
            try:
                parsed.port
            except ValueError as exc:
                raise ValueError("CORS origin has an invalid port") from exc
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname is None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or origin != f"{parsed.scheme}://{parsed.netloc}"
            ):
                raise ValueError("CORS origins must be exact HTTP origins")
        return origins

    DEFAULT_USER_LEVEL: str = Field(
        default="B1", description="Default course level for new users"
    )

    ADMIN_USERNAME: str = Field(
        min_length=1,
        max_length=128,
        description="SQLAdmin panel username",
    )
    ADMIN_PASSWORD: str = Field(
        min_length=12,
        max_length=256,
        description="SQLAdmin panel password",
    )

    @field_validator("ADMIN_USERNAME")
    @classmethod
    def require_private_admin_username(cls, v: str) -> str:
        value = _require_non_placeholder(
            v, field_name="ADMIN_USERNAME", rejected=set()
        )
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("ADMIN_USERNAME cannot contain control characters")
        return value

    @field_validator("ADMIN_PASSWORD")
    @classmethod
    def require_private_admin_password(cls, v: str) -> str:
        return _require_non_placeholder(
            v,
            field_name="ADMIN_PASSWORD",
            rejected=_REJECTED_ADMIN_PASSWORDS,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
