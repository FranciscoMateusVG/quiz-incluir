"""add quizzes.unit

Tags a quiz with its workbook unit (free text, e.g. "Unit 3") so same-unit
quizzes can be grouped in the picker UI. Optional with no default — existing
quizzes get NULL and keep rendering exactly as before.

Additive and idempotent, matching every other migration in this chain
(``a1c4e7d9b2f0``, ``d4a9f2c1b6e3``): ``ADD COLUMN IF NOT EXISTS`` so it is
safe to run against either a ``SQLModel.create_all()``-built database or one
built purely from the migration chain.

Revision ID: 3b05117e8bf4
Revises: cce38be9b12c
Create Date: 2026-09-15 16:24:49.595349

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3b05117e8bf4'
down_revision: Union[str, Sequence[str], None] = 'cce38be9b12c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS unit VARCHAR")


def downgrade() -> None:
    op.execute("ALTER TABLE quizzes DROP COLUMN IF EXISTS unit")
