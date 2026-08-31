"""add users.role (student/admin) for the admin grades dashboard

Adds a ``role`` column to ``users`` distinguishing regular students from
admins who can view the class-wide grades dashboard. Defaults every existing
and new row to ``student`` — nobody is silently granted admin access by this
migration; promotion happens manually via the SQLAdmin backoffice.

Guarded/idempotent the same way as c7f3a1b8e4d2: the enum type and column are
created only when absent, so this is safe to run against a database that was
bootstrapped via ``SQLModel.metadata.create_all`` (which already creates the
column with the current model's ``userrole`` type) as well as one built
through the full migration chain.

Revision ID: d4a9f2c1b6e3
Revises: c7f3a1b8e4d2
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd4a9f2c1b6e3'
down_revision: Union[str, Sequence[str], None] = 'c7f3a1b8e4d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
                CREATE TYPE userrole AS ENUM ('student', 'admin');
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'role'
            ) THEN
                ALTER TABLE users ADD COLUMN role userrole NOT NULL DEFAULT 'student';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS role;")
    op.execute("DROP TYPE IF EXISTS userrole;")
