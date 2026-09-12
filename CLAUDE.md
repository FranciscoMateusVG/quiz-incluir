# quiz-incluir

A quiz app for Programa Incluir's English course: students take CEFR-levelled
quizzes, teachers see class-wide grades. FastAPI backend, React SPA frontend,
Postgres, deployed as a **single process** at quiz.programaincluir.org.

## Layout

```
app/
├── backend/    FastAPI + SQLModel + Alembic. The ASGI app is app/backend/main.py.
├── web/        React 19 + TypeScript SPA (Vite). The frontend.
├── shared/     quiz_shared: Pydantic wire schemas + enums. Source of truth.
└── ai/         Offline question generation. Not part of the served app.
```

Python is a **uv workspace** (`pyproject.toml` at the root, members under
`app/`). `app/web` is a **separate pnpm project** — deliberately not a uv or
pnpm workspace member, since nothing else in this repo is JS.

> `app/web` uses **pnpm** (pinned via `packageManager`), matching the
> `monorepo-incluir` convention. It is not part of that monorepo's workspace —
> that is a different git repo, so its `@repo/ui` / `@repo/domains` packages
> can only be copied from, not depended on.

## Running it

```bash
make backend    # API + SPA on :8000 (needs make web-build first)
make web        # Vite dev server on :5173, proxying /api and /backoffice -> :8000
make web-build  # compile the SPA into app/backend/static/web
make web-test   # vitest
```

Day-to-day UI work: `make backend` in one shell, `make web` in another, and
use **:5173** (hot reload). `make web-build` then `make backend` is how you
check the real, served bundle.

Two setup gotchas:

- **`Makefile` is gitignored.** Treat it as local convenience, not shared
  tooling.
- **Its `DATABASE_URL` does not match `compose.yaml`.** The Makefile points at
  `:55433` (`quiz/quiz`); `compose.yaml` brings up postgres on `:5432`
  (`postgres/postgres`, db `quiz`). If you use the compose DB:
  ```bash
  make backend DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/quiz"
  ```

Anything past listing quizzes needs the auth service — see "Authentication".

## URL map

The API and both admin surfaces are registered **before** a catch-all UI mount
at `/`. Ordering in `main.py` is load-bearing: anything registered after a root
mount is unreachable.

| Path | Served by |
|---|---|
| `/api/v1/*` | the REST API |
| `/backoffice/*` | SQLAdmin (DB CRUD, separate password) |
| everything else | the UI |

Three traps live here, all of them consequences of the catch-all:

1. **Never put a trailing slash on an API path.** Collection routes are
   declared `@router.get("")`, so `/api/v1/quizzes/` misses the API, is caught
   by the UI mount, and returns `index.html` **with a 200**. `app/web`'s fetch
   wrapper rejects non-JSON responses to make that failure legible; if you call
   the API from anywhere else, do the same.
2. **SQLAdmin lives at `/backoffice`, not `/admin`.** A sub-app mount beats the
   catch-all for its whole prefix, so at `/admin` it also swallowed the SPA's
   own `/admin/grades` routes. Those are real, shareable URLs now, so the two
   cannot share a prefix. `main.py` keeps an explicit `/backoffice` →
   `/backoffice/` redirect because Starlette's own trailing-slash fallback only
   fires when nothing else matches — and the catch-all always matches.
3. **The SPA fallback is selective.** `SpaStaticFiles`
   (`app/backend/app/core/spa.py`) serves `index.html` for unknown paths only
   when the extension is `""` or `.html`. A missing `.js`/`.css` must keep
   404ing — answering it with HTML turns a stale asset reference into a
   confusing MIME error instead of an obvious missing-file one.

## Serving the SPA

`app/backend/main.py` always mounts the built SPA (`app/backend/static/web`)
at `/`, behind the API and `/backoffice` routes registered above it — it
refuses to boot if the bundle is missing, rather than serving 404s. Build it
with `make web-build` (or `pnpm --dir app/web build`).

Note `render.yaml` uses `runtime: python` with no Node stage, so a Render
deploy from that config alone would have no bundle to serve. The real
production deploy is `docker/backend.Dockerfile` (a `node:22` build stage
compiles the SPA and copies it in; no Node ships in the final image) via
`docker-compose.prod.yml` — see the header comment there.

## UI

`app/web` is a React SPA covering every screen: login, quiz picker, question
flow, results, and the two admin grade screens. Sign-in is real (CPF +
password, delegated to the monorepo — see "Authentication" below).

`/quiz/:index` is URL-authoritative — the index in the path is what's
rendered, and the in-flight attempt persists to `sessionStorage`
(`store/useAttemptStore.ts`), so a refresh or the back button both work
correctly mid-quiz. UI chrome is Brazilian Portuguese (`src/i18n/pt-BR.ts`),
per `monorepo-incluir/AGENTS.md`; quiz *content* stays English, since that's
the language being taught.

## The API contract

`app/shared/quiz_shared/{schemas,enums}.py` is the source of truth, imported by
the backend and mirrored by hand in `app/web/src/api/types.ts`. There is **no
OpenAPI schema** to generate from (`openapi_url=None` in `main.py`), so a test
(`src/__tests__/enums.test.ts`) parses `enums.py` and fails if the TS unions
drift.

Three things that surprise people:

- **`score`/`max_score` are normalized to 0–10**, not raw points
  (`GRADE_SCALE` in `app/core/grading.py`). `score` is `null` until the attempt
  is finished, and `max_score` is `0.0` for a quiz with no gradable points — so
  guard the percentage divide.
- **`LanguageLevel` vs `CourseLevel`.** Both contain the literals `B1`/`B2` and
  mean different things: `quiz.level` is CEFR difficulty (A1–C2), `user.level`
  is the student's turma (B1–B4). The admin filter and grade chart group by
  `CourseLevel`.
