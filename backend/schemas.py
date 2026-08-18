from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from validators import normalize_totp_secret

_MAX_TAGS = 20
_MAX_TAG_LENGTH = 40
_MAX_CUSTOM_FIELDS = 30
_MAX_FIELD_LABEL = 100
_MAX_FIELD_VALUE = 4096
_MAX_FOLDER_LENGTH = 200

Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=2,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9._@-]*$",
    ),
]


class SimpleDetailSchema(BaseModel):
    detail: str


class TrashPurgeResponse(BaseModel):
    deleted_count: int


class MetaResponse(BaseModel):
    version: str


class UserRole(StrEnum):
    admin = "admin"
    member = "member"
    service = "service"


class SharePermission(StrEnum):
    read = "read"
    write = "write"


class EntryPermission(StrEnum):
    owner = "owner"
    read = "read"
    write = "write"


class AuthUser(BaseModel):
    id: int
    username: str
    role: UserRole
    active: bool
    must_change_password: bool


class UserCreateResponse(AuthUser):
    service_token: str | None = None


class ShareTarget(BaseModel):
    id: int
    username: str
    role: UserRole
    public_key: str


class AuthSessionResponse(BaseModel):
    user: AuthUser
    token: str
    salt: str
    public_key: str
    encrypted_private_key: str
    encrypted_auth_private_key: str


class AuthChallengeResponse(BaseModel):
    challenge: str
    nonce: str
    salt: str
    public_key: str
    encrypted_private_key: str
    encrypted_auth_private_key: str


class AuthStatus(BaseModel):
    initialized: bool


class AuthBootstrapPayload(BaseModel):
    username: Username
    salt: str = Field(min_length=22, max_length=24)
    public_key: str = Field(min_length=43, max_length=44)
    encrypted_private_key: str = Field(min_length=1, max_length=4096)
    auth_public_key: str = Field(min_length=43, max_length=44)
    encrypted_auth_private_key: str = Field(min_length=1, max_length=4096)


class AuthChallengePayload(BaseModel):
    username: Username


class AuthLoginPayload(BaseModel):
    challenge: str = Field(min_length=32, max_length=128)
    signature: str = Field(min_length=43, max_length=88)


class PasswordChangePayload(BaseModel):
    new_salt: str = Field(min_length=22, max_length=24)
    encrypted_private_key: str = Field(min_length=1, max_length=4096)
    encrypted_auth_private_key: str = Field(min_length=1, max_length=4096)
    proof: str = Field(min_length=86, max_length=88)


class UserCreatePayload(BaseModel):
    username: Username
    role: UserRole = UserRole.member
    salt: str | None = Field(default=None, min_length=22, max_length=24)
    public_key: str | None = Field(default=None, min_length=43, max_length=44)
    encrypted_private_key: str | None = Field(
        default=None, min_length=1, max_length=4096
    )
    auth_public_key: str | None = Field(default=None, min_length=43, max_length=44)
    encrypted_auth_private_key: str | None = Field(
        default=None, min_length=1, max_length=4096
    )

    @model_validator(mode="after")
    def _human_keys_required(self) -> "UserCreatePayload":
        if self.role != UserRole.service and any(
            value is None
            for value in (
                self.salt,
                self.public_key,
                self.encrypted_private_key,
                self.auth_public_key,
                self.encrypted_auth_private_key,
            )
        ):
            raise ValueError("Client key material is required for a human user.")
        return self


class UserUpdatePayload(BaseModel):
    role: UserRole | None = None
    active: bool | None = None


class CustomField(BaseModel):
    label: str = Field(default="", max_length=_MAX_FIELD_LABEL)
    value: str = Field(default="", max_length=_MAX_FIELD_VALUE)
    hidden: bool = False

    model_config = ConfigDict(str_strip_whitespace=True)


