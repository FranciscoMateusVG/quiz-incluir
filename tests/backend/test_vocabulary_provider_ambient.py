"""Ambient OpenAI configuration must not influence the vocabulary adapter."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "app" / "backend"
SHARED_ROOT = REPO_ROOT / "app" / "shared"
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(SHARED_ROOT))

from app.core import vocabulary_provider  # noqa: E402


FORBIDDEN_AMBIENT_VARIABLES = (
    "OPENAI_ORG_ID",
    "OPENAI_PROJECT_ID",
    "OPENAI_ADMIN_KEY",
    "OPENAI_CUSTOM_HEADERS",
    "OPENAI_LOG",
    "OPENAI_BASE_URL",
)


class AmbientProviderConfigurationTests(unittest.IsolatedAsyncioTestCase):
    def test_application_settings_fail_before_sdk_import(self) -> None:
        script = """
import sys

try:
    from app.core import config  # noqa: F401
except Exception as exc:
    assert "unsupported ambient OpenAI configuration" in str(exc)
    assert "openai" not in sys.modules
else:
    raise AssertionError("ambient provider control did not fail startup")
"""
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OPENAI_")
        }
        environment.update(
            {
                "OPENAI_LOG": "debug",
                "PYTHONPATH": os.pathsep.join((str(BACKEND_ROOT), str(SHARED_ROOT))),
            }
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_openai_log_cannot_run_sdk_import_time_configuration(self) -> None:
        script = """
import logging
import sys

before = (logging.getLogger().level, tuple(logging.getLogger().handlers))
from app.core import vocabulary_provider
after = (logging.getLogger().level, tuple(logging.getLogger().handlers))

assert "openai" not in sys.modules
assert before == after
assert vocabulary_provider._ambient_openai_variables() == ("OPENAI_LOG",)
"""
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OPENAI_")
        }
        environment.update(
            {
                "OPENAI_LOG": "debug",
                "PYTHONPATH": os.pathsep.join((str(BACKEND_ROOT), str(SHARED_ROOT))),
            }
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_each_ambient_control_fails_before_sdk_import(self) -> None:
        for variable in FORBIDDEN_AMBIENT_VARIABLES:
            with self.subTest(variable=variable):
                environment = {
                    "OPENAI_API_KEY": "allowed-provider-key",
                    variable: "hostile-ambient-value",
                }
                with (
                    patch.dict(os.environ, environment, clear=True),
                    patch.object(
                        vocabulary_provider.importlib, "import_module"
                    ) as sdk_import,
                    self.assertRaises(
                        vocabulary_provider.ProviderUnavailable
                    ) as raised,
                ):
                    vocabulary_provider._import_openai_sdk()
                sdk_import.assert_not_called()
                self.assertEqual(
                    str(raised.exception),
                    "ambient provider configuration is forbidden",
                )
                self.assertTrue(raised.exception.charge_known_absent)

    async def test_lookup_rejects_ambient_controls_before_prompt_or_client(
        self,
    ) -> None:
        adapter = vocabulary_provider.OpenAIVocabularyProvider("explicit-test-key")
        for variable in FORBIDDEN_AMBIENT_VARIABLES:
            with self.subTest(variable=variable):
                with (
                    patch.dict(
                        os.environ,
                        {
                            "OPENAI_API_KEY": "ignored-environment-key",
                            variable: "hostile-ambient-value",
                        },
                        clear=True,
                    ),
                    patch.object(
                        vocabulary_provider, "_lookup_parameters"
                    ) as build_prompt,
                    patch.object(
                        vocabulary_provider, "_new_provider_http_client"
                    ) as build_http_client,
                    patch.object(vocabulary_provider, "AsyncOpenAI") as build_sdk,
                    self.assertRaises(vocabulary_provider.ProviderUnavailable),
                ):
                    await adapter.lookup("private prompt must not be logged")
                build_prompt.assert_not_called()
                build_http_client.assert_not_called()
                build_sdk.assert_not_called()

    async def test_pronunciation_rejects_ambient_headers_before_client(self) -> None:
        adapter = vocabulary_provider.OpenAIVocabularyProvider("explicit-test-key")
        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "ignored-environment-key",
                    "OPENAI_CUSTOM_HEADERS": '{"X-Leak":"server text"}',
                },
                clear=True,
            ),
            patch.object(
                vocabulary_provider, "_new_provider_http_client"
            ) as build_http_client,
            patch.object(vocabulary_provider, "AsyncOpenAI") as build_sdk,
            self.assertRaises(vocabulary_provider.ProviderUnavailable),
        ):
            await adapter.pronounce("server-owned translation")
        build_http_client.assert_not_called()
        build_sdk.assert_not_called()

    def test_api_key_is_the_only_permitted_openai_environment_variable(self) -> None:
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "allowed-provider-key"},
            clear=True,
        ):
            self.assertEqual(vocabulary_provider._ambient_openai_variables(), ())


if __name__ == "__main__":
    unittest.main()
