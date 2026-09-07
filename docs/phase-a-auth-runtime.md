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
| `MONOREPO_AUTH_URL` | Exactly `http://hono-app:3003` for production, `http://quiz-staging-hono:3003` for the isolated staging network, or `http://127.0.0.1:4503` for the approved isolated host fixture. Every other host, address, port, scheme, or URL spelling fails startup. |
| `TRUSTED_PROXY_CIDRS` | Comma-separated exact `/32` or `/128` public Traefik peers, supplied per environment by infrastructure. Empty trusts no proxies; broad or loopback entries fail startup. |
| `FLET_SESSION_TIMEOUT_SECONDS` | Optional. Defaults to and is capped at 3,600 seconds. Short values are for isolated expiry testing only. |

`TRUSTED_PROXY_CIDRS` authorizes only the public `X-Forwarded-For` chain used
to set the server-owned Flet `Page.client_ip`. It never authorizes
`X-Quiz-Client-IP`. That dedicated header is accepted only from an original
socket peer of exactly `127.0.0.1` or `::1` for the same-process Flet relay.
Missing or unprovable peer metadata cannot gain relay authority.
An exact-loopback caller with absent or malformed dedicated metadata uses the
shared safe bucket and never falls through to public XFF interpretation.

## Deployment verification

Before a staging release, verify all four layers rather than merely checking
the source file:

1. `docker compose -f <selected-compose-file> config` renders the intended
   private auth origin and exact `TRUSTED_PROXY_CIDRS` value.
2. The built backend image command contains `--no-proxy-headers`.
3. From the running staging backend, `quiz-staging-hono` resolves only to the
   isolated Hono container address on `quiz-staging-net`. Compare resolver
   output with that container's address and network membership. Do not accept
   a source render or a health response from another container as proof: the
   Dokploy-injected shared network can add a conflicting production alias only
   at deployment time.
4. The running staging container contains the intended environment values;
   verify names and non-secret configuration only, never credential values.

The isolated real-BetterAuth substrate is reached from the joined staging
network as `http://quiz-staging-hono:3003`; the host-only loopback fixture URL
is not reachable from another container. No production identity or credential
is needed for Phase A verification.

The relay's private HTTP client ignores ambient proxy/netrc/CA environment
state (`trust_env=False`) and never follows redirects. A misconfigured proxy
therefore cannot receive CPF/password, canonical client IP, or session cookies,
and a redirect cannot move those values away from the exact configured origin.

## Session and logout semantics

Every protected API call revalidates the opaque cookie with BetterAuth.
Proven invalid/expired/revoked state returns `401`; upstream outage returns
`503`; malformed/unexpected upstream state returns `502`. Those outcomes must
not be collapsed.

An active session requires the pinned BetterAuth minimum shape: nonempty string
`session.id`, nonempty string `user.id`, and a syntactically validated
`user.email`. Only an absent or null session is invalid; falsey values of the
wrong type are malformed. The accepted cookie is one exact BetterAuth
`name=value` pair, at most 4,096 bytes, with an RFC 6265 cookie-octet value. It
is preserved unchanged and validated both when issued and before every forward.

The verified email is the immutable Quiz-local identity key. First login uses a
private verified-identity creation path with explicit `STUDENT`/`B1` defaults;
existing local role and level are retained. Public create input keeps `EmailStr`
validation, and `PATCH /api/v1/users/me` accepts only non-identity fields.

Logout acts only on the current Quiz-created cookie. A `204` is emitted only
after sign-out and a former-cookie probe proves the session absent. A sign-out
`2xx` by itself is not confirmation. The frontend clears local state in every
logout outcome but displays a warning when server revocation is unconfirmed.

Same-tab Flet reconnect behavior is intentionally unchanged. The normal
retention timeout is 3,600 seconds; exact reconnect/expiry behavior is a
staging WebSocket gate, not a durable SSO guarantee.