- **`POST /attempts/{id}/answers` returns `200`, not `201`**, is an upsert
  (unique on `attempt_id, question_id`), and already includes `is_correct` and
  `points_awarded`. No UI surfaces per-question feedback today; the data is
  there if you want to.

### Question types

`question.config` is an untyped JSON column shaped per `question.type`
(`app/backend/app/core/question_types.py`). The response payload shapes are
**not negotiable** — the graders read exactly these keys:

| `type` | student-visible `config` | `response` submitted |
|---|---|---|
| `multiple_choice` | `{options}` | `{selected: "<option text>"}` |
| `multiple_selection` | `{options}` | `{selected: ["<text>", ...]}` |
| `true_false` | — | `{selected: true \| false}` |
| `short_text` | — | `{text: "..."}` |

- Choice grading compares the option **text**, not its index (lowercased and
  stripped on both sides). Sending an index silently scores zero.
- `true_false` compares with a strict `==` against a boolean, so the *string*
  `"true"` also silently scores zero.
- Malformed config degrades rather than raising, both server-side
  (`parse_config` returns `None`) and client-side (`parseOptions` returns
  `null`). Keep it that way; there is legacy data.

### The answer key is stripped for non-admins

`GET /api/v1/questions` and `/questions/{id}` are **public**, and used to return
`config` in full — leaking `correct_index`, `correct_indices`, `answer`,
`accepted_answers` and `explanations` to the browser before the student
answered. `public_config()` in `question_types.py` now removes those unless the
caller is an admin (via `get_optional_current_user`, so the routes stay public).

Grading, `pdf_report.py` and SQLAdmin all read the ORM row directly and are
unaffected. If you add a config key that gives away an answer, add it to
`ANSWER_KEY_FIELDS`.

## Authentication

There is **no local password store and no JWT**. `POST /api/v1/auth/token`
relays credentials to the Programa Incluir monorepo's BetterAuth service at
`MONOREPO_AUTH_URL` (`apps/hono-app`, `:3003`) and returns its **session-cookie
string** as `access_token`. Treat that token as opaque — it cannot be decoded,
and staleness only ever surfaces as a 401.

Consequences worth knowing:

- Every authenticated request makes an **uncached outbound HTTP call** to that
  service. Batch client-side fetches (`getQuestions` uses `Promise.all`) rather
  than looping.
- A local `users` row is auto-created on first authenticated request, defaulting
  to `role=student`, `level=B1`.
- **Admin is a manual DB edit.** `users.role` has no endpoint; set it in
  SQLAdmin. Route guards read it from `GET /users/me`.
- `/backoffice` is a *separate* gate — `ADMIN_USERNAME`/`ADMIN_PASSWORD` in a
  signed cookie session, unrelated to user auth.

Which endpoints need a token: `/quizzes`, `/questions`, `/media` and
`/quiz-media` reads are **public**; attempts, answers, the PDF report and
`/admin/*` all require one. So the picker and question rendering are testable
with no auth service running.

## Media

Metadata only — no uploads, no file storage. Rows carry `type`, `url`,
`caption`, `position`, pointing at external hosts. Two kinds, and the
distinction matters: **`quiz_media`** is context shared by the whole quiz (a
reading passage, a listening clip) and renders as a persistent header on
*every* question; **`question_media`** illustrates one question.

`resolveMediaUrl` (`app/web/src/lib/media.ts`) unwraps `?imgurl=` wrapper
params, passes absolute URLs through, and joins relative ones onto the API
base. It is tested — see `src/__tests__/media.test.ts`.

Every seeded `text` media row carries its passage inline in `caption` with **no
`url`**, so markdown rendering needs no network. The `url` branch still exists
and now fetches from the browser, so a remote markdown file would need CORS on
its host (it falls back to the caption on failure). Images, audio and video use
plain `<img>`/`<audio>`/`<video>` tags, which need no CORS.

## Conventions (app/web)

Follows `monorepo-incluir/apps/frontend` where it makes sense: `PascalCase.tsx`
components, `camelCase.ts` hooks and helpers, kebab-case only inside
`components/ui/` (shadcn), inline `import { type Foo }`, Prettier defaults plus
the Tailwind class sorter, `strict` + `noUncheckedIndexedAccess`, `@/*` → `src/*`.
Commits as `feat(scope):`.

Light mode only, with the brand palette (mirrors `app.programaincluir.org`)
defined as tokens in `tailwind.config.ts`. Cards are **flat white with a 1px
border and no shadow** — house style, not an oversight.

Charts use chart.js + react-chartjs-2, lazy-loaded so students don't download
them. The grade distribution is a real box plot computed in `lib/boxplot.ts`
(Tukey: quartiles by linear interpolation, whiskers to 1.5 IQR) rather than a
plugin. Its median rule is drawn in **foreground ink, not a second orange** —
a same-hue outline/median pair only ΔE 7.5 apart nearly disappears against its
own box (validated with the dataviz skill's palette checker).

## Known issues (pre-existing, unfixed)

- **`GET /api/v1/answers` has no ownership filter.** Any authenticated user can
  list every answer in the database, including other students'. `attempt_id` is
  an optional client-supplied filter, not a scope. (`/answers/{id}` *does*
  check ownership.) No UI calls it.
- `GET /attempts/{id}/report.pdf` fetches media over the network
  **synchronously in the handler**, blocking the event loop; a slow media host
  stalls the worker.
- `settings.FRONTEND_URL` and `settings.DEFAULT_USER_LEVEL` are defined but
  never read. `ALL_CORS_ORIGINS` is only used as an on/off flag — the actual
  origin list is hardcoded `["*"]`.
