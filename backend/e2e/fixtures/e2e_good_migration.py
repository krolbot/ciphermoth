"""Synthetic e2e migration: never part of a release.

Revision ID: e2e000000001
Revises: 9c0d1e2f3a4b
"""

import sqlalchemy as sa
from alembic import op

revision = "e2e000000001"
down_revision = "9c0d1e2f3a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("e2e_marker", sa.Integer(), nullable=False, server_default="7"),
    )
    op.create_table(
        "e2e_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("note", sa.Text(), nullable=False),
    )
    op.execute("INSERT INTO e2e_audit (note) VALUES ('migrated')")


def downgrade() -> None:
    op.drop_table("e2e_audit")
    op.drop_column("settings", "e2e_marker")
