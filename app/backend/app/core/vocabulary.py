"""Vocabulary normalization, local controls, and provider orchestration."""

from __future__ import annotations

import asyncio
import time
import unicodedata
from collections import OrderedDict, defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.ai_budget import (
    LOOKUP_MAX_INPUT_TOKENS,
    LOOKUP_MAX_OUTPUT_TOKENS,
    LOOKUP_RESERVATION_MICROUSD,
    AIBudgetRepository,
    BudgetExceeded,
    BudgetUnavailable,
    lookup_cost_microusd,
    tts_cost_microusd,
)
from app.core.vocabulary_provider import (
    ProviderFailure,
    ProviderInvalidResponse,
    ProviderLookupResult,
    ProviderNoResult,
    ProviderRateLimited,
    VocabularyProvider,
)
from app.models import VocabularyLookupGrant
from quiz_shared.schemas import (
    VocabularyErrorCode,
    VocabularyLookupResponse,
    validate_canonical_vocabulary_output,
)


LOOKUP_GRANT_TTL_SECONDS = 900
VOCABULARY_JOURNEY_DEADLINE_SECONDS = 12
T = TypeVar("T")


def _has_unsafe_unicode(value: str) -> bool:
    return any(
        ord(character) <= 0x1F
        or 0x7F <= ord(character) <= 0x9F
        or character in {"\u2028", "\u2029"}
        or unicodedata.category(character) == "Cf"
        for character in value
    )


def normalize_lookup_text(value: str) -> str:
    if not isinstance(value, str) or _has_unsafe_unicode(value):
        raise ValueError("invalid vocabulary text")
    normalized = unicodedata.normalize("NFC", value)
    normalized = " ".join(normalized.split())
    if not 1 <= len(normalized) <= 120:
        raise ValueError("invalid vocabulary text length")
    return normalized


def validate_pronunciation_text(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 120:
        raise ValueError("invalid canonical pronunciation text")
    try:
        return validate_canonical_vocabulary_output(value)
    except ValueError as exc:
        raise ValueError("invalid canonical pronunciation text") from exc


def _cache_key(value: str) -> str:
    return normalize_lookup_text(value).casefold()


class VocabularyCache(Generic[T]):
    def __init__(
        self,
        *,
        max_entries: int = 512,
        ttl_seconds: float = 86_400,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries <= 0 or ttl_seconds <= 0:
            raise ValueError("cache bounds must be positive")
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, T]] = OrderedDict()

    def get(self, text: str) -> T | None:
        key = _cache_key(text)
        entry = self._entries.pop(key, None)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= self._clock():
            return None
        self._entries[key] = entry
        return value

    def put(self, text: str, value: T) -> None:
        key = _cache_key(text)
        self._entries.pop(key, None)
        self._entries[key] = (self._clock() + self._ttl, value)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)


