# Serves the whole app: the FastAPI API and the Flet UI, mounted onto the
# same ASGI app object in app/backend/main.py (which loads app/frontend at
# import time, hence COPY . . below rather than just app/backend).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
COPY . .
RUN uv sync --frozen --package quiz-backend

# alembic.ini + prepend_sys_path require cwd = app/backend (env.py imports
# app.core.config and db_models relative to this directory).
WORKDIR /app/app/backend

# `alembic upgrade head` brings an existing DB to the latest revision and
# fully creates the schema on a fresh DB (initial_schema revision). The app
# additionally runs SQLModel create_all in its lifespan as a no-op safety net.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn main:app --host 0.0.0.0 --port 8000"]
