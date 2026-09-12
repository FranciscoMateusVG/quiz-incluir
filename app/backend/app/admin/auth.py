"""Login gate for the SQLAdmin panel, mounted at ``/backoffice``.

Deliberately independent of the app's own user auth, which delegates to the
Programa Incluir monorepo's BetterAuth service (see
``app/core/monorepo_auth.py``) and grants admin rights from a ``users.role``
column that is only ever set by hand — not a gate this surface should depend
on. Credentials come from ``settings.ADMIN_USERNAME`` /
``settings.ADMIN_PASSWORD`` and the session is a signed cookie via
Starlette's ``SessionMiddleware`` (registered in ``main.py``).
"""

from __future__ import annotations

import secrets

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.core.config import settings


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))

        valid = secrets.compare_digest(
            username, settings.ADMIN_USERNAME
        ) and secrets.compare_digest(password, settings.ADMIN_PASSWORD)

        if not valid:
            return False

        request.session["admin_authenticated"] = True
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("admin_authenticated"))
