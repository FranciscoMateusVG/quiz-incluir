"""change users.level from languagelevel (CEFR) to courselevel (B1-B4)

``User.level`` now tracks the Programa Incluir monorepo's own course-level
scheme (B1-B4, matching its informal class-naming convention) instead of the
CEFR scale used for quiz content difficulty (``Quiz.level``, unchanged,
still ``languagelevel``). The two enums are independent concepts that happen
to share the ``B1``/``B2`` labels.

Existing rows are remapped by best-effort CEFR -> course-level proximity
(A1/A2 -> B1, B1 -> B1, B2 -> B2, C1 -> B3, C2 -> B4) rather than dropped,
since this is a lossy but reversible one-time reinterpretation, not a
data-integrity concern (no downstream logic reads users.level today).

Guarded/idempotent the same way as a1c4e7d9b2f0: the enum type is created
only when absent, so this is safe to run against a database that was
bootstrapped via ``SQLModel.metadata.create_all`` (which already creates the
column with the current model's ``courselevel`` type) as well as one built
through the full migration chain.

Revision ID: c7f3a1b8e4d2
Revises: a1c4e7d9b2f0
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c7f3a1b8e4d2'
down_revision: Union[str, Sequence[str], None] = 'a1c4e7d9b2f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'courselevel') THEN
                CREATE TYPE courselevel AS ENUM ('B1', 'B2', 'B3', 'B4');
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'level'
                AND udt_name = 'languagelevel'
            ) THEN
                ALTER TABLE users ALTER COLUMN level DROP DEFAULT;
                ALTER TABLE users ALTER COLUMN level TYPE courselevel USING (
                    CASE level::text
                        WHEN 'A1' THEN 'B1'
                        WHEN 'A2' THEN 'B1'
                        WHEN 'B1' THEN 'B1'
                        WHEN 'B2' THEN 'B2'
                        WHEN 'C1' THEN 'B3'
                        WHEN 'C2' THEN 'B4'
                        ELSE 'B1'
                    END
                )::courselevel;
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
                WHERE table_name = 'users' AND column_name = 'level'
                AND udt_name = 'courselevel'
            ) THEN
                ALTER TABLE users ALTER COLUMN level TYPE languagelevel USING (
                    CASE level::text
                        WHEN 'B1' THEN 'B1'
                        WHEN 'B2' THEN 'B2'
                        WHEN 'B3' THEN 'C1'
                        WHEN 'B4' THEN 'C2'
                        ELSE 'A1'
                    END
                )::languagelevel;
            END IF;
        END $$;
        """
    )
