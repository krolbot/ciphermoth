"""add client-encrypted vault payloads

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-17 15:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "hash_key", existing_type=sa.String(), nullable=True)
    op.add_column(
        "users", sa.Column("auth_public_key", sa.LargeBinary(), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("encrypted_auth_private_key", sa.LargeBinary(), nullable=True),
    )
    op.create_table(
        "auth_challenges",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_auth_challenges_user_id"),
        "auth_challenges",
        ["user_id"],
        unique=False,
    )
    op.add_column(
        "passwords", sa.Column("encrypted_payload", sa.LargeBinary(), nullable=True)
    )
    op.alter_column(
        "passwords", "password_name", existing_type=sa.String(), nullable=True
    )
    op.alter_column(
        "passwords", "password_value", existing_type=sa.LargeBinary(), nullable=True
    )
    op.add_column(
        "password_access",
        sa.Column("encrypted_preferences", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "password_attachments",
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=True),
    )
    op.alter_column(
        "password_attachments",
        "filename",
        existing_type=sa.LargeBinary(),
        nullable=True,
    )
    op.alter_column(
        "password_attachments", "content", existing_type=sa.LargeBinary(), nullable=True
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM passwords WHERE encrypted_payload IS NOT NULL
                ) OR EXISTS (
                    SELECT 1 FROM password_attachments
                    WHERE encrypted_payload IS NOT NULL
                ) OR EXISTS (
                    SELECT 1 FROM users WHERE hash_key IS NULL
                ) OR EXISTS (
                    SELECT 1 FROM password_access
                    WHERE encrypted_preferences IS NOT NULL
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade after client-encrypted data or users exist';
                END IF;
            END
            $$;
            """
        )
    )
    op.alter_column(
        "password_attachments",
        "content",
        existing_type=sa.LargeBinary(),
        nullable=False,
    )
    op.alter_column(
        "password_attachments",
        "filename",
        existing_type=sa.LargeBinary(),
        nullable=False,
    )
    op.drop_column("password_attachments", "encrypted_payload")
    op.drop_column("password_access", "encrypted_preferences")
    op.alter_column(
        "passwords", "password_value", existing_type=sa.LargeBinary(), nullable=False
    )
    op.alter_column(
        "passwords", "password_name", existing_type=sa.String(), nullable=False
    )
    op.drop_column("passwords", "encrypted_payload")
    op.drop_index(op.f("ix_auth_challenges_user_id"), table_name="auth_challenges")
    op.drop_table("auth_challenges")
    op.drop_column("users", "encrypted_auth_private_key")
    op.drop_column("users", "auth_public_key")
    op.alter_column("users", "hash_key", existing_type=sa.String(), nullable=False)
