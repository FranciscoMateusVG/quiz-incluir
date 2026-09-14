"""Regression tests for the combined FastAPI/Flet process lifecycle.

Flet 0.86.5 normally owns its app-manager lifespan when it is the outer
application.  Quiz mounts the Flet application under its own FastAPI app, so
the outer lifespan must start and stop that manager explicitly.

These tests deliberately exercise the public FastAPI lifespan context.  They
do not mutate Flet's private session registry; reconnect/eviction behaviour
needs a real Flet WebSocket client and belongs in the staging journey.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import unittest
from importlib.metadata import version
from pathlib import Path
from unittest.mock import AsyncMock, patch

from starlette.routing import WebSocketRoute


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "app" / "backend"

# The backend is a flat application package rather than an installed Python
# package in a source checkout.  Load its entrypoint under an unambiguous name
# so test runners cannot accidentally resolve another top-level ``main``.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_spec = importlib.util.spec_from_file_location(
    "quiz_backend_main_for_lifecycle_tests", BACKEND_DIR / "main.py"
)
assert _spec is not None and _spec.loader is not None
backend_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backend_main)


class CombinedAppLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_outer_fastapi_lifespan_orders_database_flet_and_shutdown(self):
        events: list[str] = []

        async def record_init_db() -> None:
            events.append("init_db")

        async def record_flet_start() -> None:
            events.append("flet_start")

        async def record_flet_shutdown() -> None:
            events.append("flet_shutdown")

        init_db = AsyncMock(side_effect=record_init_db)
        start = AsyncMock(side_effect=record_flet_start)
        shutdown = AsyncMock(side_effect=record_flet_shutdown)

        with (
            patch.object(backend_main, "init_db", init_db),
            patch.object(backend_main.flet_fastapi.app_manager, "start", start),
            patch.object(backend_main.flet_fastapi.app_manager, "shutdown", shutdown),
        ):
            async with backend_main.app.router.lifespan_context(backend_main.app):
                events.append("serving")

        self.assertEqual(
            events,
            ["init_db", "flet_start", "serving", "flet_shutdown"],
        )
        init_db.assert_awaited_once_with()
        start.assert_awaited_once_with()
        shutdown.assert_awaited_once_with()

    async def test_shutdown_failure_does_not_mask_runtime_failure(self):
        runtime_failure = RuntimeError("original runtime failure")
        cleanup_failure = RuntimeError("secondary cleanup failure")

        with (
            patch.object(backend_main, "init_db", new=AsyncMock()),
            patch.object(
                backend_main.flet_fastapi.app_manager,
                "start",
                new=AsyncMock(),
            ),
            patch.object(
                backend_main.flet_fastapi.app_manager,
                "shutdown",
                new=AsyncMock(side_effect=cleanup_failure),
            ) as shutdown,
        ):
            with self.assertLogs(backend_main.logger, level="ERROR"):
                with self.assertRaises(RuntimeError) as raised:
                    async with backend_main.app.router.lifespan_context(
                        backend_main.app
                    ):
                        raise runtime_failure

        self.assertIs(raised.exception, runtime_failure)
        shutdown.assert_awaited_once_with()

    async def test_shutdown_failure_does_not_mask_flet_startup_failure(self):
        startup_failure = RuntimeError("original Flet startup failure")
        cleanup_failure = RuntimeError("secondary cleanup failure")

        with (
            patch.object(backend_main, "init_db", new=AsyncMock()),
            patch.object(
                backend_main.flet_fastapi.app_manager,
                "start",
                new=AsyncMock(side_effect=startup_failure),
            ),
            patch.object(
                backend_main.flet_fastapi.app_manager,
                "shutdown",
                new=AsyncMock(side_effect=cleanup_failure),
            ) as shutdown,
        ):
            with self.assertLogs(backend_main.logger, level="ERROR"):
                with self.assertRaises(RuntimeError) as raised:
                    async with backend_main.app.router.lifespan_context(
                        backend_main.app
                    ):
                        self.fail("the app must not begin serving after startup fails")

        self.assertIs(raised.exception, startup_failure)
        shutdown.assert_awaited_once_with()


class FletConstructionContractTests(unittest.TestCase):
    def test_pinned_flet_receives_configured_session_timeout(self):
        # This assertion makes the lifecycle assumptions above fail loudly when
        # Flet is upgraded; its manager and WebSocket semantics must be reviewed
        # rather than silently inherited from another version.
        self.assertEqual(version("flet"), "0.86.5")

        websocket_routes = [
            route
            for route in backend_main.flet_app.router.routes
            if isinstance(route, WebSocketRoute)
        ]
        self.assertEqual(len(websocket_routes), 1)

        # flet.fastapi.app() closes over its constructor arguments in the
        # public WebSocket endpoint.  Reading the closure proves the configured
        # value reached the Flet application actually mounted by Quiz, rather
        # than merely appearing in source or settings.
        construction_args = inspect.getclosurevars(
            websocket_routes[0].endpoint
        ).nonlocals
        self.assertEqual(
            construction_args["session_timeout_seconds"],
            backend_main.settings.FLET_SESSION_TIMEOUT_SECONDS,
        )


if __name__ == "__main__":
    unittest.main()
