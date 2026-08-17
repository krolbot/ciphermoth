from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SETTINGS_DEFAULTS = {
    "inactivity_ms": 120_000,
    "warn_before_ms": 60_000,
    "hidden_ms": 60_000,
    "debounce_ms": 1_000,
    "clipboard_clear_ms": 30_000,
    # When true, the browser (never the server) checks GitHub for a newer
    # release. Off by choice keeps the instance fully third-party-free.
    "update_check_enabled": True,
}


class BaseModel(DeclarativeBase):
    pass


class InstanceStateModel(BaseModel):
    __tablename__ = "instance_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bootstrapped_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)


class MasterPasswordModel(BaseModel):
    __tablename__ = "master_password"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )
    deleted: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=None)

    salt: Mapped[bytes] = mapped_column(LargeBinary)
    hash_key: Mapped[str] = mapped_column(String)


class UserModel(BaseModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )
    username: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    salt: Mapped[bytes] = mapped_column(LargeBinary)
    hash_key: Mapped[str] = mapped_column(String)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    encrypted_private_key: Mapped[bytes] = mapped_column(LargeBinary)
    service_token_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )


class SessionModel(BaseModel):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class PasswordModel(BaseModel):
    __tablename__ = "passwords"
    __table_args__ = (
        Index(
            "uq_passwords_name_active",
            "owner_id",
            "password_name",
            unique=True,
            postgresql_where=text("deleted IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )
    deleted: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=None)

    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    encryption_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )
    password_name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="login", server_default="login")
    username: Mapped[str | None] = mapped_column(String)
    password_value: Mapped[bytes] = mapped_column(LargeBinary)
    description: Mapped[str | None] = mapped_column(String)
    url: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_secret: Mapped[bytes | None] = mapped_column(LargeBinary)
    tags: Mapped[bytes | None] = mapped_column(LargeBinary)
    custom_fields: Mapped[bytes | None] = mapped_column(LargeBinary)
    folder: Mapped[bytes | None] = mapped_column(LargeBinary)
    password_history: Mapped[bytes | None] = mapped_column(LargeBinary)
    favorite: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    backed_up: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )


class PasswordAttachmentModel(BaseModel):
    __tablename__ = "password_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    password_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("passwords.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[bytes] = mapped_column(LargeBinary)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[bytes | None] = mapped_column(LargeBinary)
    size_bytes: Mapped[int] = mapped_column(Integer)


class PasswordAccessModel(BaseModel):
    __tablename__ = "password_access"

    password_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("passwords.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(String(16))
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    favorite: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    granted_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())


class SettingsModel(BaseModel):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )

    inactivity_ms: Mapped[int] = mapped_column(
        Integer, server_default=str(SETTINGS_DEFAULTS["inactivity_ms"])
    )
    warn_before_ms: Mapped[int] = mapped_column(
        Integer, server_default=str(SETTINGS_DEFAULTS["warn_before_ms"])
    )
    hidden_ms: Mapped[int] = mapped_column(
        Integer, server_default=str(SETTINGS_DEFAULTS["hidden_ms"])
    )
    debounce_ms: Mapped[int] = mapped_column(
        Integer, server_default=str(SETTINGS_DEFAULTS["debounce_ms"])
    )
    clipboard_clear_ms: Mapped[int] = mapped_column(
        Integer, server_default=str(SETTINGS_DEFAULTS["clipboard_clear_ms"])
    )
    update_check_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
