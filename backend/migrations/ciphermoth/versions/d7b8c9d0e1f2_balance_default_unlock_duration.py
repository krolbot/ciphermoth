"""balance default browser unlock duration

Revision ID: d7b8c9d0e1f2
Revises: d6a7b8c9d0e1
Create Date: 2026-08-25 22:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d7b8c9d0e1f2"
down_revision = "d6a7b8c9d0e1"
branch_labels = None
depends_on = None


_PREVIOUS_UNLOCK_MS = 1_800_000
_WARN_BEFORE_MS = 60_000
_NEW_INACTIVITY_MS = 900_000
_NEW_HIDDEN_MS = 600_000


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE settings
            SET inactivity_ms = :new_inactivity_ms,
                hidden_ms = :new_hidden_ms
            WHERE inactivity_ms = :previous_unlock_ms
              AND hidden_ms = :previous_unlock_ms
              AND warn_before_ms = :warn_before_ms
            """
        ),
        {
            "new_inactivity_ms": _NEW_INACTIVITY_MS,
            "new_hidden_ms": _NEW_HIDDEN_MS,
            "previous_unlock_ms": _PREVIOUS_UNLOCK_MS,
            "warn_before_ms": _WARN_BEFORE_MS,
        },
    )


def downgrade() -> None:
    # A user may intentionally choose these values after the migration. Do not
    # silently extend a customized unlock duration during downgrade.
    pass
