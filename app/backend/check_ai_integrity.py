"""Post-deploy integrity check for the Phase B vocabulary data contract."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from sqlalchemy import func
from sqlmodel import select

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import (
    AIBudgetReservation,
    AIDailyUsage,
    AIMonthlyBudget,
    User,
    VocabularyLookupGrant,
)


async def check_integrity() -> dict[str, int]:
    if (
        settings.OPENAI_API_KEY is None
        or not settings.OPENAI_API_KEY.get_secret_value().strip()
    ):
        raise RuntimeError("OPENAI_API_KEY is required for vocabulary activation")
    now = datetime.now(UTC)
    month_start = date(now.year, now.month, 1)
    async with async_session_maker() as session:
        budget = await session.get(AIMonthlyBudget, month_start)
        if budget is None:
            raise RuntimeError("current UTC-month AI budget row is missing")
        if budget.limit_microusd != settings.AI_MONTHLY_BUDGET_MICROUSD:
            raise RuntimeError("current AI budget row does not match configured limit")
        if (
            budget.committed_microusd < 0
            or budget.reserved_microusd < 0
            or budget.committed_microusd + budget.reserved_microusd
            > budget.limit_microusd
        ):
            raise RuntimeError("current AI budget counters violate their invariant")

        orphan_reservations = (
            await session.exec(
                select(func.count(AIBudgetReservation.id))
                .select_from(AIBudgetReservation)
                .outerjoin(
                    AIMonthlyBudget,
                    AIBudgetReservation.month_start == AIMonthlyBudget.month_start,
                )
                .where(AIMonthlyBudget.month_start.is_(None))
            )
        ).one()
        orphan_daily = (
            await session.exec(
                select(func.count())
                .select_from(AIDailyUsage)
                .outerjoin(User, AIDailyUsage.user_id == User.id)
                .where(User.id.is_(None))
            )
        ).one()
        orphan_grants = (
            await session.exec(
                select(func.count(VocabularyLookupGrant.id))
                .select_from(VocabularyLookupGrant)
                .outerjoin(User, VocabularyLookupGrant.user_id == User.id)
                .where(User.id.is_(None))
            )
        ).one()
        if orphan_reservations or orphan_daily or orphan_grants:
            raise RuntimeError("orphaned Phase B accounting records found")
        return {
            "current_budget_rows": 1,
            "orphan_reservations": int(orphan_reservations),
            "orphan_daily_usage": int(orphan_daily),
            "orphan_lookup_grants": int(orphan_grants),
        }


if __name__ == "__main__":
    result = asyncio.run(check_integrity())
    print("Phase B integrity OK", result)
