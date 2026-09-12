from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqladmin import Admin
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from app.admin.auth import AdminAuth
from app.admin.views import ALL_VIEWS
from app.api.auth_errors import AuthAPIError, auth_api_error_handler
from app.core.client_ip import PreserveOriginalPeerMiddleware
from app.api.main import api_router
from app.core.config import settings
from app.core.database import engine, init_db
from app.core.spa import SpaStaticFiles, spa_dist_dir


API_V1_STR = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Quiz",
    openapi_url=None,
    lifespan=lifespan,
)

app.add_exception_handler(AuthAPIError, auth_api_error_handler)
app.add_middleware(PreserveOriginalPeerMiddleware)

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

app.include_router(api_router, prefix=API_V1_STR)

# Mounted at "/backoffice", not the sqladmin default of "/admin".
#
# A sub-app mount wins over the catch-all UI mount below for every path under
# its prefix, so this can't share a prefix with the React router's own
# "/admin/grades" routes — SQLAdmin would answer them with its own 404 instead
# of the SPA ever seeing the request.
BACKOFFICE_URL = "/backoffice"

admin = Admin(
    app,
    engine,
    base_url=BACKOFFICE_URL,
    authentication_backend=AdminAuth(secret_key=settings.SECRET_KEY),
)
for view in ALL_VIEWS:
    admin.add_view(view)


@app.get(BACKOFFICE_URL, include_in_schema=False)
async def backoffice_trailing_slash_redirect() -> RedirectResponse:
    """Starlette only auto-redirects a bare mount path to its trailing-slash
    form when nothing else matches — but the UI mount below matches every
    path, so it always wins over that fallback and "/backoffice" (no slash)
    would otherwise be served by the SPA instead of reaching SQLAdmin."""
    return RedirectResponse(url=f"{BACKOFFICE_URL}/")


# Mount the UI last: a root mount is a catch-all, so it must sit behind the
# API and backoffice routes registered above or it would shadow them.
#
# Nothing Python-side is involved at runtime beyond handing out files:
# `pnpm --dir app/web build` emits static assets into app/backend/static/web,
# and SpaStaticFiles serves them with a fallback so client-side routes
# survive a hard refresh.
BACKEND_DIR = Path(__file__).resolve().parent
DIST = spa_dist_dir(BACKEND_DIR)
if not (DIST / "index.html").is_file():
    raise RuntimeError(
        f"No SPA build found at {DIST}. Run `make web-build` "
        "(or `pnpm --dir app/web build`) first."
    )
app.mount("/", SpaStaticFiles(directory=DIST, html=True), name="spa")
