"""add durable vocabulary spend, daily-use, and pronunciation-grant tables

Revision ID: f1b2c3d4e5a6
Revises: cce38be9b12c
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1b2c3d4e5a6"
down_revision: Union[str, Sequence[str], None] = "cce38be9b12c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_monthly_budgets",
        sa.Column("month_start", sa.Date(), nullable=False),
        sa.Column("limit_microusd", sa.BigInteger(), nullable=False),
        sa.Column("committed_microusd", sa.BigInteger(), nullable=False),
        sa.Column("reserved_microusd", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM month_start) = 1",
            name="ck_ai_monthly_budgets_month_starts_on_day_one",
        ),
        sa.CheckConstraint(
            "limit_microusd BETWEEN 1 AND 5000000",
            name="ck_ai_monthly_budgets_limit_range",
        ),
        sa.CheckConstraint(
            "committed_microusd >= 0",
            name="ck_ai_monthly_budgets_committed_nonnegative",
        ),
        sa.CheckConstraint(
            "reserved_microusd >= 0",
            name="ck_ai_monthly_budgets_reserved_nonnegative",
        ),
        sa.CheckConstraint(
            "committed_microusd + reserved_microusd <= limit_microusd",
            name="ck_ai_monthly_budgets_within_limit",
        ),
        sa.PrimaryKeyConstraint("month_start"),
    )
    op.create_table(
        "ai_budget_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("month_start", sa.Date(), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("reserved_microusd", sa.BigInteger(), nullable=False),
        sa.Column("committed_microusd", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "operation IN ('lookup', 'pronunciation')",
            name="ck_ai_budget_reservations_operation",
        ),
        sa.CheckConstraint(
            "state IN ('reserved', 'committed', 'released')",
            name="ck_ai_budget_reservations_state",
        ),
        sa.CheckConstraint(
            "reserved_microusd > 0",
            name="ck_ai_budget_reservations_reserved_positive",
        ),
        sa.CheckConstraint(
            "committed_microusd IS NULL OR committed_microusd >= 0",
            name="ck_ai_budget_reservations_committed_nonnegative",
        ),
        sa.CheckConstraint(
            "(state = 'committed' AND committed_microusd IS NOT NULL "
            "AND committed_microusd <= reserved_microusd) OR "
            "(state IN ('reserved', 'released') AND committed_microusd IS NULL)",
            name="ck_ai_budget_reservations_state_amount_coherent",
        ),
        sa.ForeignKeyConstraint(
            ["month_start"],
            ["ai_monthly_budgets.month_start"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_budget_reservations_month_state",
        "ai_budget_reservations",
        ["month_start", "state"],
        unique=False,
    )
    op.create_index(
        "ix_ai_budget_reservations_created_at",
        "ai_budget_reservations",
        ["created_at"],
        unique=False,
    )
    op.create_table(
        "ai_daily_usage",
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "operation IN ('lookup', 'pronunciation')",
            name="ck_ai_daily_usage_operation",
        ),
        sa.CheckConstraint(
            "count >= 0",
            name="ck_ai_daily_usage_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("usage_date", "user_id", "operation"),
    )
    op.create_table(
        "vocabulary_lookup_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("translation", sa.String(length=120), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(translation) BETWEEN 1 AND 120",
            name="ck_vocabulary_lookup_grants_translation_length",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_vocabulary_lookup_grants_expires_at",
        "vocabulary_lookup_grants",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_vocabulary_lookup_grants_user_id_id",
        "vocabulary_lookup_grants",
        ["user_id", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vocabulary_lookup_grants_user_id_id",
        table_name="vocabulary_lookup_grants",
    )
    op.drop_index(
        "ix_vocabulary_lookup_grants_expires_at",
        table_name="vocabulary_lookup_grants",
    )
    op.drop_table("vocabulary_lookup_grants")
    op.drop_table("ai_daily_usage")
    op.drop_index(
        "ix_ai_budget_reservations_created_at",
        table_name="ai_budget_reservations",
    )
    op.drop_index(
        "ix_ai_budget_reservations_month_state",
        table_name="ai_budget_reservations",
    )
    op.drop_table("ai_budget_reservations")
    op.drop_table("ai_monthly_budgets")
