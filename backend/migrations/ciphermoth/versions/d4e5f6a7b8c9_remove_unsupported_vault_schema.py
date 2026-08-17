"""remove the unsupported vault schema

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-17 20:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    has_existing_data = bind.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1 FROM master_password
                UNION ALL SELECT 1 FROM users
                UNION ALL SELECT 1 FROM passwords
                UNION ALL SELECT 1 FROM password_access
                UNION ALL SELECT 1 FROM password_attachments
                UNION ALL SELECT 1 FROM settings
            )
            """
        )
    )
    if has_existing_data:
        raise RuntimeError(
            "This release requires an empty database; reset it before upgrading."
        )

    op.drop_table("master_password")
    op.drop_column("users", "hash_key")

    op.drop_index("uq_passwords_name_active", table_name="passwords")
    op.alter_column("passwords", "owner_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column(
        "passwords",
        "encryption_version",
        existing_type=sa.Integer(),
        server_default="3",
        nullable=False,
    )
    op.alter_column(
        "passwords",
        "encrypted_payload",
        existing_type=sa.LargeBinary(),
        nullable=False,
    )
    for column in (
        "password_name",
        "kind",
        "username",
        "password_value",
        "description",
        "url",
        "totp_secret",
        "tags",
        "custom_fields",
        "folder",
        "password_history",
        "favorite",
        "backed_up",
    ):
        op.drop_column("passwords", column)

    op.drop_column("password_access", "favorite")

    op.alter_column(
        "password_attachments",
        "encrypted_payload",
        existing_type=sa.LargeBinary(),
        nullable=False,
    )
    for column in ("filename", "content", "content_type"):
        op.drop_column("password_attachments", column)


def downgrade() -> None:
    raise RuntimeError("This schema replacement is irreversible; reset the database.")
