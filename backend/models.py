from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    func,
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

    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    encrypted_private_key: Mapped[bytes] = mapped_column(LargeBinary)
    auth_public_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    encrypted_auth_private_key: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
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


class AuthChallengeModel(BaseModel):
    __tablename__ = "auth_challenges"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP)


class PasswordModel(BaseModel):
    __tablename__ = "passwords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )
    deleted: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=None)

    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    encryption_version: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3"
    )
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary)


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
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary)
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
    encrypted_preferences: Mapped[bytes | None] = mapped_column(LargeBinary)

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
