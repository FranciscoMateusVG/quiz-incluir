"""Durable AI spend-budget contract tests.

Pure arithmetic and metadata tests run everywhere.  Accounting transitions
run only when ``QUIZ_TEST_POSTGRES_URL`` names an explicitly disposable
PostgreSQL database.  Those tests create and drop a unique schema, because the
conditional updates and row locks are PostgreSQL correctness boundaries that
an in-memory imitation cannot prove.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app" / "backend"))
sys.path.insert(0, str(REPO_ROOT / "app" / "shared"))

from app.core.ai_budget import (  # noqa: E402
    LOOKUP_RESERVATION_MICROUSD,
    MAX_MONTHLY_BUDGET_MICROUSD,
    AIBudgetRepository,
    BudgetExceeded,
    BudgetUnavailable,
    lookup_cost_microusd,
    tts_cost_microusd,
)
from app.core.vocabulary import (  # noqa: E402
    VocabularyGrantRepository,
    VocabularyServiceError,
)
from app.models import (  # noqa: E402
    AIBudgetReservation,
    AIDailyUsage,
    AIMonthlyBudget,
    User,
    VocabularyLookupGrant,
)
from quiz_shared.schemas import VocabularyErrorCode  # noqa: E402
from quiz_shared.enums import CourseLevel, UserRole  # noqa: E402


FIXED_NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def _state_value(reservation: AIBudgetReservation) -> str:
    value = reservation.state
    return value.value if hasattr(value, "value") else str(value)


def _postgres_url() -> str | None:
    value = os.environ.get("QUIZ_TEST_POSTGRES_URL")
    if not value:
        return None
    if value.startswith("postgresql://"):
        return "postgresql+asyncpg://" + value.removeprefix("postgresql://")
    if value.startswith("postgres://"):
        return "postgresql+asyncpg://" + value.removeprefix("postgres://")
    return value


class CostArithmeticTests(unittest.TestCase):
    def test_global_monthly_cap_is_exactly_five_dollars(self) -> None:
        self.assertEqual(MAX_MONTHLY_BUDGET_MICROUSD, 5_000_000)
        self.assertEqual(LOOKUP_RESERVATION_MICROUSD, 461)
        self.assertLessEqual(LOOKUP_RESERVATION_MICROUSD, MAX_MONTHLY_BUDGET_MICROUSD)

    def test_lookup_cost_uses_one_integer_ceiling_after_both_components(self) -> None:
        # Approved prices are $0.15/M input tokens and $0.60/M output tokens.
        # 150/50 therefore costs 52.5 micro-USD and must be charged as 53.
        self.assertEqual(lookup_cost_microusd(150, 50), 53)
        self.assertEqual(lookup_cost_microusd(100, 0), 15)
        self.assertEqual(lookup_cost_microusd(0, 100), 60)
        self.assertEqual(lookup_cost_microusd(1, 0), 1)
        self.assertEqual(lookup_cost_microusd(0, 1), 1)
        self.assertEqual(lookup_cost_microusd(0, 0), 0)

    def test_tts_cost_is_exactly_fifteen_microusd_per_code_point(self) -> None:
        self.assertEqual(tts_cost_microusd(0), 0)
        self.assertEqual(tts_cost_microusd(30), 450)
        self.assertEqual(tts_cost_microusd(120), 1_800)

    def test_negative_usage_is_rejected_instead_of_reducing_spend(self) -> None:
        for call in (
            lambda: lookup_cost_microusd(-1, 0),
            lambda: lookup_cost_microusd(0, -1),
            lambda: tts_cost_microusd(-1),
        ):
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()

    def test_repository_rejects_configuration_above_hard_cap(self) -> None:
        def unusable_factory() -> None:
            return None

        AIBudgetRepository(
            unusable_factory,
            monthly_limit_microusd=MAX_MONTHLY_BUDGET_MICROUSD,
            now=lambda: FIXED_NOW,
        )
        with self.assertRaises(ValueError):
            AIBudgetRepository(
                unusable_factory,
                monthly_limit_microusd=MAX_MONTHLY_BUDGET_MICROUSD + 1,
                now=lambda: FIXED_NOW,
            )


class BudgetModelSchemaTests(unittest.TestCase):
    def test_month_model_has_integer_counters_timestamps_and_named_checks(self) -> None:
        table = AIMonthlyBudget.__table__
        self.assertEqual(table.name, "ai_monthly_budgets")
        self.assertEqual(
            set(table.columns),
            {
                table.c.month_start,
                table.c.limit_microusd,
                table.c.committed_microusd,
                table.c.reserved_microusd,
                table.c.created_at,
                table.c.updated_at,
            },
        )
        self.assertIsInstance(table.c.limit_microusd.type, BigInteger)
        self.assertIsInstance(table.c.committed_microusd.type, BigInteger)
        self.assertIsInstance(table.c.reserved_microusd.type, BigInteger)
        self.assertTrue(table.c.created_at.type.timezone)
        self.assertTrue(table.c.updated_at.type.timezone)
        self.assertEqual(
            {
                constraint.name
                for constraint in table.constraints
                if isinstance(constraint, CheckConstraint)
            },
            {
                "ck_ai_monthly_budgets_month_starts_on_day_one",
                "ck_ai_monthly_budgets_limit_range",
                "ck_ai_monthly_budgets_committed_nonnegative",
                "ck_ai_monthly_budgets_reserved_nonnegative",
                "ck_ai_monthly_budgets_within_limit",
            },
        )

    def test_reservation_has_reconciliation_indexes_and_constraints(self) -> None:
        table = AIBudgetReservation.__table__
        self.assertEqual(table.name, "ai_budget_reservations")
        self.assertTrue(table.c.created_at.type.timezone)
        self.assertTrue(table.c.updated_at.type.timezone)
        self.assertEqual(
            {index.name for index in table.indexes},
            {
                "ix_ai_budget_reservations_month_state",
                "ix_ai_budget_reservations_created_at",
            },
        )
        self.assertEqual(
            {
                constraint.name
                for constraint in table.constraints
                if isinstance(constraint, CheckConstraint)
            },
            {
                "ck_ai_budget_reservations_operation",
                "ck_ai_budget_reservations_state",
                "ck_ai_budget_reservations_reserved_positive",
                "ck_ai_budget_reservations_committed_nonnegative",
                "ck_ai_budget_reservations_state_amount_coherent",
            },
        )

    def test_daily_usage_primary_key_prevents_duplicate_user_day_kind_rows(
        self,
    ) -> None:
        table = AIDailyUsage.__table__
        self.assertEqual(table.name, "ai_daily_usage")
        self.assertEqual(
            [column.name for column in table.primary_key.columns],
            ["usage_date", "user_id", "operation"],
        )
        self.assertIsInstance(table.c.count.type, BigInteger)
        self.assertTrue(table.c.created_at.type.timezone)
        self.assertTrue(table.c.updated_at.type.timezone)

    def test_budget_migration_is_real_not_only_create_all_metadata(self) -> None:
        migration = (
            REPO_ROOT
            / "app"
            / "backend"
            / "alembic"
            / "versions"
            / "f1b2c3d4e5a6_add_ai_budget_tables.py"
        )
        source = migration.read_text(encoding="utf-8")
        self.assertIn(
            'down_revision: Union[str, Sequence[str], None] = "cce38be9b12c"',
            source,
        )
        for table_name in (
            "ai_monthly_budgets",
            "ai_budget_reservations",
            "ai_daily_usage",
            "vocabulary_lookup_grants",
        ):
            self.assertIn(f'"{table_name}"', source)
            self.assertIn(f'op.drop_table("{table_name}")', source)
        for index_name in (
            "ix_ai_budget_reservations_month_state",
            "ix_ai_budget_reservations_created_at",
            "ix_vocabulary_lookup_grants_expires_at",
            "ix_vocabulary_lookup_grants_user_id_id",
        ):
            self.assertIn(f'"{index_name}"', source)
        for constraint_name in (
            "ck_ai_monthly_budgets_limit_range",
            "ck_ai_monthly_budgets_within_limit",
            "ck_ai_budget_reservations_state_amount_coherent",
            "ck_ai_daily_usage_count_nonnegative",
        ):
            self.assertIn(f'"{constraint_name}"', source)


class StorageFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_storage_construction_failure_is_typed_and_fail_closed(self) -> None:
        def broken_factory() -> Any:
            raise RuntimeError("test storage unavailable")

        repository = AIBudgetRepository(
            broken_factory,
            monthly_limit_microusd=MAX_MONTHLY_BUDGET_MICROUSD,
            now=lambda: FIXED_NOW,
        )
        with self.assertRaises(BudgetUnavailable):
            await repository.reserve("lookup", LOOKUP_RESERVATION_MICROUSD)

        with self.assertRaises(BudgetUnavailable):
            await repository.consume_daily(uuid4(), "lookup")


@unittest.skipUnless(
    _postgres_url(),
    "requires an explicitly disposable QUIZ_TEST_POSTGRES_URL; PostgreSQL "
    "accounting/concurrency semantics are not replaced with SQL-shape mocks",
)
class PostgresBudgetRepositoryTests(unittest.IsolatedAsyncioTestCase):
    """Repository transitions against a unique schema in disposable Postgres."""

    engine: Any
    session_factory: async_sessionmaker[AsyncSession]
    schema_name: str
    now: datetime
    user_id: UUID

    async def asyncSetUp(self) -> None:
        url = _postgres_url()
        assert url is not None
        self.schema_name = "quiz_ai_budget_test_" + uuid4().hex
        admin_engine = create_async_engine(url)
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema_name}"'))
        await admin_engine.dispose()

        self.engine = create_async_engine(
            url,
            connect_args={"server_settings": {"search_path": self.schema_name}},
        )
        async with self.engine.begin() as connection:
            for table in (
                User.__table__,
                AIMonthlyBudget.__table__,
                AIBudgetReservation.__table__,
                AIDailyUsage.__table__,
                VocabularyLookupGrant.__table__,
            ):
                await connection.run_sync(table.create)

        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self.now = FIXED_NOW
        self.user_id = uuid4()
        async with self.session_factory.begin() as session:
            session.add(
                User(
                    id=self.user_id,
                    email=f"budget-{self.user_id}@example.test",
                    level=CourseLevel.B1,
                    role=UserRole.STUDENT,
                )
            )

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        url = _postgres_url()
        assert url is not None
        admin_engine = create_async_engine(url)
        async with admin_engine.begin() as connection:
            await connection.execute(
                text(f'DROP SCHEMA IF EXISTS "{self.schema_name}" CASCADE')
            )
        await admin_engine.dispose()

    def repository(self, *, limit: int = MAX_MONTHLY_BUDGET_MICROUSD):
        return AIBudgetRepository(
            self.session_factory,
            monthly_limit_microusd=limit,
            now=lambda: self.now,
        )

    async def _month(self, month_start: date) -> AIMonthlyBudget:
        async with self.session_factory() as session:
            result = await session.get(AIMonthlyBudget, month_start)
            assert result is not None
            return result

    async def _reservation(self, reservation_id: UUID) -> AIBudgetReservation:
        async with self.session_factory() as session:
            result = await session.get(AIBudgetReservation, reservation_id)
            assert result is not None
            return result

    async def test_exact_monthly_ceiling_succeeds_and_one_over_is_denied(self) -> None:
        repository = self.repository(limit=100)
        reservation = await repository.reserve("lookup", 100)
        self.assertEqual(reservation.month_start, date(2026, 9, 1))

        month = await self._month(date(2026, 9, 1))
        self.assertEqual(month.reserved_microusd, 100)
        self.assertEqual(month.committed_microusd, 0)

        with self.assertRaises(BudgetExceeded) as raised:
            await repository.reserve("lookup", 1)
        self.assertEqual(raised.exception.retry_after_seconds, 2_030_400)

    async def test_commit_and_release_are_idempotent_state_transitions(self) -> None:
        repository = self.repository(limit=1_000)
        committed = await repository.reserve("lookup", 100)
        released = await repository.reserve("pronunciation", 90)

        await repository.commit(committed.id, 53)
        await repository.commit(committed.id, 53)
        await repository.release(released.id)
        await repository.release(released.id)

        month = await self._month(date(2026, 9, 1))
        self.assertEqual(month.committed_microusd, 53)
        self.assertEqual(month.reserved_microusd, 0)

        committed_row = await self._reservation(committed.id)
        self.assertEqual(_state_value(committed_row), "committed")
        self.assertEqual(committed_row.committed_microusd, 53)
        released_row = await self._reservation(released.id)
        self.assertEqual(_state_value(released_row), "released")
        self.assertIsNone(released_row.committed_microusd)

    async def test_unknown_outcome_stays_reserved_across_repository_instances(
        self,
    ) -> None:
        first = self.repository(limit=1_000)
        reservation = await first.reserve("lookup", 100)

        # No commit/release models a timeout, process death, or unknown charge.
        second = self.repository(limit=1_000)
        with self.assertRaises(BudgetExceeded):
            await second.reserve("lookup", 901)

        month = await self._month(date(2026, 9, 1))
        self.assertEqual(month.reserved_microusd, 100)
        row = await self._reservation(reservation.id)
        self.assertEqual(_state_value(row), "reserved")

    async def test_actual_cost_above_reservation_fails_closed(self) -> None:
        repository = self.repository(limit=1_000)
        reservation = await repository.reserve("lookup", 100)

        with self.assertRaises(BudgetUnavailable):
            await repository.commit(reservation.id, 101)

        month = await self._month(date(2026, 9, 1))
        self.assertEqual(month.committed_microusd, 0)
        self.assertEqual(month.reserved_microusd, 100)
        row = await self._reservation(reservation.id)
        self.assertEqual(_state_value(row), "reserved")

    async def test_reservations_use_the_current_utc_month(self) -> None:
        repository = self.repository(limit=1_000)
        december = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
        self.now = december
        first = await repository.reserve("lookup", 10)
        self.now = december + timedelta(seconds=1)
        second = await repository.reserve("lookup", 20)

        self.assertEqual(first.month_start, date(2026, 12, 1))
        self.assertEqual(second.month_start, date(2027, 1, 1))
        self.assertEqual((await self._month(first.month_start)).reserved_microusd, 10)
        self.assertEqual((await self._month(second.month_start)).reserved_microusd, 20)

    async def test_durable_daily_limit_is_per_user_kind_and_utc_day(self) -> None:
        repository = self.repository()
        for _ in range(100):
            self.assertIsNone(await repository.consume_daily(self.user_id, "lookup"))

        with self.assertRaises(BudgetExceeded) as raised:
            await repository.consume_daily(self.user_id, "lookup")
        self.assertEqual(raised.exception.retry_after_seconds, 43_200)

        # The pronunciation bucket is independent.
        self.assertIsNone(await repository.consume_daily(self.user_id, "pronunciation"))

        self.now += timedelta(hours=12)
        self.assertIsNone(await repository.consume_daily(self.user_id, "lookup"))

    async def test_parallel_reservations_cannot_exceed_global_cap(self) -> None:
        import asyncio

        repository = self.repository(limit=100)
        results = await asyncio.gather(
            repository.reserve("lookup", 60),
            repository.reserve("pronunciation", 60),
            return_exceptions=True,
        )
        self.assertEqual(
            sum(isinstance(result, AIBudgetReservation) for result in results), 1
        )
        self.assertEqual(
            sum(isinstance(result, BudgetExceeded) for result in results), 1
        )
        month = await self._month(date(2026, 9, 1))
        self.assertEqual(month.reserved_microusd, 60)

    async def test_pronunciation_grant_is_user_bound_and_expires(self) -> None:
        repository = VocabularyGrantRepository(
            self.session_factory, now=lambda: self.now
        )
        lookup_id = await repository.create(self.user_id, "house")
        self.assertEqual(await repository.resolve(self.user_id, lookup_id), "house")

        with self.assertRaises(VocabularyServiceError) as wrong_user:
            await repository.resolve(uuid4(), lookup_id)
        self.assertEqual(wrong_user.exception.code, VocabularyErrorCode.INVALID_INPUT)

        self.now += timedelta(seconds=901)
        with self.assertRaises(VocabularyServiceError) as expired:
            await repository.resolve(self.user_id, lookup_id)
        self.assertEqual(expired.exception.code, VocabularyErrorCode.INVALID_INPUT)


if __name__ == "__main__":
    unittest.main()
