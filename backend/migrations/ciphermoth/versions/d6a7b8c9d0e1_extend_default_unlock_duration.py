"""extend default browser unlock duration

Revision ID: d6a7b8c9d0e1
Revises: d5f6a7b8c9d0
Create Date: 2026-08-19 06:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d6a7b8c9d0e1"
down_revision = "d5f6a7b8c9d0"
branch_labels = None
depends_on = None


_OLD_INACTIVITY_MS = 120_000
_OLD_HIDDEN_MS = 60_000
_WARN_BEFORE_MS = 60_000
_NEW_UNLOCK_MS = 1_800_000


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE settings
            SET inactivity_ms = :new_unlock_ms,
                hidden_ms = :new_unlock_ms
            WHERE inactivity_ms = :old_inactivity_ms
              AND hidden_ms = :old_hidden_ms
              AND warn_before_ms = :warn_before_ms
            """
        ),
        {
            "new_unlock_ms": _NEW_UNLOCK_MS,
            "old_inactivity_ms": _OLD_INACTIVITY_MS,
            "old_hidden_ms": _OLD_HIDDEN_MS,
            "warn_before_ms": _WARN_BEFORE_MS,
        },
    )


def downgrade() -> None:
    # A user may intentionally choose 30 minutes after this migration. There is
    # no reliable way to distinguish that choice from a migrated default, so a
    # downgrade must not silently shorten an existing user's unlock duration.
    pass
