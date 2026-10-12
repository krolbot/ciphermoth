"""Synthetic e2e migration that fails halfway: never part of a release.

Part of it commits outside the migration transaction, the way a CREATE INDEX
CONCURRENTLY step would, so the failure leaves the database changed.

Revision ID: e2e000000002
Revises: 9c0d1e2f3a4b
"""

from alembic import op

revision = "e2e000000002"
down_revision = "9c0d1e2f3a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("CREATE TABLE e2e_half_done (id integer)")
        op.execute("UPDATE settings SET inactivity_ms = inactivity_ms + 1")
        op.execute("UPDATE passwords SET description = 'damaged by e2e'")
    raise RuntimeError("synthetic migration failure (e2e)")


def downgrade() -> None:
    pass
