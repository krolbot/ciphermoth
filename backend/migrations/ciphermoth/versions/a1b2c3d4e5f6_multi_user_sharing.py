"""add multi-user accounts and per-entry sharing

Revision ID: a1b2c3d4e5f6
Revises: 9c0d1e2f3a4b
Create Date: 2026-08-17 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "9c0d1e2f3a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instance_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bootstrapped_at", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        sa.table(
            "instance_state",
            sa.column("id", sa.Integer()),
            sa.column("bootstrapped_at", sa.TIMESTAMP()),
        ),
        [{"id": 1, "bootstrapped_at": None}],
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("hash_key", sa.String(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_private_key", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint(
            "role IN ('admin', 'member', 'service')", name="ck_users_role"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "last_seen",
            sa.TIMESTAMP(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index(
        "ix_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True
    )

    op.add_column("passwords", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.add_column(
        "passwords",
        sa.Column(
            "encryption_version", sa.Integer(), server_default="1", nullable=False
        ),
    )
    op.create_foreign_key(
        "fk_passwords_owner_id_users",
        "passwords",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_passwords_owner_id", "passwords", ["owner_id"])
    op.drop_index("uq_passwords_name_active", table_name="passwords")
    op.create_index(
        "uq_passwords_name_active",
        "passwords",
        ["owner_id", "password_name"],
        unique=True,
        postgresql_where=sa.text("deleted IS NULL"),
    )

    op.create_table(
        "password_access",
        sa.Column("password_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("permission", sa.String(length=16), nullable=False),
        sa.Column("wrapped_key", sa.LargeBinary(), nullable=False),
        sa.Column("favorite", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("granted_by", sa.Integer(), nullable=True),
        sa.Column(
            "created", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "permission IN ('owner', 'read', 'write')",
            name="ck_password_access_permission",
        ),
        sa.ForeignKeyConstraint(["password_id"], ["passwords.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("password_id", "user_id"),
    )

    op.add_column("settings", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_settings_user_id_users",
        "settings",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint("uq_settings_user_id", "settings", ["user_id"])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM users)")):
        raise RuntimeError(
            "Cannot downgrade multi-user sharing after bootstrap: "
            "per-entry encryption keys would be destroyed."
        )

    op.drop_constraint("uq_settings_user_id", "settings", type_="unique")
    op.drop_constraint("fk_settings_user_id_users", "settings", type_="foreignkey")
    op.drop_column("settings", "user_id")

    op.drop_table("password_access")
    op.drop_index("uq_passwords_name_active", table_name="passwords")
    op.create_index(
        "uq_passwords_name_active",
        "passwords",
        ["password_name"],
        unique=True,
        postgresql_where=sa.text("deleted IS NULL"),
    )
    op.drop_index("ix_passwords_owner_id", table_name="passwords")
    op.drop_constraint("fk_passwords_owner_id_users", "passwords", type_="foreignkey")
    op.drop_column("passwords", "encryption_version")
    op.drop_column("passwords", "owner_id")

    op.drop_index("ix_user_sessions_token_hash", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")
    op.drop_table("instance_state")