class PerUserRateLimiter:
    """Per-process secondary limiter; Postgres remains the durable backstop."""

    def __init__(
        self,
        *,
        limit: int = 10,
        window_seconds: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("limiter bounds must be positive")
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._buckets: dict[tuple[UUID, str], deque[float]] = defaultdict(deque)

    def consume(self, user_id: UUID, operation: str) -> int | None:
        now = self._clock()
        bucket = self._buckets[(user_id, operation)]
        boundary = now - self._window
        while bucket and bucket[0] <= boundary:
            bucket.popleft()
        if len(bucket) >= self._limit:
            return max(1, ceil(bucket[0] + self._window - now))
        bucket.append(now)
        return None


@dataclass(frozen=True)
class CachedVocabularyResult:
    translation: str
    definition: str


class VocabularyServiceError(Exception):
    def __init__(
        self,
        code: VocabularyErrorCode,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.retry_after_seconds = retry_after_seconds


class VocabularyGrantRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session_factory = session_factory
        self._now = now

    def _utc_now(self) -> datetime:
        now = self._now()
        if now.tzinfo is None:
            raise ValueError("grant clock must be timezone-aware")
        return now.astimezone(UTC)

    async def create(self, user_id: UUID, translation: str) -> UUID:
        now = self._utc_now()
        grant = VocabularyLookupGrant(
            user_id=user_id,
            translation=translation,
            expires_at=now + timedelta(seconds=LOOKUP_GRANT_TTL_SECONDS),
            created_at=now,
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    session.add(grant)
            return grant.id
        except Exception as exc:
            raise VocabularyServiceError(
                VocabularyErrorCode.PROVIDER_UNAVAILABLE
            ) from exc

    async def resolve(self, user_id: UUID, lookup_id: UUID) -> str:
        now = self._utc_now()
        try:
            async with self._session_factory() as session:
                result = await session.exec(
                    select(VocabularyLookupGrant.translation).where(
                        VocabularyLookupGrant.id == lookup_id,
                        VocabularyLookupGrant.user_id == user_id,
                        VocabularyLookupGrant.expires_at > now,
                    )
                )
                translation = result.one_or_none()
        except Exception as exc:
            raise VocabularyServiceError(
                VocabularyErrorCode.PROVIDER_UNAVAILABLE
            ) from exc
        if translation is None:
            raise VocabularyServiceError(VocabularyErrorCode.INVALID_INPUT)
        try:
            return validate_pronunciation_text(translation)
        except ValueError as exc:
            raise VocabularyServiceError(
                VocabularyErrorCode.INVALID_PROVIDER_RESPONSE
            ) from exc


class VocabularyService:
    def __init__(
        self,
        *,
        provider: VocabularyProvider | None,
        budget: AIBudgetRepository,
        grants: VocabularyGrantRepository,
        cache: VocabularyCache[CachedVocabularyResult] | None = None,
        limiter: PerUserRateLimiter | None = None,
        concurrency: int = 4,
    ) -> None:
        if concurrency <= 0:
            raise ValueError("provider concurrency must be positive")
        self._provider = provider
        self._budget = budget
        self._grants = grants
        self._cache = cache or VocabularyCache()
        self._limiter = limiter or PerUserRateLimiter()
        self._provider_slots = asyncio.Semaphore(concurrency)
        self._flights: dict[str, asyncio.Task[CachedVocabularyResult]] = {}
        self._flight_guard = asyncio.Lock()

    def _require_enabled(self) -> VocabularyProvider:
        if self._provider is None:
            raise VocabularyServiceError(VocabularyErrorCode.PROVIDER_UNAVAILABLE)
        return self._provider

    def _consume_minute(self, user_id: UUID, operation: str) -> None:
        retry_after = self._limiter.consume(user_id, operation)
        if retry_after is not None:
            raise VocabularyServiceError(
                VocabularyErrorCode.RATE_LIMITED,
                retry_after_seconds=retry_after,
            )

    async def _consume_daily(self, user_id: UUID, operation: str) -> None:
        try:
            await self._budget.consume_daily(user_id, operation)  # type: ignore[arg-type]
        except BudgetExceeded as exc:
            raise VocabularyServiceError(
                VocabularyErrorCode.RATE_LIMITED,
                retry_after_seconds=exc.retry_after_seconds,
            ) from exc
        except BudgetUnavailable as exc:
            raise VocabularyServiceError(
                VocabularyErrorCode.PROVIDER_UNAVAILABLE
            ) from exc

    @staticmethod
    def _provider_error(exc: ProviderFailure) -> VocabularyServiceError:
        if isinstance(exc, ProviderRateLimited):
            return VocabularyServiceError(
                VocabularyErrorCode.RATE_LIMITED,
                retry_after_seconds=exc.retry_after_seconds,
            )
        if isinstance(exc, ProviderNoResult):
            return VocabularyServiceError(VocabularyErrorCode.NO_RESULT)
        if isinstance(exc, ProviderInvalidResponse):
            return VocabularyServiceError(VocabularyErrorCode.INVALID_PROVIDER_RESPONSE)
        return VocabularyServiceError(VocabularyErrorCode.PROVIDER_UNAVAILABLE)

    @staticmethod
    def _validate_provider_result(
        source_text: str, result: ProviderLookupResult
    ) -> CachedVocabularyResult:
        if (
            isinstance(result.input_tokens, bool)
            or not isinstance(result.input_tokens, int)
            or not 0 <= result.input_tokens <= LOOKUP_MAX_INPUT_TOKENS
            or isinstance(result.output_tokens, bool)
            or not isinstance(result.output_tokens, int)
            or not 0 <= result.output_tokens <= LOOKUP_MAX_OUTPUT_TOKENS
        ):
            raise ProviderInvalidResponse(
                "provider returned invalid usage", charge_known_absent=False
            )
        try:
            response = VocabularyLookupResponse(
                lookup_id=UUID(int=0),
                source_text=source_text,
                translation=result.translation,
                definition=result.definition,
            )
        except ValidationError as exc:
            raise ProviderInvalidResponse(
                "provider returned unsafe vocabulary data",
                charge_known_absent=False,
            ) from exc
        return CachedVocabularyResult(response.translation, response.definition)

    async def _lookup_provider(
        self,
        source_text: str,
        *,
        deadline: float,
    ) -> CachedVocabularyResult:
        provider = self._require_enabled()
        reservation = None
        provider_started = False
        try:
            async with asyncio.timeout_at(deadline):
                reservation = await self._budget.reserve(
                    "lookup", LOOKUP_RESERVATION_MICROUSD
                )
                async with self._provider_slots:
                    provider_started = True
                    result: ProviderLookupResult = await provider.lookup(source_text)
                cached = self._validate_provider_result(source_text, result)
                actual = lookup_cost_microusd(result.input_tokens, result.output_tokens)
                await self._budget.commit(reservation.id, actual)
        except BudgetExceeded as exc:
            raise VocabularyServiceError(
                VocabularyErrorCode.RATE_LIMITED,
                retry_after_seconds=exc.retry_after_seconds,
            ) from exc
        except BudgetUnavailable as exc:
            raise VocabularyServiceError(
                VocabularyErrorCode.PROVIDER_UNAVAILABLE
            ) from exc
        except ProviderFailure as exc:
            if reservation is not None and exc.charge_known_absent:
                await self._release_or_fail(reservation.id)
            raise self._provider_error(exc) from exc
        except TimeoutError as exc:
            if reservation is not None and not provider_started:
                await self._release_or_fail(reservation.id)
            raise VocabularyServiceError(
                VocabularyErrorCode.PROVIDER_UNAVAILABLE
            ) from exc
        self._cache.put(source_text, cached)
        return cached

    async def _release_or_fail(self, reservation_id: UUID) -> None:
        try:
            await self._budget.release(reservation_id)
        except BudgetUnavailable as exc:
            raise VocabularyServiceError(
                VocabularyErrorCode.PROVIDER_UNAVAILABLE
            ) from exc

    def _finish_flight(
        self, key: str, completed: asyncio.Task[CachedVocabularyResult]
    ) -> None:
        if self._flights.get(key) is completed:
            self._flights.pop(key, None)
        if not completed.cancelled():
            # Retrieve background failures even when every waiting request was
            # cancelled. Awaiters still observe the same stored exception.
            completed.exception()

    async def _coalesced_lookup(
        self,
        source_text: str,
        *,
        deadline: float,
    ) -> CachedVocabularyResult:
        key = _cache_key(source_text)
        async with self._flight_guard:
            task = self._flights.get(key)
            if task is None:
                task = asyncio.create_task(
                    self._lookup_provider(source_text, deadline=deadline)
                )
                self._flights[key] = task
                task.add_done_callback(
                    lambda completed, flight_key=key: self._finish_flight(
                        flight_key, completed
                    )
                )
        return await asyncio.shield(task)

    async def lookup(self, user_id: UUID, text: str) -> VocabularyLookupResponse:
        deadline = (
            asyncio.get_running_loop().time() + VOCABULARY_JOURNEY_DEADLINE_SECONDS
        )
        try:
            async with asyncio.timeout_at(deadline):
                self._require_enabled()
                self._consume_minute(user_id, "lookup")
                await self._consume_daily(user_id, "lookup")
                cached = self._cache.get(text)
                if cached is None:
                    cached = await self._coalesced_lookup(text, deadline=deadline)
                lookup_id = await self._grants.create(user_id, cached.translation)
                return VocabularyLookupResponse(
                    lookup_id=lookup_id,
                    source_text=text,
                    translation=cached.translation,
                    definition=cached.definition,
                )
        except TimeoutError as exc:
            raise VocabularyServiceError(
                VocabularyErrorCode.PROVIDER_UNAVAILABLE
            ) from exc

    async def pronounce(self, user_id: UUID, lookup_id: UUID) -> bytes:
        reservation = None
        provider_started = False
        try:
            async with asyncio.timeout(VOCABULARY_JOURNEY_DEADLINE_SECONDS):
                translation = await self._grants.resolve(user_id, lookup_id)
                provider = self._require_enabled()
                self._consume_minute(user_id, "pronunciation")
                await self._consume_daily(user_id, "pronunciation")
                cost = tts_cost_microusd(len(translation))
                reservation = await self._budget.reserve("pronunciation", cost)
                async with self._provider_slots:
                    provider_started = True
                    audio = await provider.pronounce(translation)
                await self._budget.commit(reservation.id, cost)
                return audio
        except BudgetExceeded as exc:
            raise VocabularyServiceError(
                VocabularyErrorCode.RATE_LIMITED,
                retry_after_seconds=exc.retry_after_seconds,
            ) from exc
        except BudgetUnavailable as exc:
            raise VocabularyServiceError(
                VocabularyErrorCode.PROVIDER_UNAVAILABLE
            ) from exc
        except ProviderFailure as exc:
            if reservation is not None and exc.charge_known_absent:
                await self._release_or_fail(reservation.id)
            raise self._provider_error(exc) from exc
        except TimeoutError as exc:
            if reservation is not None and not provider_started:
                await self._release_or_fail(reservation.id)
            raise VocabularyServiceError(
                VocabularyErrorCode.PROVIDER_UNAVAILABLE
            ) from exc
