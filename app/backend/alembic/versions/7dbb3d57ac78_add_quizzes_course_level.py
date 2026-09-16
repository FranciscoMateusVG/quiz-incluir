"""add quizzes.course_level

Tags a quiz with the course/turma level (``CourseLevel``, B1-B4) it belongs
to, distinct from the existing CEFR ``level`` (``LanguageLevel``, A1-C2), so
quizzes can be browsed level-first alongside the existing unit grouping.

Reuses the ``courselevel`` Postgres enum type already created by
``c7f3a1b8e4d2_change_users_level_to_courselevel`` for ``users.level`` — no
``CREATE TYPE`` needed since this migration is downstream of it.

Additive and idempotent, matching every other migration in this chain
(``a1c4e7d9b2f0``, ``3b05117e8bf4``): ``ADD COLUMN IF NOT EXISTS`` so it is
safe to run against either a ``SQLModel.create_all()``-built database or one
built purely from the migration chain. Existing quizzes backfill to ``B1``.

Revision ID: 7dbb3d57ac78
Revises: 3b05117e8bf4
Create Date: 2026-09-15 17:40:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7dbb3d57ac78'
down_revision: Union[str, Sequence[str], None] = '3b05117e8bf4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS course_level "
        "courselevel NOT NULL DEFAULT 'B1'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE quizzes DROP COLUMN IF EXISTS course_level")
