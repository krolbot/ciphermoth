"""add service user bearer tokens

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-17 05:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("service_token_hash", sa.String(length=64), nullable=True)
    )
    op.create_unique_constraint(
        "uq_users_service_token_hash", "users", ["service_token_hash"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_service_token_hash", "users", type_="unique")
    op.drop_column("users", "service_token_hash")
