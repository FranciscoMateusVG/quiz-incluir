"""Durable, fail-closed provider spend accounting."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from math import ceil
from typing import Literal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import AIBudgetReservation, AIDailyUsage, AIMonthlyBudget


MAX_MONTHLY_BUDGET_MICROUSD = 5_000_000
LOOKUP_MAX_INPUT_TOKENS = 2_048
LOOKUP_MAX_OUTPUT_TOKENS = 256
# Official snapshot pricing verified 2026-09-07. Values are hundredths of a
# micro-US-dollar per token: $0.15/M input and $0.60/M output.
LOOKUP_INPUT_RATE_NUMERATOR = 15
LOOKUP_OUTPUT_RATE_NUMERATOR = 60
LOOKUP_RATE_DENOMINATOR = 100
TTS_MICROUSD_PER_CHARACTER = 15
_LOOKUP_MAX_COST_NUMERATOR = (
    LOOKUP_MAX_INPUT_TOKENS * LOOKUP_INPUT_RATE_NUMERATOR
    + LOOKUP_MAX_OUTPUT_TOKENS * LOOKUP_OUTPUT_RATE_NUMERATOR
)
LOOKUP_RESERVATION_MICROUSD = (
    _LOOKUP_MAX_COST_NUMERATOR + LOOKUP_RATE_DENOMINATOR - 1
) // LOOKUP_RATE_DENOMINATOR
DAILY_OPERATION_LIMIT = 100
BudgetOperation = Literal["lookup", "pronunciation"]


class BudgetExceeded(Exception):
    def __init__(self, *, retry_after_seconds: int | None = None) -> None:
        super().__init__("provider spend limit reached")
        self.retry_after_seconds = retry_after_seconds


class BudgetUnavailable(Exception):
    pass


def lookup_cost_microusd(input_tokens: int, output_tokens: int) -> int:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts must be nonnegative")
    numerator = (
        input_tokens * LOOKUP_INPUT_RATE_NUMERATOR
        + output_tokens * LOOKUP_OUTPUT_RATE_NUMERATOR
    )
    return (numerator + LOOKUP_RATE_DENOMINATOR - 1) // LOOKUP_RATE_DENOMINATOR


def tts_cost_microusd(code_points: int) -> int:
    if code_points < 0:
        raise ValueError("character count must be nonnegative")
    return code_points * TTS_MICROUSD_PER_CHARACTER


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("budget clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


def _month_start(now: datetime) -> date:
    return date(now.year, now.month, 1)


def _seconds_to_next_day(now: datetime) -> int:
    tomorrow = now.date() + timedelta(days=1)
    return max(
        1, ceil((datetime.combine(tomorrow, time.min, UTC) - now).total_seconds())
    )


def _seconds_to_next_month(now: datetime) -> int:
    if now.month == 12:
        next_month = date(now.year + 1, 1, 1)
    else:
        next_month = date(now.year, now.month + 1, 1)
    return max(
        1,
        ceil((datetime.combine(next_month, time.min, UTC) - now).total_seconds()),
    )


class AIBudgetRepository:
    """Postgres-backed daily limits and atomic monthly reservations."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | Callable[[], AsyncSession],
        *,
        monthly_limit_microusd: int,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not 1 <= monthly_limit_microusd <= MAX_MONTHLY_BUDGET_MICROUSD:
            raise ValueError(
                "monthly AI budget must be between 1 and 5,000,000 microusd"
            )
        self._session_factory = session_factory
        self._limit = monthly_limit_microusd
        self._now = now

    async def reserve(
        self, operation: BudgetOperation, amount_microusd: int
    ) -> AIBudgetReservation:
        if operation not in ("lookup", "pronunciation") or amount_microusd <= 0:
            raise ValueError("invalid reservation")
        now = _utc(self._now())
        month_start = _month_start(now)
        reservation = AIBudgetReservation(
            month_start=month_start,
            operation=operation,
            reserved_microusd=amount_microusd,
            created_at=now,
            updated_at=now,
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.exec(
                        insert(AIMonthlyBudget)
                        .values(
                            month_start=month_start,
                            limit_microusd=self._limit,
                            committed_microusd=0,
                            reserved_microusd=0,
                            created_at=now,
                            updated_at=now,
                        )
                        .on_conflict_do_nothing(index_elements=["month_start"])
                    )
                    changed = await session.exec(
                        update(AIMonthlyBudget)
                        .where(
                            AIMonthlyBudget.month_start == month_start,
                            AIMonthlyBudget.committed_microusd
                            + AIMonthlyBudget.reserved_microusd
                            + amount_microusd
                            <= AIMonthlyBudget.limit_microusd,
                        )
                        .values(
                            reserved_microusd=AIMonthlyBudget.reserved_microusd
                            + amount_microusd,
                            updated_at=now,
                        )
                        .returning(AIMonthlyBudget.month_start)
                    )
                    if changed.scalar_one_or_none() is None:
                        raise BudgetExceeded(
                            retry_after_seconds=_seconds_to_next_month(now)
                        )
                    session.add(reservation)
            return reservation
        except BudgetExceeded:
            raise
        except Exception as exc:
            raise BudgetUnavailable("AI budget storage unavailable") from exc

    async def commit(self, reservation_id: UUID, actual_microusd: int) -> None:
        if actual_microusd < 0:
            raise ValueError("actual cost must be nonnegative")
        now = _utc(self._now())
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    result = await session.exec(
                        select(AIBudgetReservation)
                        .where(AIBudgetReservation.id == reservation_id)
                        .with_for_update()
                    )
                    reservation = result.one_or_none()
                    if reservation is None:
                        raise BudgetUnavailable("reservation missing")
                    if reservation.state == "committed":
                        if reservation.committed_microusd != actual_microusd:
                            raise BudgetUnavailable("reservation settlement mismatch")
                        return
                    if (
                        reservation.state != "reserved"
                        or actual_microusd > reservation.reserved_microusd
                    ):
                        raise BudgetUnavailable("reservation cannot be committed")
                    changed = await session.exec(
                        update(AIMonthlyBudget)
                        .where(
                            AIMonthlyBudget.month_start == reservation.month_start,
                            AIMonthlyBudget.reserved_microusd
                            >= reservation.reserved_microusd,
                        )
                        .values(
                            reserved_microusd=AIMonthlyBudget.reserved_microusd
                            - reservation.reserved_microusd,
                            committed_microusd=AIMonthlyBudget.committed_microusd
                            + actual_microusd,
                            updated_at=now,
                        )
                        .returning(AIMonthlyBudget.month_start)
                    )
                    if changed.scalar_one_or_none() is None:
                        raise BudgetUnavailable("monthly budget state is inconsistent")
                    reservation.state = "committed"
                    reservation.committed_microusd = actual_microusd
                    reservation.updated_at = now
                    session.add(reservation)
        except BudgetUnavailable:
            raise
        except Exception as exc:
            raise BudgetUnavailable("AI budget storage unavailable") from exc

    async def release(self, reservation_id: UUID) -> None:
        now = _utc(self._now())
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    result = await session.exec(
                        select(AIBudgetReservation)
                        .where(AIBudgetReservation.id == reservation_id)
                        .with_for_update()
                    )
                    reservation = result.one_or_none()
                    if reservation is None:
                        raise BudgetUnavailable("reservation missing")
                    if reservation.state == "released":
                        return
                    if reservation.state != "reserved":
                        raise BudgetUnavailable("reservation cannot be released")
                    changed = await session.exec(
                        update(AIMonthlyBudget)
                        .where(
                            AIMonthlyBudget.month_start == reservation.month_start,
                            AIMonthlyBudget.reserved_microusd
                            >= reservation.reserved_microusd,
                        )
                        .values(
                            reserved_microusd=AIMonthlyBudget.reserved_microusd
                            - reservation.reserved_microusd,
                            updated_at=now,
                        )
                        .returning(AIMonthlyBudget.month_start)
                    )
                    if changed.scalar_one_or_none() is None:
                        raise BudgetUnavailable("monthly budget state is inconsistent")
                    reservation.state = "released"
                    reservation.updated_at = now
                    session.add(reservation)
        except BudgetUnavailable:
            raise
        except Exception as exc:
            raise BudgetUnavailable("AI budget storage unavailable") from exc

    async def consume_daily(self, user_id: UUID, operation: BudgetOperation) -> None:
        if operation not in ("lookup", "pronunciation"):
            raise ValueError("invalid operation")
        now = _utc(self._now())
        usage_date = now.date()
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    statement = (
                        insert(AIDailyUsage)
                        .values(
                            usage_date=usage_date,
                            user_id=user_id,
                            operation=operation,
                            count=1,
                            created_at=now,
                            updated_at=now,
                        )
                        .on_conflict_do_update(
                            index_elements=["usage_date", "user_id", "operation"],
                            set_={
                                "count": AIDailyUsage.count + 1,
                                "updated_at": now,
                            },
                            where=AIDailyUsage.count < DAILY_OPERATION_LIMIT,
                        )
                        .returning(AIDailyUsage.count)
                    )
                    changed = await session.exec(statement)
                    if changed.scalar_one_or_none() is None:
                        raise BudgetExceeded(
                            retry_after_seconds=_seconds_to_next_day(now)
                        )
        except BudgetExceeded:
            raise
        except Exception as exc:
            raise BudgetUnavailable("AI daily limit storage unavailable") from exc
