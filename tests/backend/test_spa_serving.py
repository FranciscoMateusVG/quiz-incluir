"""React replacement: actual static mount with no DB/auth/provider I/O."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx
from fastapi import FastAPI
from sqladmin import Admin
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.admin.auth import AdminAuth
from app.core.client_ip import (
    PreserveOriginalPeerMiddleware,
    parse_trusted_proxy_cidrs,
)
from app.core.database import engine
from app.core.spa import SpaStaticFiles


class SpaServingTests(unittest.IsolatedAsyncioTestCase):
    async def test_sqladmin_urls_use_only_a_trusted_forwarded_scheme(self):
        app = FastAPI(openapi_url=None)
        Admin(
            app,
            engine,
            base_url="/backoffice",
            authentication_backend=AdminAuth(secret_key="test-only-secret"),
        )

        trusted_app = PreserveOriginalPeerMiddleware(
            app, parse_trusted_proxy_cidrs("10.24.0.7/32")
        )
        transport = httpx.ASGITransport(
            app=trusted_app, client=("10.24.0.7", 43123)
        )
        async with httpx.AsyncClient(
            transport=transport, base_url="http://quiz.test"
        ) as client:
            response = await client.get(
                "/backoffice/login", headers={"x-forwarded-proto": "https"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(
                'href="https://quiz.test/backoffice/statics/css/', response.text
            )
            self.assertIn(
                'action="https://quiz.test/backoffice/login"', response.text
            )
            self.assertNotIn("http://quiz.test/backoffice", response.text)

            redirect = await client.get(
                "/backoffice/",
                headers={"x-forwarded-proto": "https"},
                follow_redirects=False,
            )
            self.assertEqual(redirect.status_code, 302)
            self.assertEqual(
                redirect.headers["location"],
                "https://quiz.test/backoffice/login",
            )

        untrusted_transport = httpx.ASGITransport(
            app=trusted_app, client=("198.51.100.90", 43123)
        )
        async with httpx.AsyncClient(
            transport=untrusted_transport, base_url="http://quiz.test"
        ) as client:
            response = await client.get(
                "/backoffice/login",
                headers={
                    "x-forwarded-proto": "https",
                    "x-forwarded-host": "spoofed.invalid",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(
                'href="http://quiz.test/backoffice/statics/css/', response.text
            )
            self.assertIn(
                'action="http://quiz.test/backoffice/login"', response.text
            )
            self.assertNotIn("spoofed.invalid", response.text)

    async def test_deep_routes_assets_and_reserved_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath('index.html').write_text('react-fixture')
            root.joinpath('asset.js').write_text('fixture-script')
            app = FastAPI(openapi_url=None)
            app.mount('/', SpaStaticFiles(directory=root, html=True))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                for path in ['/', '/quizzes', '/quiz/2', '/admin/grades/fixture']:
                    response = await client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.text, 'react-fixture')
                for path in ['/api/v1/missing', '/backoffice/missing', '/docs', '/redoc', '/openapi.json', '/missing.js']:
                    self.assertEqual((await client.get(path)).status_code, 404)
                self.assertEqual((await client.get('/asset.js')).text, 'fixture-script')

    async def test_actual_entrypoint_preserves_auth_handler_peer_middleware_and_db_lifecycle(self):
        import importlib.util
        from unittest.mock import AsyncMock, patch
        from app.api.auth_errors import AuthAPIError, auth_api_error_handler
        from app.core.client_ip import PreserveOriginalPeerMiddleware
        from app.core.config import settings
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location('quiz_react_backend_main', root / 'app/backend/main.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIs(module.app.exception_handlers[AuthAPIError], auth_api_error_handler)
        peer_middleware = next(
            item
            for item in module.app.user_middleware
            if item.cls is PreserveOriginalPeerMiddleware
        )
        self.assertEqual(
            tuple(peer_middleware.kwargs["trusted_proxy_cidrs"]),
            settings.trusted_proxy_networks,
        )
        self.assertFalse(
            any(item.cls is SessionMiddleware for item in module.app.user_middleware)
        )
        session_middleware = next(
            item
            for item in module.admin.admin.user_middleware
            if item.cls is SessionMiddleware
        )
        self.assertEqual(
            session_middleware.kwargs,
            {
                "secret_key": settings.SECRET_KEY,
                "session_cookie": "quiz_backoffice_session",
                "max_age": 1800,
                "path": "/backoffice",
                "same_site": "strict",
                "https_only": True,
            },
        )
        cors_middleware = next(
            item for item in module.app.user_middleware if item.cls is CORSMiddleware
        )
        self.assertEqual(cors_middleware.kwargs["allow_origins"], ["https://quiz.test"])
        self.assertTrue(cors_middleware.kwargs["allow_credentials"])
        self.assertFalse(hasattr(module, 'flet_app'))
        with patch.object(module, 'init_db', new=AsyncMock()) as initialize:
            async with module.app.router.lifespan_context(module.app):
                initialize.assert_awaited_once()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url='http://test') as client:
            self.assertEqual((await client.get('/quizzes')).status_code, 200)
            self.assertEqual((await client.get('/backoffice')).status_code, 307)
            response = await client.post('/api/v1/auth/token', json={})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()['code'], 'invalid_request')

    async def test_actual_backoffice_cookie_and_cors_boundaries(self):
        import importlib.util
        import os

        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location(
            "quiz_react_backend_security_boundaries",
            root / "app/backend/main.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=module.app),
            base_url="https://quiz.test",
            follow_redirects=False,
        ) as client:
            login = await client.post(
                "/backoffice/login",
                data={
                    "username": os.environ["ADMIN_USERNAME"],
                    "password": os.environ["ADMIN_PASSWORD"],
                },
            )
            self.assertEqual(login.status_code, 302)
            cookie = login.headers["set-cookie"].lower()
            self.assertIn("quiz_backoffice_session=", cookie)
            self.assertIn("path=/backoffice", cookie)
            self.assertIn("max-age=1800", cookie)
            self.assertIn("httponly", cookie)
            self.assertIn("samesite=strict", cookie)
            self.assertIn("secure", cookie)

            spa = await client.get("/quizzes")
            api = await client.post("/api/v1/auth/token", json={})
            self.assertNotIn("cookie", spa.request.headers)
            self.assertNotIn("cookie", api.request.headers)
            self.assertNotIn("set-cookie", spa.headers)
            self.assertNotIn("set-cookie", api.headers)

            logout = await client.get("/backoffice/logout")
            self.assertEqual(logout.status_code, 302)
            expired = logout.headers["set-cookie"].lower()
            self.assertIn("quiz_backoffice_session=null", expired)
            self.assertIn("path=/backoffice", expired)
            self.assertIn("expires=thu, 01 jan 1970", expired)

            allowed = await client.post(
                "/api/v1/auth/token",
                headers={"origin": "https://quiz.test"},
                json={},
            )
            self.assertEqual(
                allowed.headers.get("access-control-allow-origin"),
                "https://quiz.test",
            )
            self.assertEqual(
                allowed.headers.get("access-control-allow-credentials"), "true"
            )

            unlisted = await client.post(
                "/api/v1/auth/token",
                headers={"origin": "https://evil.example"},
                json={},
            )
            self.assertNotIn("access-control-allow-origin", unlisted.headers)

            preflight = await client.options(
                "/api/v1/auth/token",
                headers={
                    "origin": "https://quiz.test",
                    "access-control-request-method": "GET",
                },
            )
            self.assertEqual(preflight.status_code, 200)
            self.assertEqual(
                preflight.headers.get("access-control-allow-origin"),
                "https://quiz.test",
            )

            rejected_preflight = await client.options(
                "/api/v1/auth/token",
                headers={
                    "origin": "https://evil.example",
                    "access-control-request-method": "GET",
                },
            )
            self.assertEqual(rejected_preflight.status_code, 400)
            self.assertNotIn(
                "access-control-allow-origin", rejected_preflight.headers
            )
