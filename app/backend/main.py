import importlib.util
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import flet.fastapi as flet_fastapi
from fastapi import FastAPI
from sqladmin import Admin
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.admin.auth import AdminAuth
from app.admin.views import ALL_VIEWS
from app.api.auth_errors import AuthAPIError, auth_api_error_handler
from app.api.main import api_router
from app.core.client_ip import (
    CanonicalFletClientIpMiddleware,
    PreserveOriginalPeerMiddleware,
)
from app.core.config import settings
from app.core.database import engine, init_db


API_V1_STR = "/api/v1"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        # flet_fastapi.app() returns a sub-application, so its manager is not
        # started automatically by the parent FastAPI lifespan. The manager
        # owns disconnected-session expiry and temporary-resource cleanup.
        await flet_fastapi.app_manager.start()
        yield
    except BaseException:
        try:
            await flet_fastapi.app_manager.shutdown()
        except Exception:
            # Teardown must not replace the startup/runtime failure that caused
            # it. The original exception remains the actionable one.
            logger.exception("Flet app-manager cleanup failed")
        raise
    else:
        # Normal shutdown is allowed to report its own teardown failure.
        await flet_fastapi.app_manager.shutdown()


app = FastAPI(
    title="Quiz",
    openapi_url=None,
    lifespan=lifespan,
)
app.add_exception_handler(AuthAPIError, auth_api_error_handler)

# Set all CORS enabled origins
if settings.ALL_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Session cookies for the SQLAdmin login below.
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
# Uvicorn runs with proxy-header rewriting disabled. Capture the untouched
# socket peer once, before the mounted Flet app canonicalizes its WebSocket
# scope for Page.client_ip.
app.add_middleware(PreserveOriginalPeerMiddleware)

app.include_router(api_router, prefix=API_V1_STR)

admin = Admin(
    app, engine, authentication_backend=AdminAuth(secret_key=settings.SECRET_KEY)
)
for view in ALL_VIEWS:
    admin.add_view(view)

# Mount the Flet UI last: a root mount is a catch-all, so it must sit behind
# the API and admin routes registered above or it would shadow them. The
# frontend is a flat, unpackaged source tree (see app/frontend/pyproject.toml)
# that assumes it's sys.path[0] (bare `import config`, `from router import
# make_app`, etc.), so it's added to sys.path here and loaded under a distinct
# module name — "main" is already taken by this file.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

_frontend_main_spec = importlib.util.spec_from_file_location(
    "quiz_frontend_main", FRONTEND_DIR / "main.py"
)
_frontend_main = importlib.util.module_from_spec(_frontend_main_spec)
_frontend_main_spec.loader.exec_module(_frontend_main)

flet_app = flet_fastapi.app(
    main=_frontend_main.main,
    assets_dir=str(FRONTEND_DIR / "assets"),
    no_cdn=True,
    session_timeout_seconds=settings.FLET_SESSION_TIMEOUT_SECONDS,
)
# flet.fastapi.app() builds its own bare FastAPI() instance under the hood
# with the default docs/openapi routes still enabled — strip those so
# mounting the UI at "/" doesn't reopen the docs this app just disabled above.
flet_app.router.routes = [
    route
    for route in flet_app.router.routes
    if getattr(route, "path", None) not in ("/docs", "/redoc", "/openapi.json")
]
app.mount(
    "/",
    CanonicalFletClientIpMiddleware(
        flet_app, trusted_proxy_cidrs=settings.trusted_proxy_networks
    ),
)
