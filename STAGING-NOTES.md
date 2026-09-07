# Quiz staging — provisioning notes (aperture-ztid5)

Companion to `docker-compose.staging.yml`. Read before provisioning.

## What this stack is

The combined single-process Quiz service running against a **real but isolated**
Incluir BetterAuth with **synthetic identities** and its own databases. Never
production auth, never production data, never production identities.

## Topology decision, and why

Quiz reaches BetterAuth **server-side** (Python `httpx`, container-to-container).
So the isolated Hono needs **no public route, no Traefik label, no domain and no
TLS certificate**. Only `quiz-incluir-backend-staging` is published, at
`staging-quiz.programaincluir.org`.

That is deliberate: it keeps the entire test-auth surface internal. A second
public auth host would be a larger attack surface for no functional gain. **If a
browser-side auth call is ever introduced, this decision and `CORS_ORIGINS` must
both be revisited** — the current shape assumes the server-side relay.

## ⚠ The one unresolved provisioning constraint

`quiz-staging-hono` is referenced by **image tag**, not built here. Dokploy
builds from a single repo, and the Hono lives in `monorepo-incluir` — so the
image must be **built from the pinned monorepo revision and made available on
the target host** before this stack can come up.

Pinned revision: `9cb605fc2cc63930a9fdf4f73ccec3ec05c6daad`, the same commit
Incluir production runs, built from `apps/hono-app/Dockerfile`. This is the same
artifact already proven locally in compose project `quiz-authfix-ztid5`.

Resolve by either (a) building the image on the host from that pinned revision
and setting `STAGING_HONO_IMAGE` to the local tag, or (b) publishing it to a
registry the host can pull. That decision is not made here.

## Required environment (set in the Dokploy panel, never committed)

| Variable | Notes |
|---|---|
| `QUIZ_DB_PASSWORD` | staging-only |
| `SECRET_KEY` | staging-only; SQLAdmin session signing |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | staging-only. This is the **SQLAdmin** surface — a separate auth system from BetterAuth. `config.py` ships insecure placeholders, so both MUST be set explicitly rather than inherited. |
| `STAGING_HONO_IMAGE` | tag of the Hono image built from the pinned revision |
| `STAGING_HONO_DB_PASSWORD` | staging-only |
| `STAGING_BETTER_AUTH_SECRET` | staging-only; must NOT be a production value |
| `TRUSTED_PROXY_CIDRS` | **Leave EMPTY during preparation — empty is deny-all.** |

## TRUSTED_PROXY_CIDRS — get this right

It is the **exact observed Traefik peer** as a `/32` (or `/128` for IPv6). It is
**not** a network range. `10.0.1.0/24` and any staging equivalent are
**forbidden by contract** — a `/24` trusts every container that can reach that
network, which on a shared `dokploy-network` is a materially wider boundary than
the single proxy actually in front of us.

Obtain the peer by **rendering the networking and observing it**, then prove the
raw peer chain before any auth gate. Do not infer it, and do not carry a value
over from production.

## Verification that must NOT be skipped

- **Prove network membership from the SOURCE side** before trusting any
  in-container `hono-app:3003/health` result. A health check run from a *peer*
  container proves that peer's connectivity, not the backend's.
- **Quiz has no real HTTP health endpoint.** `/openapi.json` returns `paths {}`,
  and `/health`, `/login`, `/admin` all return the same 200 SPA shell. An HTTP
  200 proves the shell is served and would pass against a dead application
  layer. Health evidence must be container- or websocket-level.
- The merged image serves **port 8000**. Production's domain still targets a
  removed frontend service on 8080 — that retarget is `aperture-rp14v`, gated,
  and is **not** part of staging.

## Fixtures

Synthetic identities come from the monorepo `seed-e2e.ts` set (all
`@incluir.test`), seeded into `quiz-staging-hono-db`. Quiz roles are **local**
and do not federate: to pin an admin, pre-insert the Quiz `users` row before
that identity's first login — `get_or_create_by_email` returns an existing row
untouched and never writes `role`.
