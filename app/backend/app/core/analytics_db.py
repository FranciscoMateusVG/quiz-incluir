"""DuckDB-backed analytics queries over the live Postgres database.

Used only by the admin grades dashboard (``app/api/routes/admin.py``).
DuckDB's ``postgres`` extension lets us ``ATTACH`` the same Postgres database
the app already uses and query it directly with SQL, without copying or
caching anything — every query re-reads current Postgres state, which is
what makes the dashboard "real-time" (the frontend then polls these
endpoints on an interval to keep the view fresh).

This is a separate path from the rest of the app's SQLAlchemy/asyncpg async
engine (``app.core.database``) — it exists purely for ad hoc analytical
aggregation, not for transactional reads/writes.
"""

from __future__ import annotations

import duckdb

from app.core.config import settings


def _pg_conninfo() -> str:
    """Strip the ``+asyncpg`` driver suffix; DuckDB's postgres scanner speaks libpq."""
    url = settings.DATABASE_URL
    if "+asyncpg" in url:
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    return url


def get_analytics_connection() -> duckdb.DuckDBPyConnection:
    """Open a fresh in-memory DuckDB connection, ATTACHed to Postgres as ``pg``.

    Opened per-call rather than cached/pooled: these are low-QPS admin-only
    endpoints, so a short-lived connection avoids any staleness or
    connection-lifecycle complexity. Callers are responsible for closing it
    (typically via a ``try/finally`` in the same sync function, since this
    must run inside a worker thread — DuckDB's Python client is sync).
    """
    con = duckdb.connect(":memory:")
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{_pg_conninfo()}' AS pg (TYPE POSTGRES, READ_ONLY)")
    return con
