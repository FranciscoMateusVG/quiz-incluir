"""fix schema drift from models.py

Three bugs left the migration-built schema out of sync with ``models.py``
(discovered while auditing the chain against the ORM models — none of this
was caught before because Render's deploy relies solely on
``SQLModel.metadata.create_all()``, which already has the correct schema; only
the Dokploy production path, which runs ``alembic upgrade head`` against a
fresh database, ever hits these bugs):

1. ``questions.created_at``, ``quizzes.created_at``/``updated_at``,
   ``users.created_at``, ``quiz_attempts.started_at``/``finished_at``, and
   ``answers.answered_at`` were created as naive ``TIMESTAMP`` columns in
   ``9363763904ae``, but ``models._tz_datetime_column()`` requires
   ``timezone=True`` — asyncpg rejects the tz-aware ``datetime.now(UTC)``
   defaults against a naive column, so every insert into these tables fails.
   ``users.updated_at`` is also nullable in the DB despite being NOT-NULL-with-
   default in the model.
2. ``questions.level`` is a ``NOT NULL`` column with no default left over from
   ``9363763904ae`` that ``Question`` never declared (only ``Quiz.level``
   exists) — every ORM insert into ``questions`` violates this constraint.
3. ``d4a9f2c1b6e3`` created the ``userrole`` enum as
   ``('student', 'admin')`` (lowercase, i.e. the members' ``.value``), but
   SQLAlchemy's default ``Enum`` handling persists the member **names**
   (``'STUDENT'``/``'ADMIN'``) unless ``values_callable`` is given — which is
   what every other enum in this chain does (e.g. ``questiontype`` stores
   ``'MULTIPLE_CHOICE'``, not ``'multiple_choice'``). Any insert/filter on
   ``UserRole`` raises ``invalid input value for enum userrole``.

Guarded/idempotent the same way as every prior corrective migration in this
chain (``a1c4e7d9b2f0``, ``c7f3a1b8e4d2``, ``d4a9f2c1b6e3``): every statement
checks current state first, so this is a no-op against a database bootstrapped
via ``SQLModel.metadata.create_all()`` (which already matches the model) as
well as safe to apply to a migration-built database.

Revision ID: cce38be9b12c
Revises: d4a9f2c1b6e3
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'cce38be9b12c'
down_revision: Union[str, Sequence[str], None] = 'd4a9f2c1b6e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NAIVE_TIMESTAMP_COLUMNS = [
    ("questions", "created_at"),
    ("quizzes", "created_at"),
    ("quizzes", "updated_at"),
    ("users", "created_at"),
    ("quiz_attempts", "started_at"),
    ("quiz_attempts", "finished_at"),
    ("answers", "answered_at"),
]


def upgrade() -> None:
    # 1. userrole enum: 'student'/'admin' -> 'STUDENT'/'ADMIN' to match
    # SQLAlchemy's default (member-name-based) enum persistence.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum e JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'userrole' AND e.enumlabel = 'student'
            ) THEN
                ALTER TYPE userrole RENAME VALUE 'student' TO 'STUDENT';
                ALTER TYPE userrole RENAME VALUE 'admin' TO 'ADMIN';
            END IF;
        END $$;
        """
    )

    # 2. Orphan questions.level column (Question has no `level` field).
    op.execute("ALTER TABLE questions DROP COLUMN IF EXISTS level")

    # 3. Add timezone=True to every naive timestamp column.
    for table, column in _NAIVE_TIMESTAMP_COLUMNS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = '{table}' AND column_name = '{column}'
                    AND data_type = 'timestamp without time zone'
                ) THEN
                    ALTER TABLE {table} ALTER COLUMN {column} TYPE timestamptz
                        USING {column} AT TIME ZONE 'UTC';
                END IF;
            END $$;
            """
        )

    # 4. users.updated_at should be NOT NULL, matching the model's
    # default-with-onupdate factory.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'updated_at'
                AND is_nullable = 'YES'
            ) THEN
                UPDATE users SET updated_at = created_at WHERE updated_at IS NULL;
                ALTER TABLE users ALTER COLUMN updated_at SET NOT NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'updated_at'
                AND is_nullable = 'NO'
            ) THEN
                ALTER TABLE users ALTER COLUMN updated_at DROP NOT NULL;
            END IF;
        END $$;
        """
    )

    for table, column in reversed(_NAIVE_TIMESTAMP_COLUMNS):
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = '{table}' AND column_name = '{column}'
                    AND data_type = 'timestamp with time zone'
                ) THEN
                    ALTER TABLE {table} ALTER COLUMN {column} TYPE timestamp
                        USING {column} AT TIME ZONE 'UTC';
                END IF;
            END $$;
            """
        )

    # Re-adding questions.level is lossy (original per-row values were never
    # recorded anywhere) — restore the column with a default so downgrade
    # doesn't fail, matching the documented lossy-remap precedent in
    # c7f3a1b8e4d2.
    op.execute(
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS level languagelevel "
        "NOT NULL DEFAULT 'A1'"
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum e JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'userrole' AND e.enumlabel = 'STUDENT'
            ) THEN
                ALTER TYPE userrole RENAME VALUE 'STUDENT' TO 'student';
                ALTER TYPE userrole RENAME VALUE 'ADMIN' TO 'admin';
            END IF;
        END $$;
        """
    )
