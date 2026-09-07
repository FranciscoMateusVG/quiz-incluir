# Phase A authentication runtime

The production backend is the single combined FastAPI/Flet process built from
`docker/backend.Dockerfile`. It deliberately starts Uvicorn with
`--no-proxy-headers`; application middleware is the only owner of forwarded-IP
interpretation. Do not re-enable generic Uvicorn proxy parsing. Doing so makes
raw-peer trust depend on ambient `FORWARDED_ALLOW_IPS` state.

## Required deployment environment

| Variable | Requirement |
| --- | --- |
| `DATABASE_URL` / `QUIZ_DB_PASSWORD` | Dedicated Quiz Postgres only. Never point this service at the Incluir database. |
| `SECRET_KEY` | Non-default SQLAdmin session-signing secret. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Non-default SQLAdmin credentials. This Phase does not change SQLAdmin auth. |
| `MONOREPO_AUTH_URL` | Private HTTP origin for the existing Hono/BetterAuth service, such as `http://hono-app:3003`. Public hostnames/IPs and URL credentials/query/fragment are rejected. |
| `TRUSTED_PROXY_CIDRS` | Narrow comma-separated CIDRs for public Traefik peer(s), supplied per environment by infrastructure. Empty trusts no proxies; invalid or wildcard CIDRs fail startup. |
| `FLET_SESSION_TIMEOUT_SECONDS` | Optional. Defaults to and is capped at 3,600 seconds. Short values are for isolated expiry testing only. |

`TRUSTED_PROXY_CIDRS` authorizes only the public `X-Forwarded-For` chain used
to set the server-owned Flet `Page.client_ip`. It never authorizes
`X-Quiz-Client-IP`. That dedicated header is accepted only from an original
socket peer of exactly `127.0.0.1` or `::1` for the same-process Flet relay.
Missing or unprovable peer metadata cannot gain relay authority.

## Deployment verification

Before a staging release, verify all three layers rather than merely checking
the source file:

1. `docker compose -f docker-compose.prod.yml config` renders the intended
   private auth origin and exact `TRUSTED_PROXY_CIDRS` value.
2. The built backend image command contains `--no-proxy-headers`.
3. The running staging container contains the intended environment values;
   verify names and non-secret configuration only, never credential values.

The isolated real-BetterAuth substrate is reached from a joined container
network as `http://hono-app:3003`; the host-only loopback fixture URL is not
reachable from another container. No production identity or credential is
needed for Phase A verification.

## Session and logout semantics

Every protected API call revalidates the opaque cookie with BetterAuth.
Proven invalid/expired/revoked state returns `401`; upstream outage returns
`503`; malformed/unexpected upstream state returns `502`. Those outcomes must
not be collapsed.

Logout acts only on the current Quiz-created cookie. A `204` is emitted only
after sign-out and a former-cookie probe proves the session absent. A sign-out
`2xx` by itself is not confirmation. The frontend clears local state in every
logout outcome but displays a warning when server revocation is unconfirmed.

Same-tab Flet reconnect behavior is intentionally unchanged. The normal
retention timeout is 3,600 seconds; exact reconnect/expiry behavior is a
staging WebSocket gate, not a durable SSO guarantee.
