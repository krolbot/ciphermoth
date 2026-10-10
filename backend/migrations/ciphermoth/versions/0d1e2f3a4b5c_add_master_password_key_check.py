"""add encrypted key check to master_password

Revision ID: 0d1e2f3a4b5c
Revises: 9c0d1e2f3a4b
Create Date: 2026-10-10 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0d1e2f3a4b5c"
down_revision = "9c0d1e2f3a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "master_password", sa.Column("key_check", sa.LargeBinary(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("master_password", "key_check")