class Password(BaseModel):
    password_name: str = Field(min_length=1, max_length=255)
    kind: str = Field(default="login")
    username: str | None = Field(default=None, max_length=255)
    password_value: Annotated[
        str, StringConstraints(strip_whitespace=False, min_length=1)
    ]
    url: str | None = Field(default=None, max_length=2048)
    totp_secret: str | None = Field(default=None, max_length=512)
    description: str | None = Field(default=None, max_length=1024)
    tags: list[str] = Field(default_factory=list, max_length=_MAX_TAGS)
    custom_fields: list[CustomField] = Field(
        default_factory=list, max_length=_MAX_CUSTOM_FIELDS
    )
    folder: str | None = Field(default=None, max_length=_MAX_FOLDER_LENGTH)
    favorite: bool = False

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("totp_secret")
    @classmethod
    def _normalize_totp(cls, value: str | None) -> str | None:
        return normalize_totp_secret(value)

    @field_validator("folder")
    @classmethod
    def _clean_folder(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("kind")
    @classmethod
    def _clean_kind(cls, value: str) -> str:
        return value if value in ("login", "note") else "login"

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for tag in value:
            tag = tag.strip()[:_MAX_TAG_LENGTH].strip()
            if tag and tag not in cleaned:
                cleaned.append(tag)
        return cleaned

    @field_validator("custom_fields")
    @classmethod
    def _clean_custom_fields(cls, value: list[CustomField]) -> list[CustomField]:
        return [field for field in value if field.label]


class PasswordHistoryEntry(BaseModel):
    value: str
    changed_at: datetime


class PasswordResponse(Password):
    id: int
    owner_id: int
    owner_username: str
    access: EntryPermission
    backed_up: bool
    updated: datetime
    deleted: datetime | None = None
    password_history: list[PasswordHistoryEntry] = Field(default_factory=list)
    attachment_count: int = 0


class EncryptedPasswordResponse(BaseModel):
    id: int
    owner_id: int
    owner_username: str | None = None
    access: EntryPermission
    encryption_version: int
    encrypted_payload: str
    wrapped_key: str
    encrypted_preferences: str | None = None
    created: datetime
    updated: datetime
    deleted: datetime | None = None


EncryptedAttachmentCiphertext = Annotated[
    str, Field(min_length=1, max_length=12_000_000)
]


class EncryptedPasswordCreatePayload(BaseModel):
    encrypted_payload: str = Field(min_length=1, max_length=4_000_000)
    wrapped_key: str = Field(min_length=1, max_length=16_384)
    encrypted_preferences: str | None = Field(default=None, max_length=16_384)
    encrypted_attachments: list[EncryptedAttachmentCiphertext] = Field(
        default_factory=list, max_length=20
    )


class EncryptedPasswordUpdatePayload(BaseModel):
    encrypted_payload: str = Field(min_length=1, max_length=4_000_000)
    encrypted_preferences: str | None = Field(default=None, max_length=16_384)
    encrypted_attachments: list[EncryptedAttachmentCiphertext] | None = Field(
        default=None, max_length=20
    )


class EncryptedPreferencesUpdatePayload(BaseModel):
    encrypted_preferences: str = Field(min_length=1, max_length=16_384)


class EncryptedAttachmentPayload(BaseModel):
    encrypted_payload: EncryptedAttachmentCiphertext


class EncryptedAttachmentResponse(BaseModel):
    id: int
    password_id: int
    encrypted_payload: str
    size_bytes: int
    created: datetime


class AttachmentResponse(BaseModel):
    id: int
    filename: str
    content_type: str | None = None
    size_bytes: int
    created: datetime


class FavoriteUpdatePayload(BaseModel):
    favorite: bool


class PasswordCreate(BaseModel):
    id: int
    created: bool
    detail: str


class ShareUpdatePayload(BaseModel):
    permission: SharePermission
    wrapped_key: str = Field(min_length=1, max_length=16_384)


class ShareGrant(BaseModel):
    user_id: int
    username: str
    role: UserRole
    permission: SharePermission


class PasswordUpdate(BaseModel):
    updated: bool
    detail: str


class PasswordDelete(BaseModel):
    deleted: bool
    detail: str


class SettingsResponse(BaseModel):
    inactivity_ms: int
    warn_before_ms: int
    hidden_ms: int
    debounce_ms: int
    clipboard_clear_ms: int
    update_check_enabled: bool


class SettingsUpdate(BaseModel):
    inactivity_ms: int = Field(ge=30_000, le=3_600_000)
    warn_before_ms: int = Field(ge=5_000, le=600_000)
    hidden_ms: int = Field(ge=10_000, le=3_600_000)
    debounce_ms: int = Field(ge=100, le=10_000)
    clipboard_clear_ms: int = Field(ge=5_000, le=600_000)
    update_check_enabled: bool


class OnConflict(StrEnum):
    skip = "skip"
    overwrite = "overwrite"


class PasswordImportResult(BaseModel):
    imported: int
    skipped: int
    overwritten: int
    total: int


class UpdateApplyPayload(BaseModel):
    target: str = Field(pattern=r"^v\d+\.\d+\.\d+$")


class UpdateApplyStatus(BaseModel):
    state: str
    detail: str | None = None
    target: str | None = None
    finished_at: str | None = None
    updater_present: bool = False
