# Serves the whole app from one process: the FastAPI API plus the React SPA,
# mounted onto the same ASGI app object in app/backend/main.py.
#
# The SPA is built in the node stage below and copied into
# app/backend/static/web; the app stage mounts it as static files and ships
# no Node runtime itself.

# ---------------------------------------------------------------- web build
FROM node:22-bookworm-slim AS web

# corepack activates the pnpm version pinned in app/web/package.json.
RUN corepack enable

WORKDIR /web

# Copy the manifests first so the dependency layer caches independently of
# source changes.
COPY app/web/package.json app/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY app/web/ ./
# Writes to ../backend/static/web by default (see vite.config.ts); point it at
# a stage-local directory instead, since app/backend does not exist here.
RUN pnpm exec tsc --noEmit \
    && pnpm exec vite build --outDir /web/dist --emptyOutDir

# ---------------------------------------------------------------- app
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
# The whole repo, not just app/backend: this is a uv workspace, so `uv sync`
# needs every member's manifest present to resolve, and app/shared
# (quiz_shared) is a real runtime dependency of the backend.
COPY . .
RUN uv sync --frozen --package quiz-backend

# After COPY . ., so it is not clobbered. .dockerignore excludes
# app/backend/static, so nothing built locally leaks into the image — this
# stage's output is the only SPA bundle present.
COPY --from=web /web/dist ./app/backend/static/web

# alembic.ini + prepend_sys_path require cwd = app/backend (env.py imports
# app.core.config and db_models relative to this directory).
WORKDIR /app/app/backend

# `alembic upgrade head` brings an existing DB to the latest revision and
# fully creates the schema on a fresh DB (initial_schema revision). The app
# additionally runs SQLModel create_all in its lifespan as a no-op safety net.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn main:app --host 0.0.0.0 --port 8000"]
