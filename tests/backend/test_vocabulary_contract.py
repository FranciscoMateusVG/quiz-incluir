"""Phase B contract tests for vocabulary lookup and pronunciation.

Every external dependency is replaced with a deterministic fake.  In
particular, this module never imports provider credentials and never makes a
network call to an AI provider.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import unittest
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from pydantic import ValidationError
from starlette.requests import Request


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app" / "backend"))
sys.path.insert(0, str(REPO_ROOT / "app" / "shared"))

vocabulary_routes = importlib.import_module("app.api.routes.vocabulary")
vocabulary_core = importlib.import_module("app.core.vocabulary")
vocabulary_provider = importlib.import_module("app.core.vocabulary_provider")

from app.api.auth_errors import (  # noqa: E402
    AuthAPIError,
    auth_api_error_handler,
)
from app.api.deps import get_current_user  # noqa: E402
from quiz_shared.schemas import (  # noqa: E402
    AuthErrorCode,
    PronunciationRequest,
    VocabularyErrorCode,
    VocabularyErrorResponse,
    VocabularyLookupRequest,
    VocabularyLookupResponse,
)


LOOKUP_ID = "11111111-1111-4111-8111-111111111111"
LOOKUP_UUID = UUID(LOOKUP_ID)


@cache
def _unsafe_contract_characters() -> tuple[str, ...]:
    """Return every code point class the wire contract explicitly forbids."""

    return (
        *(chr(codepoint) for codepoint in range(0x20)),
        *(chr(codepoint) for codepoint in range(0x7F, 0xA0)),
        "\u2028",
        "\u2029",
        *(
            chr(codepoint)
            for codepoint in range(sys.maxunicode + 1)
            if unicodedata.category(chr(codepoint)) == "Cf"
        ),
    )


def _lookup_response(
    *, source_text: str = "casa", lookup_id: str = LOOKUP_ID
) -> VocabularyLookupResponse:
    return VocabularyLookupResponse(
        lookup_id=lookup_id,
        source_text=source_text,
        translation="house",
        definition="A building where people live.",
    )


class _FakeVocabularyService:
    def __init__(self) -> None:
        self.lookup_result = _lookup_response()
        self.audio = b"ID3\x04\x00\x00fake-mp3"
        self.lookup_error: Exception | None = None
        self.pronunciation_error: Exception | None = None
        self.lookup_calls: list[tuple[object, str]] = []
        self.pronunciation_calls: list[tuple[object, UUID]] = []

    async def lookup(self, user_id: object, text: str) -> VocabularyLookupResponse:
        self.lookup_calls.append((user_id, text))
        if self.lookup_error is not None:
            raise self.lookup_error
        return self.lookup_result

    async def pronounce(self, user_id: object, lookup_id: UUID) -> bytes:
        self.pronunciation_calls.append((user_id, lookup_id))
        if self.pronunciation_error is not None:
            raise self.pronunciation_error
        return self.audio


class _OwnershipCheckingService(_FakeVocabularyService):
    def __init__(self) -> None:
        super().__init__()
        self.owners: dict[UUID, object] = {}
        self.expired: set[UUID] = set()

    async def pronounce(self, user_id: object, lookup_id: UUID) -> bytes:
        self.pronunciation_calls.append((user_id, lookup_id))
        if lookup_id in self.expired or self.owners.get(lookup_id) != user_id:
            raise vocabulary_routes.VocabularyAPIError(
                422,
                VocabularyErrorCode.INVALID_INPUT,
                "Consulta inválida ou expirada.",
            )
        return self.audio


@dataclass(frozen=True)
class _CachedProviderResult:
    """Semantic provider output intentionally has no request display text."""

    translation: str
    definition: str


class _FakeBudget:
    def __init__(self) -> None:
        self.daily_calls: list[tuple[UUID, str]] = []
        self.reserve_calls: list[tuple[str, int]] = []
        self.commit_calls: list[tuple[UUID, int]] = []
        self.release_calls: list[UUID] = []

    async def consume_daily(self, user_id: UUID, operation: str) -> None:
        self.daily_calls.append((user_id, operation))

    async def reserve(self, operation: str, amount: int) -> object:
        self.reserve_calls.append((operation, amount))
        return SimpleNamespace(id=uuid4())

    async def commit(self, reservation_id: UUID, amount: int) -> None:
        self.commit_calls.append((reservation_id, amount))

    async def release(self, reservation_id: UUID) -> None:
        self.release_calls.append(reservation_id)


class _FakeGrants:
    def __init__(self) -> None:
        self.create_calls: list[tuple[UUID, str]] = []
        self.resolve_calls: list[tuple[UUID, UUID]] = []
        self.translations: dict[tuple[UUID, UUID], str] = {}

    async def create(self, user_id: UUID, translation: str) -> UUID:
        self.create_calls.append((user_id, translation))
        lookup_id = uuid4()
        self.translations[(user_id, lookup_id)] = translation
        return lookup_id

    async def resolve(self, user_id: UUID, lookup_id: UUID) -> str:
        self.resolve_calls.append((user_id, lookup_id))
        return self.translations[(user_id, lookup_id)]


class _NeverReturningDailyBudget(_FakeBudget):
    async def consume_daily(self, user_id: UUID, operation: str) -> None:
        self.daily_calls.append((user_id, operation))
        await asyncio.Event().wait()


class _UnavailableReservationBudget(_FakeBudget):
    async def reserve(self, operation: str, amount: int) -> object:
        self.reserve_calls.append((operation, amount))
        raise vocabulary_core.BudgetUnavailable("configured limit mismatch")


class _NeverReturningGrantResolve(_FakeGrants):
    async def resolve(self, user_id: UUID, lookup_id: UUID) -> str:
        self.resolve_calls.append((user_id, lookup_id))
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class _NeverReturningGrantCreate(_FakeGrants):
    async def create(self, user_id: UUID, translation: str) -> UUID:
        self.create_calls.append((user_id, translation))
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class _FakeProvider:
    def __init__(self) -> None:
        self.lookup_calls: list[str] = []
        self.pronunciation_calls: list[str] = []

    async def lookup(self, text: str):
        self.lookup_calls.append(text)
        return vocabulary_provider.ProviderLookupResult(
            translation="house",
            definition="A building where people live.",
            input_tokens=8,
            output_tokens=12,
        )

    async def pronounce(self, translation: str) -> bytes:
        self.pronunciation_calls.append(translation)
        return b"ID3\x04\x00\x00fake-mp3"


class _TranslationProvider(_FakeProvider):
    def __init__(self, translation: str) -> None:
        super().__init__()
        self.translation = translation

    async def lookup(self, text: str):
        self.lookup_calls.append(text)
        return vocabulary_provider.ProviderLookupResult(
            translation=self.translation,
            definition="A safe definition.",
            input_tokens=8,
            output_tokens=12,
        )


class _BlockingProvider(_FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.active = 0
        self.maximum_active = 0
        self.first_active = asyncio.Event()
        self.four_active = asyncio.Event()
        self.release = asyncio.Event()

    async def _block(self) -> None:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.first_active.set()
        if self.active == 4:
            self.four_active.set()
        try:
            await self.release.wait()
        finally:
            self.active -= 1

    async def lookup(self, text: str):
        self.lookup_calls.append(text)
        await self._block()
        return vocabulary_provider.ProviderLookupResult(
            translation="house",
            definition="A building where people live.",
            input_tokens=8,
            output_tokens=12,
        )

    async def pronounce(self, translation: str) -> bytes:
        self.pronunciation_calls.append(translation)
        await self._block()
        return b"ID3\x04\x00\x00fake-mp3"


class _FakeStreamingResponse:
    def __init__(self, body: bytes, content_type: str) -> None:
        self.body = body
        self.headers = httpx.Headers({"content-type": content_type})

    async def iter_bytes(self):
        yield self.body[:7]
        yield self.body[7:]

    async def aiter_bytes(self):
        async for chunk in self.iter_bytes():
            yield chunk


class _FakeAsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False


class _FakeCreateEndpoint:
    def __init__(self, response: _FakeStreamingResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeAsyncContext(self.response)


class _FakeOpenAIClient:
    def __init__(self) -> None:
        lookup_body = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "translation": "house",
                                    "definition": "A building where people live.",
                                }
                            ),
                            "refusal": None,
                        }
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 12},
            }
        ).encode()
        self.lookup = _FakeCreateEndpoint(
            _FakeStreamingResponse(lookup_body, "application/json")
        )
        self.speech = _FakeCreateEndpoint(
            _FakeStreamingResponse(b"ID3\x04\x00\x00audio", "audio/mpeg")
        )
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(with_streaming_response=self.lookup)
        )
        self.audio = SimpleNamespace(
            speech=SimpleNamespace(with_streaming_response=self.speech)
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


def _endpoint_app(
    service: _FakeVocabularyService,
    *,
    authenticated: bool = True,
) -> tuple[FastAPI, object]:
    app = FastAPI()
    app.add_exception_handler(AuthAPIError, auth_api_error_handler)
    app.add_exception_handler(
        vocabulary_routes.VocabularyAPIError,
        vocabulary_routes.vocabulary_api_error_handler,
    )
    app.include_router(
        vocabulary_routes.router,
        prefix="/api/v1/vocabulary",
    )

    user = SimpleNamespace(id=uuid4())

    if authenticated:

        async def current_user():
            return user
    else:

        async def current_user():
            raise AuthAPIError(
                401,
                AuthErrorCode.AUTH_REQUIRED,
                "Autenticação necessária.",
            )

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[vocabulary_routes.get_vocabulary_service] = lambda: service
    return app, user


async def _request(
    app: FastAPI,
    method: str,
    path: str,
    **kwargs,
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://quiz.test",
    ) as client:
        return await client.request(method, path, **kwargs)


def _streaming_json_request(chunks: tuple[bytes, ...]) -> Request:
    position = 0

    async def receive():
        nonlocal position
        if position >= len(chunks):
            return {"type": "http.disconnect"}
        chunk = chunks[position]
        position += 1
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": position < len(chunks),
        }

    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/vocabulary/lookup",
            "raw_path": b"/api/v1/vocabulary/lookup",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 40000),
            "server": ("quiz.test", 80),
        },
        receive,
    )


class VocabularySchemaTests(unittest.TestCase):
    def test_lookup_and_pronunciation_requests_are_exact_objects(self) -> None:
        self.assertEqual(VocabularyLookupRequest(text="casa").text, "casa")
        self.assertEqual(
            str(PronunciationRequest(lookup_id=LOOKUP_ID).lookup_id),
            LOOKUP_ID,
        )

        invalid_payloads = (
            (VocabularyLookupRequest, {}),
            (VocabularyLookupRequest, {"text": 7}),
            (VocabularyLookupRequest, {"text": "casa", "extra": True}),
            (PronunciationRequest, {}),
            (PronunciationRequest, {"lookup_id": 7}),
            (PronunciationRequest, {"lookup_id": "not-a-uuid"}),
            (
                PronunciationRequest,
                {"lookup_id": LOOKUP_ID, "translation": "house"},
            ),
        )
        for schema, payload in invalid_payloads:
            with self.subTest(schema=schema.__name__, payload=payload):
                with self.assertRaises(ValidationError):
                    schema.model_validate(payload)

    def test_lookup_response_is_strict_and_includes_opaque_lookup_id(self) -> None:
        response = _lookup_response()
        self.assertEqual(
            response.model_dump(mode="json"),
            {
                "lookup_id": LOOKUP_ID,
                "source_text": "casa",
                "translation": "house",
                "definition": "A building where people live.",
            },
        )
        with self.assertRaises(ValidationError):
            VocabularyLookupResponse.model_validate(
                {**response.model_dump(mode="json"), "alternatives": ["home"]}
            )

    def test_response_rejects_blank_oversize_and_unsafe_unicode(self) -> None:
        for field, limit in (
            ("source_text", 120),
            ("translation", 120),
            ("definition", 240),
        ):
            for value in (
                "",
                " " * 2,
                " padded",
                "cafe\u0301",
                "x" * (limit + 1),
                *(
                    f"bad{character}value"
                    for character in _unsafe_contract_characters()
                ),
            ):
                with self.subTest(field=field, value=repr(value)):
                    payload = _lookup_response().model_dump(mode="json")
                    payload[field] = value
                    with self.assertRaises(ValidationError):
                        VocabularyLookupResponse.model_validate(payload)

    def test_public_vocabulary_error_codes_are_stable(self) -> None:
        self.assertEqual(
            {item.value for item in VocabularyErrorCode},
            {
                "invalid_input",
                "no_result",
                "rate_limited",
                "provider_unavailable",
                "invalid_provider_response",
            },
        )

    def test_retry_timing_is_absent_or_within_the_31_day_contract(self) -> None:
        valid = VocabularyErrorResponse(
            code=VocabularyErrorCode.RATE_LIMITED,
            message="Limite atingido.",
            retry_after_seconds=17,
        )
        self.assertEqual(valid.retry_after_seconds, 17)
        for invalid in (0, -1, 2_678_401):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                VocabularyErrorResponse(
                    code=VocabularyErrorCode.RATE_LIMITED,
                    message="Limite atingido.",
                    retry_after_seconds=invalid,
                )


class VocabularyNormalizationTests(unittest.TestCase):
    def test_lookup_normalizes_nfc_outer_and_repeated_whitespace(self) -> None:
        normalize = vocabulary_core.normalize_lookup_text
        self.assertEqual(normalize("  BOM   DIA "), "BOM DIA")
        self.assertEqual(normalize("bom\u00a0\u00a0dia"), "bom dia")
        self.assertEqual(normalize("ac\u0327a\u0303o"), "ação")
        self.assertTrue(unicodedata.is_normalized("NFC", normalize("ação")))

    def test_lookup_rejects_empty_limits_and_all_unsafe_controls(self) -> None:
        rejected = (
            "",
            "   ",
            "x" * 121,
            *(f"bad{character}value" for character in _unsafe_contract_characters()),
        )
        for value in rejected:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                vocabulary_core.normalize_lookup_text(value)

    def test_provider_translation_validator_rejects_instead_of_mutating(self) -> None:
        validate = vocabulary_core.validate_pronunciation_text
        self.assertEqual(validate("good morning"), "good morning")
        rejected = (
            "",
            " house",
            "house ",
            "good  morning",
            "x" * 121,
            *(f"bad{character}value" for character in _unsafe_contract_characters()),
            "cafe\u0301",
        )
        for value in rejected:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                validate(value)


class VocabularyCacheTests(unittest.TestCase):
    def test_cache_key_is_nfc_casefolded_and_whitespace_collapsed(self) -> None:
        now = [1000.0]
        cache = vocabulary_core.VocabularyCache(
            max_entries=2,
            ttl_seconds=10,
            clock=lambda: now[0],
        )
        result = _CachedProviderResult(
            translation="good morning",
            definition="A greeting used in the morning.",
        )
        cache.put("  BOM   DIA ", result)

        self.assertIs(cache.get("bom dia"), result)
        self.assertIs(cache.get("BOM\u00a0DIA"), result)

        now[0] += 11
        self.assertIsNone(cache.get("bom dia"))

    def test_cache_is_bounded_lru_and_stores_no_request_source_casing(self) -> None:
        cache = vocabulary_core.VocabularyCache(max_entries=2, ttl_seconds=60)
        one = _CachedProviderResult("one", "The number one.")
        two = _CachedProviderResult("two", "The number two.")
        three = _CachedProviderResult("three", "The number three.")
        cache.put("um", one)
        cache.put("dois", two)
        self.assertIs(cache.get("UM"), one)  # make `um` most recently used
        cache.put("três", three)
        self.assertIsNone(cache.get("dois"))
        self.assertFalse(hasattr(one, "source_text"))


class PerUserMinuteLimiterTests(unittest.TestCase):
    def test_ten_per_minute_then_retry_and_window_reset(self) -> None:
        now = [1000.0]
        limiter = vocabulary_core.PerUserRateLimiter(
            limit=10,
            window_seconds=60,
            clock=lambda: now[0],
        )
        user_id = uuid4()
        for _ in range(10):
            self.assertIsNone(limiter.consume(user_id, "lookup"))
        self.assertGreaterEqual(limiter.consume(user_id, "lookup"), 1)
        now[0] += 60
        self.assertIsNone(limiter.consume(user_id, "lookup"))

    def test_users_and_lookup_pronunciation_buckets_are_independent(self) -> None:
        limiter = vocabulary_core.PerUserRateLimiter(limit=1, window_seconds=60)
        first_user = uuid4()
        second_user = uuid4()
        self.assertIsNone(limiter.consume(first_user, "lookup"))
        self.assertIsNotNone(limiter.consume(first_user, "lookup"))
        self.assertIsNone(limiter.consume(first_user, "pronunciation"))
        self.assertIsNone(limiter.consume(second_user, "lookup"))


class VocabularyServiceTests(unittest.IsolatedAsyncioTestCase):
    def _service(
        self,
        *,
        provider: object,
        budget: _FakeBudget,
        grants: _FakeGrants,
        cache: object | None = None,
        concurrency: int = 4,
    ):
        return vocabulary_core.VocabularyService(
            provider=provider,
            budget=budget,
            grants=grants,
            cache=cache,
            concurrency=concurrency,
        )

    async def test_absent_provider_is_disabled_before_rate_or_budget_use(self) -> None:
        budget = _FakeBudget()
        grants = _FakeGrants()
        service = self._service(provider=None, budget=budget, grants=grants)

        with self.assertRaises(vocabulary_core.VocabularyServiceError) as raised:
            await service.lookup(uuid4(), "casa")

        self.assertEqual(
            raised.exception.code, VocabularyErrorCode.PROVIDER_UNAVAILABLE
        )
        self.assertEqual(budget.daily_calls, [])
        self.assertEqual(budget.reserve_calls, [])

    async def test_cache_hit_gets_fresh_user_scoped_grant_without_provider_cost(
        self,
    ) -> None:
        provider = _FakeProvider()
        budget = _FakeBudget()
        grants = _FakeGrants()
        cache = vocabulary_core.VocabularyCache()
        cache.put(
            "casa",
            vocabulary_core.CachedVocabularyResult(
                translation="house",
                definition="A building where people live.",
            ),
        )
        service = self._service(
            provider=provider,
            budget=budget,
            grants=grants,
            cache=cache,
        )
        user_id = uuid4()

        first = await service.lookup(user_id, "CASA")
        second = await service.lookup(user_id, "casa")

        self.assertNotEqual(first.lookup_id, second.lookup_id)
        self.assertEqual((first.source_text, second.source_text), ("CASA", "casa"))
        self.assertEqual(
            grants.create_calls,
            [(user_id, "house"), (user_id, "house")],
        )
        self.assertEqual(
            budget.daily_calls,
            [(user_id, "lookup"), (user_id, "lookup")],
        )
        self.assertEqual(provider.lookup_calls, [])
        self.assertEqual(budget.reserve_calls, [])
        self.assertEqual(budget.commit_calls, [])

    async def test_budget_mismatch_fails_before_provider_or_grant(self) -> None:
        provider = _FakeProvider()
        budget = _UnavailableReservationBudget()
        grants = _FakeGrants()
        service = self._service(provider=provider, budget=budget, grants=grants)

        with self.assertRaises(vocabulary_core.VocabularyServiceError) as raised:
            await service.lookup(uuid4(), "casa")

        self.assertEqual(
            raised.exception.code,
            VocabularyErrorCode.PROVIDER_UNAVAILABLE,
        )
        self.assertEqual(len(budget.reserve_calls), 1)
        self.assertEqual(provider.lookup_calls, [])
        self.assertEqual(grants.create_calls, [])

    async def test_identical_cache_misses_share_one_paid_provider_flight(
        self,
    ) -> None:
        provider = _BlockingProvider()
        budget = _FakeBudget()
        grants = _FakeGrants()
        service = self._service(
            provider=provider,
            budget=budget,
            grants=grants,
        )
        first_user = uuid4()
        second_user = uuid4()

        first_task = asyncio.create_task(service.lookup(first_user, "Casa"))
        second_task = asyncio.create_task(service.lookup(second_user, "CASA"))
        await asyncio.wait_for(provider.first_active.wait(), timeout=1)
        await asyncio.sleep(0)
        self.assertEqual(len(provider.lookup_calls), 1)
        provider.release.set()
        first, second = await asyncio.gather(first_task, second_task)

        self.assertEqual((first.source_text, second.source_text), ("Casa", "CASA"))
        self.assertNotEqual(first.lookup_id, second.lookup_id)
        self.assertEqual(len(budget.reserve_calls), 1)
        self.assertEqual(len(budget.commit_calls), 1)
        self.assertCountEqual(
            budget.daily_calls,
            [(first_user, "lookup"), (second_user, "lookup")],
        )
        self.assertCountEqual(
            grants.create_calls,
            [(first_user, "house"), (second_user, "house")],
        )

    async def test_lookup_and_pronunciation_share_four_provider_slots(
        self,
    ) -> None:
        provider = _BlockingProvider()
        budget = _FakeBudget()
        grants = _FakeGrants()
        service = self._service(
            provider=provider,
            budget=budget,
            grants=grants,
            concurrency=4,
        )
        user_id = uuid4()
        lookup_ids = [uuid4() for _ in range(3)]
        for index, lookup_id in enumerate(lookup_ids):
            grants.translations[(user_id, lookup_id)] = f"spoken word {index}"

        tasks = [
            asyncio.create_task(service.lookup(user_id, f"palavra {index}"))
            for index in range(3)
        ]
        tasks.extend(
            asyncio.create_task(service.pronounce(user_id, lookup_id))
            for lookup_id in lookup_ids
        )
        await asyncio.wait_for(provider.four_active.wait(), timeout=1)
        await asyncio.sleep(0.02)

        self.assertEqual(provider.active, 4)
        self.assertEqual(provider.maximum_active, 4)
        self.assertEqual(
            len(provider.lookup_calls) + len(provider.pronunciation_calls),
            4,
        )
        provider.release.set()
        await asyncio.gather(*tasks)
        self.assertEqual(provider.maximum_active, 4)
        self.assertEqual(
            len(provider.lookup_calls) + len(provider.pronunciation_calls),
            6,
        )

    async def test_pronunciation_uses_server_grant_translation_and_user_id(
        self,
    ) -> None:
        provider = _FakeProvider()
        budget = _FakeBudget()
        grants = _FakeGrants()
        service = self._service(
            provider=provider,
            budget=budget,
            grants=grants,
        )
        user_id = uuid4()
        lookup_id = uuid4()
        grants.translations[(user_id, lookup_id)] = "server-owned translation"

        audio = await service.pronounce(user_id, lookup_id)

        self.assertEqual(audio, b"ID3\x04\x00\x00fake-mp3")
        self.assertEqual(grants.resolve_calls, [(user_id, lookup_id)])
        self.assertEqual(provider.pronunciation_calls, ["server-owned translation"])
        self.assertEqual(budget.daily_calls, [(user_id, "pronunciation")])
        self.assertEqual(budget.reserve_calls[0][0], "pronunciation")

    async def test_lookup_never_mints_unpronounceable_translation_grant(self) -> None:
        for translation in ("good  morning", "good\N{NO-BREAK SPACE}morning"):
            with self.subTest(translation=translation):
                provider = _TranslationProvider(translation)
                budget = _FakeBudget()
                grants = _FakeGrants()
                cache = vocabulary_core.VocabularyCache()
                service = self._service(
                    provider=provider,
                    budget=budget,
                    grants=grants,
                    cache=cache,
                )

                with self.assertRaises(
                    vocabulary_core.VocabularyServiceError
                ) as raised:
                    await service.lookup(uuid4(), "bom dia")

                self.assertEqual(
                    raised.exception.code,
                    VocabularyErrorCode.INVALID_PROVIDER_RESPONSE,
                )
                self.assertEqual(grants.create_calls, [])
                self.assertIsNone(cache.get("bom dia"))
                self.assertEqual(provider.lookup_calls, ["bom dia"])

    async def test_complete_lookup_journey_times_out_before_provider(self) -> None:
        provider = _FakeProvider()
        budget = _NeverReturningDailyBudget()
        grants = _FakeGrants()
        service = self._service(provider=provider, budget=budget, grants=grants)

        with (
            patch.object(
                vocabulary_core,
                "VOCABULARY_JOURNEY_DEADLINE_SECONDS",
                0.01,
            ),
            self.assertRaises(vocabulary_core.VocabularyServiceError) as raised,
        ):
            await service.lookup(uuid4(), "casa")

        self.assertEqual(
            raised.exception.code,
            VocabularyErrorCode.PROVIDER_UNAVAILABLE,
        )
        self.assertEqual(provider.lookup_calls, [])
        self.assertEqual(budget.reserve_calls, [])
        self.assertEqual(grants.create_calls, [])

    async def test_complete_pronunciation_journey_times_out_before_provider(
        self,
    ) -> None:
        provider = _FakeProvider()
        budget = _FakeBudget()
        grants = _NeverReturningGrantResolve()
        service = self._service(provider=provider, budget=budget, grants=grants)
        user_id = uuid4()
        lookup_id = uuid4()

        with (
            patch.object(
                vocabulary_core,
                "VOCABULARY_JOURNEY_DEADLINE_SECONDS",
                0.01,
            ),
            self.assertRaises(vocabulary_core.VocabularyServiceError) as raised,
        ):
            await service.pronounce(user_id, lookup_id)

        self.assertEqual(
            raised.exception.code,
            VocabularyErrorCode.PROVIDER_UNAVAILABLE,
        )
        self.assertEqual(grants.resolve_calls, [(user_id, lookup_id)])
        self.assertEqual(provider.pronunciation_calls, [])
        self.assertEqual(budget.daily_calls, [])
        self.assertEqual(budget.reserve_calls, [])

    async def test_cache_hit_grant_creation_is_inside_complete_deadline(self) -> None:
        provider = _FakeProvider()
        budget = _FakeBudget()
        grants = _NeverReturningGrantCreate()
        cache = vocabulary_core.VocabularyCache()
        cache.put(
            "casa",
            vocabulary_core.CachedVocabularyResult(
                translation="house",
                definition="A building where people live.",
            ),
        )
        service = self._service(
            provider=provider,
            budget=budget,
            grants=grants,
            cache=cache,
        )

        with (
            patch.object(
                vocabulary_core,
                "VOCABULARY_JOURNEY_DEADLINE_SECONDS",
                0.01,
            ),
            self.assertRaises(vocabulary_core.VocabularyServiceError) as raised,
        ):
            await service.lookup(uuid4(), "casa")

        self.assertEqual(
            raised.exception.code,
            VocabularyErrorCode.PROVIDER_UNAVAILABLE,
        )
        self.assertEqual(provider.lookup_calls, [])
        self.assertEqual(budget.reserve_calls, [])
        self.assertEqual(len(grants.create_calls), 1)


class ProviderBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_sends_only_fixed_lookup_and_speech_parameters(self) -> None:
        fake_client = _FakeOpenAIClient()
        constructor_calls: list[dict[str, object]] = []

        def client_factory(**kwargs):
            constructor_calls.append(kwargs)
            return fake_client

        with (
            patch.object(
                vocabulary_provider, "AsyncOpenAI", side_effect=client_factory
            ),
            patch.object(
                vocabulary_provider,
                "_new_provider_http_client",
                return_value=object(),
            ),
        ):
            provider = vocabulary_provider.OpenAIVocabularyProvider("test-only")
            lookup = await provider.lookup("casa")
            audio = await provider.pronounce("house")

        self.assertEqual(lookup.translation, "house")
        self.assertEqual(audio, b"ID3\x04\x00\x00audio")
        self.assertEqual(len(constructor_calls), 2)
        for call in constructor_calls:
            self.assertEqual(call["base_url"], "https://api.openai.com/v1")
            self.assertEqual(call["max_retries"], 0)
        lookup_call = fake_client.lookup.calls[0]
        self.assertEqual(lookup_call["model"], "gpt-4o-mini-2024-07-18")
        self.assertEqual(lookup_call["max_completion_tokens"], 256)
        self.assertIs(lookup_call["store"], False)
        self.assertNotIn("user", lookup_call)
        speech_call = fake_client.speech.calls[0]
        self.assertEqual(
            speech_call,
            {
                "model": "tts-1",
                "voice": "alloy",
                "input": "house",
                "response_format": "mp3",
                "speed": 0.9,
            },
        )

    async def test_fixed_transport_and_provider_pins(self) -> None:
        self.assertEqual(
            vocabulary_provider.PROVIDER_BASE_URL,
            "https://api.openai.com/v1",
        )
        self.assertEqual(vocabulary_provider.TEXT_MODEL, "gpt-4o-mini-2024-07-18")
        self.assertEqual(vocabulary_provider.TTS_MODEL, "tts-1")
        self.assertEqual(vocabulary_provider.TTS_VOICE, "alloy")
        self.assertEqual(vocabulary_provider.MAX_COMPLETION_TOKENS, 256)
        self.assertEqual(vocabulary_provider.MAX_PROVIDER_JSON_BYTES, 65_536)
        self.assertEqual(vocabulary_provider.MAX_PROVIDER_AUDIO_BYTES, 2_097_152)
        prompt = vocabulary_provider._lookup_parameters("😀" * 120)
        prompt_bytes = len(
            json.dumps(prompt, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        self.assertLessEqual(
            prompt_bytes,
            vocabulary_provider.MAX_CONSTRUCTED_PROMPT_UTF8_BYTES,
        )
        schema = prompt["response_format"]["json_schema"]["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["translation"]["maxLength"], 120)
        self.assertEqual(schema["properties"]["definition"]["maxLength"], 240)

        client = vocabulary_provider._new_provider_http_client()
        try:
            self.assertEqual(str(client.base_url), "https://api.openai.com/v1/")
            self.assertFalse(client.follow_redirects)
            self.assertFalse(client._trust_env)
            self.assertEqual(client.timeout.connect, 10.0)
            self.assertEqual(client.timeout.read, 10.0)
            self.assertEqual(client.timeout.write, 10.0)
            self.assertEqual(client.timeout.pool, 10.0)
        finally:
            await client.aclose()

    def test_retry_after_is_numeric_positive_and_clamped_to_31_days(self) -> None:
        retry_after = vocabulary_provider._retry_after
        self.assertIsNone(retry_after(httpx.Headers()))
        for invalid in ("0", "-1", "1.5", "tomorrow"):
            with self.subTest(invalid=invalid):
                self.assertIsNone(retry_after(httpx.Headers({"Retry-After": invalid})))
        self.assertEqual(retry_after(httpx.Headers({"Retry-After": "17"})), 17)
        self.assertEqual(
            retry_after(httpx.Headers({"Retry-After": "99999999"})),
            2_678_400,
        )

    def test_mp3_validation_accepts_only_bounded_id3_or_frame_sync(self) -> None:
        validate = vocabulary_provider.is_valid_mp3
        self.assertTrue(validate(b"ID3\x04\x00\x00payload"))
        self.assertTrue(validate(b"\xff\xfbpayload"))
        for invalid in (b"", b"not-mp3", b"\xff\x00payload"):
            with self.subTest(invalid=invalid):
                self.assertFalse(validate(invalid))
        self.assertFalse(
            validate(b"ID3" + b"x" * vocabulary_provider.MAX_PROVIDER_AUDIO_BYTES)
        )


class VocabularyRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_cap_accepts_exact_boundary_and_rejects_multichunk_overflow(
        self,
    ) -> None:
        exact_body = b'{"text":"' + (b" " * 1_009) + b'casa"}'
        self.assertEqual(len(exact_body), 1_024)
        parsed = await vocabulary_routes._read_bounded_json(
            _streaming_json_request((exact_body[:400], exact_body[400:]))
        )
        self.assertEqual(vocabulary_core.normalize_lookup_text(parsed["text"]), "casa")

        oversized = b'{"text":"' + (b"x" * 1_014) + b'"}'
        self.assertEqual(len(oversized), 1_025)
        with self.assertRaises(vocabulary_routes.VocabularyAPIError) as raised:
            await vocabulary_routes._read_bounded_json(
                _streaming_json_request(
                    (oversized[:512], oversized[512:900], oversized[900:])
                )
            )
        self.assertEqual(raised.exception.code, VocabularyErrorCode.INVALID_INPUT)

    async def test_lookup_normalizes_before_service_and_returns_exact_shape(
        self,
    ) -> None:
        service = _FakeVocabularyService()
        service.lookup_result = _lookup_response(source_text="BOM DIA")
        app, user = _endpoint_app(service)

        response = await _request(
            app,
            "POST",
            "/api/v1/vocabulary/lookup",
            json={"text": "  BOM   DIA "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(service.lookup_calls, [(user.id, "BOM DIA")])
        self.assertEqual(response.json(), service.lookup_result.model_dump(mode="json"))

    async def test_service_receives_current_normalized_source_on_repeated_casefold_key(
        self,
    ) -> None:
        service = _FakeVocabularyService()
        app, _user = _endpoint_app(service)

        service.lookup_result = _lookup_response(source_text="bom dia")
        first = await _request(
            app,
            "POST",
            "/api/v1/vocabulary/lookup",
            json={"text": "bom dia"},
        )
        service.lookup_result = _lookup_response(source_text="BOM DIA")
        second = await _request(
            app,
            "POST",
            "/api/v1/vocabulary/lookup",
            json={"text": "BOM DIA"},
        )

        self.assertEqual(first.json()["source_text"], "bom dia")
        self.assertEqual(second.json()["source_text"], "BOM DIA")
        self.assertEqual(
            [text for _user_id, text in service.lookup_calls],
            ["bom dia", "BOM DIA"],
        )

    async def test_pronunciation_accepts_only_lookup_id_and_returns_exact_mp3(
        self,
    ) -> None:
        service = _FakeVocabularyService()
        app, user = _endpoint_app(service)

        response = await _request(
            app,
            "POST",
            "/api/v1/vocabulary/pronunciation",
            json={"lookup_id": LOOKUP_ID},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.content, service.audio)
        self.assertEqual(
            service.pronunciation_calls,
            [(user.id, LOOKUP_UUID)],
        )

        rejected = await _request(
            app,
            "POST",
            "/api/v1/vocabulary/pronunciation",
            json={"lookup_id": LOOKUP_ID, "translation": "attacker text"},
        )
        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(rejected.json()["code"], "invalid_input")
        self.assertEqual(len(service.pronunciation_calls), 1)

    async def test_lookup_id_owner_mismatch_and_expiry_share_local_422(
        self,
    ) -> None:
        service = _OwnershipCheckingService()
        owner_app, owner = _endpoint_app(service)
        other_app, other = _endpoint_app(service)
        lookup_id = LOOKUP_UUID
        service.owners[lookup_id] = owner.id

        owned = await _request(
            owner_app,
            "POST",
            "/api/v1/vocabulary/pronunciation",
            json={"lookup_id": str(lookup_id)},
        )
        cross_user = await _request(
            other_app,
            "POST",
            "/api/v1/vocabulary/pronunciation",
            json={"lookup_id": str(lookup_id)},
        )
        service.expired.add(lookup_id)
        expired = await _request(
            owner_app,
            "POST",
            "/api/v1/vocabulary/pronunciation",
            json={"lookup_id": str(lookup_id)},
        )

        self.assertEqual(owned.status_code, 200)
        self.assertNotEqual(owner.id, other.id)
        for response in (cross_user, expired):
            self.assertEqual(response.status_code, 422)
            self.assertEqual(
                response.json(),
                {
                    "code": "invalid_input",
                    "message": "Consulta inválida ou expirada.",
                },
            )

    async def test_authentication_runs_before_json_read_or_validation(self) -> None:
        service = _FakeVocabularyService()
        app, _user = _endpoint_app(service, authenticated=False)
        huge_malformed_body = b"{" + (b"x" * 2048)

        response = await _request(
            app,
            "POST",
            "/api/v1/vocabulary/lookup",
            content=huge_malformed_body,
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "auth_required")
        self.assertEqual(service.lookup_calls, [])

    async def test_streamed_json_body_is_capped_at_1024_bytes(self) -> None:
        service = _FakeVocabularyService()
        app, _user = _endpoint_app(service)

        response = await _request(
            app,
            "POST",
            "/api/v1/vocabulary/lookup",
            content=b'{"text":"' + (b"x" * 1016) + b'"}',
            headers={"Content-Type": "application/json"},
        )

        self.assertGreater(len(response.request.content), 1024)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "invalid_input")
        self.assertEqual(service.lookup_calls, [])

    async def test_wrong_content_type_malformed_json_and_extra_keys_are_stable_422(
        self,
    ) -> None:
        service = _FakeVocabularyService()
        app, _user = _endpoint_app(service)
        requests = (
            {"content": b'{"text":"casa"}', "headers": {"Content-Type": "text/plain"}},
            {"content": b"not-json", "headers": {"Content-Type": "application/json"}},
            {"json": {"text": "casa", "extra": True}},
            {"json": {"text": "bad\x85value"}},
        )
        for kwargs in requests:
            with self.subTest(kwargs=kwargs):
                response = await _request(
                    app,
                    "POST",
                    "/api/v1/vocabulary/lookup",
                    **kwargs,
                )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(
                    set(response.json()),
                    {"code", "message"},
                )
                self.assertEqual(response.json()["code"], "invalid_input")
        self.assertEqual(service.lookup_calls, [])

    async def test_service_errors_are_stable_sanitized_and_preserve_retry_header(
        self,
    ) -> None:
        cases = (
            (404, VocabularyErrorCode.NO_RESULT, None),
            (429, VocabularyErrorCode.RATE_LIMITED, 17),
            (502, VocabularyErrorCode.INVALID_PROVIDER_RESPONSE, None),
            (503, VocabularyErrorCode.PROVIDER_UNAVAILABLE, None),
        )
        for status_code, code, retry_after in cases:
            with self.subTest(status_code=status_code, code=code):
                service = _FakeVocabularyService()
                service.lookup_error = vocabulary_routes.VocabularyAPIError(
                    status_code,
                    code,
                    "Mensagem segura.",
                    retry_after_seconds=retry_after,
                )
                app, _user = _endpoint_app(service)
                response = await _request(
                    app,
                    "POST",
                    "/api/v1/vocabulary/lookup",
                    json={"text": "casa"},
                )
                expected = {"code": code.value, "message": "Mensagem segura."}
                if retry_after is not None:
                    expected["retry_after_seconds"] = retry_after
                    self.assertEqual(response.headers["retry-after"], "17")
                self.assertEqual(response.status_code, status_code)
                self.assertEqual(response.json(), expected)
                self.assertNotIn("provider", response.json()["message"].lower())

    async def test_empty_audio_is_invalid_provider_response(self) -> None:
        # The endpoint is the last boundary before paid bytes reach the client;
        # it still rejects an empty payload from a custom/injected service.
        service = _FakeVocabularyService()
        service.audio = b""
        app, _user = _endpoint_app(service)
        response = await _request(
            app,
            "POST",
            "/api/v1/vocabulary/pronunciation",
            json={"lookup_id": LOOKUP_ID},
        )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["code"], "invalid_provider_response")


if __name__ == "__main__":
    unittest.main()
