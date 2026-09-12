"""React replacement: actual static mount with no DB/auth/provider I/O."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import httpx
from fastapi import FastAPI
from app.core.spa import SpaStaticFiles

class SpaServingTests(unittest.IsolatedAsyncioTestCase):
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
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location('quiz_react_backend_main', root / 'app/backend/main.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIs(module.app.exception_handlers[AuthAPIError], auth_api_error_handler)
        self.assertTrue(any(item.cls is PreserveOriginalPeerMiddleware for item in module.app.user_middleware))
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
