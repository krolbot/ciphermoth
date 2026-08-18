"""link service identities to their human owner

Revision ID: d5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-18 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("service_owner_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_service_owner_id",
        "users",
        "users",
        ["service_owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_service_owner_id", "users", ["service_owner_id"])

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE users
            SET service_owner_id = (
                SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1
            )
            WHERE role = 'service'
              AND (SELECT count(*) FROM users WHERE role = 'admin') = 1
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_users_service_owner_id", table_name="users")
    op.drop_constraint("fk_users_service_owner_id", "users", type_="foreignkey")
    op.drop_column("users", "service_owner_id")
