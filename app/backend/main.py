from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqladmin import Admin
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.admin.auth import AdminAuth
from app.admin.views import ALL_VIEWS
from app.api.main import api_router
from app.core.config import settings
from app.core.database import engine, init_db


API_V1_STR = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Quiz",
    openapi_url=f"{API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

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

admin = Admin(app, engine, authentication_backend=AdminAuth(secret_key=settings.SECRET_KEY))
for view in ALL_VIEWS:
    admin.add_view(view)
