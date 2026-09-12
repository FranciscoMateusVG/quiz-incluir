"""Static file serving for the React SPA (``app/web``).

Starlette's :class:`~starlette.staticfiles.StaticFiles` has no SPA rewrite:
``html=True`` resolves ``/`` to ``index.html``, but any unknown deep path (say
``/quiz/2`` or ``/admin/grades/<uuid>`` on a hard refresh) is a 404, because
those routes only exist in the client-side router.

:class:`SpaStaticFiles` adds the fallback: fall back to ``index.html`` only
when the requested path has no extension or ends in ``.html``. That
distinction matters — a missing ``.js`` or ``.css`` must keep 404ing, because
answering it with HTML turns a stale asset reference into a confusing
MIME-type error in the browser instead of an obvious missing-file error.
"""

from __future__ import annotations

import os
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

# Extensions that mean "this was a navigation, not an asset request".
_DOCUMENT_SUFFIXES = frozenset({"", ".html"})


class SpaStaticFiles(StaticFiles):
    """``StaticFiles`` that serves ``index.html`` for client-side routes."""

    async def get_response(self, path: str, scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            if os.path.splitext(path)[1].lower() not in _DOCUMENT_SUFFIXES:
                raise
            return await super().get_response("index.html", scope)


def spa_dist_dir(backend_dir: Path) -> Path:
    """Where ``pnpm --dir app/web build`` writes its output."""
    return backend_dir / "static" / "web"
