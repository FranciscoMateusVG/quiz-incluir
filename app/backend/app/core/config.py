from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import List
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.client_ip import parse_trusted_proxy_cidrs


_PRIVATE_AUTH_NETWORKS = (
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("fc00::/7"),
)
_ALLOWED_AUTH_SERVICE_NAMES = {"hono-app", "localhost"}


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

    @field_validator("MONOREPO_AUTH_URL")
    @classmethod
    def require_private_auth_url(cls, v: str) -> str:
        parsed = urlparse(v)
        host = parsed.hostname
        if (
            parsed.scheme != "http"
            or not host
            or parsed.path not in {"", "/"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "MONOREPO_AUTH_URL must be an internal HTTP service origin"
            )
        try:
            address = ip_address(host)
        except ValueError:
            if host not in _ALLOWED_AUTH_SERVICE_NAMES:
                raise ValueError("MONOREPO_AUTH_URL hostname is not allowlisted")
        else:
            private_address = any(
                address.version == network.version and address in network
                for network in _PRIVATE_AUTH_NETWORKS
            )
            if not (private_address or address.is_loopback):
                raise ValueError(
                    "MONOREPO_AUTH_URL must use loopback or RFC1918/ULA private IP"
                )
        return v.rstrip("/")

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
        default="your-secret-key-change-in-production",
        description="Session-signing key for the SQLAdmin backoffice panel only.",
    )

    FRONTEND_URL: str = Field(
        default="http://localhost:3000",
        description="Frontend URL for CORS and OAuth redirects",
    )

    ALL_CORS_ORIGINS: List[str] = Field(
        default=["*"], description="Allowed CORS origins"
    )

    DEFAULT_USER_LEVEL: str = Field(
        default="B1", description="Default course level for new users"
    )

    ADMIN_USERNAME: str = Field(default="admin", description="SQLAdmin panel username")
    ADMIN_PASSWORD: str = Field(
        default="change-me", description="SQLAdmin panel password"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
