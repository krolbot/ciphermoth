import base64
import binascii
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from api.exceptions import Forbidden, NotFound, TypesMismatchError
from crud.auth import AuthContext
from models import (
    PasswordAccessModel,
    PasswordAttachmentModel,
    PasswordModel,
    UserModel,
)
from schemas import (
    EncryptedAttachmentResponse,
    EncryptedPasswordResponse,
    EntryPermission,
    LegacyAttachmentResponse,
    LegacyPasswordResponse,
    LegacyRecipient,
    PasswordMigrationPayload,
    ShareGrant,
    SharePermission,
    UserRole,
)


def _decode(value: str, *, label: str) -> bytes:
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, binascii.Error) as exc:
        raise TypesMismatchError(f"Invalid {label}.") from exc
    if not decoded:
        raise TypesMismatchError(f"Invalid {label}.")
    return decoded


def _encode(value: bytes | None) -> str | None:
    if value is None:
        return None
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode_fernet(value: str, *, label: str) -> bytes:
    try:
        encoded = value.encode("ascii")
        token = base64.urlsafe_b64decode(encoded)
    except (UnicodeEncodeError, ValueError, binascii.Error) as exc:
        raise TypesMismatchError(f"Invalid {label}.") from exc
    if len(token) < 73 or token[0] != 0x80:
        raise TypesMismatchError(f"Invalid {label}.")
    return encoded


def _encode_fernet(value: bytes | None) -> str | None:
    if value is None:
        return None
    try:
        encoded = value.decode("ascii")
    except UnicodeDecodeError as exc:
        raise TypesMismatchError("Invalid encrypted value.") from exc
    _decode_fernet(encoded, label="encrypted value")
    return encoded


def _decode_wrapped_key(value: str) -> bytes:
    decoded = _decode(value, label="wrapped key")
    if len(decoded) < 62 or decoded[0] != 1:
        raise TypesMismatchError("Invalid wrapped key.")
    return decoded


_MAX_ATTACHMENTS_PER_ENTRY = 20
_MAX_ATTACHMENT_ENCODED = 12_000_000
_MAX_ATTACHMENT_CIPHERTEXT = 10 * 1024 * 1024
_MAX_TOTAL_ATTACHMENT_CIPHERTEXT = 50 * 1024 * 1024


def _decode_attachment_payloads(values: list[str]) -> list[bytes]:
    if len(values) > _MAX_ATTACHMENTS_PER_ENTRY:
        raise TypesMismatchError("An entry can have at most 20 attachments.")
    if any(len(value) > _MAX_ATTACHMENT_ENCODED for value in values):
        raise TypesMismatchError("Attachment ciphertext is too large.")
    payloads = [_decode_fernet(value, label="encrypted attachment") for value in values]
    if any(len(payload) > _MAX_ATTACHMENT_CIPHERTEXT for payload in payloads):
        raise TypesMismatchError("Attachment ciphertext is too large.")
    if sum(map(len, payloads)) > _MAX_TOTAL_ATTACHMENT_CIPHERTEXT:
        raise TypesMismatchError("Attachments would exceed the entry limit.")
    return payloads


class EncryptedPasswordCRUD:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _entry_and_access(
        self,
        context: AuthContext,
        password_id: int,
        *,
        deleted: bool | None = False,
    ) -> tuple[PasswordModel, PasswordAccessModel]:
        result = await self.session.execute(
            select(PasswordModel, PasswordAccessModel)
            .join(
                PasswordAccessModel,
                PasswordAccessModel.password_id == PasswordModel.id,
            )
            .where(
                PasswordModel.id == password_id,
                PasswordAccessModel.user_id == context.user.id,
                PasswordModel.deleted.is_not(None)
                if deleted is True
                else PasswordModel.deleted.is_(None)
                if deleted is False
                else true(),
            )
        )
        row = result.one_or_none()
        if row is None:
            raise NotFound("Password not found.")
        return row[0], row[1]

    @staticmethod
    def _response(
        entry: PasswordModel,
        access: PasswordAccessModel,
        owner_username: str | None = None,
    ) -> EncryptedPasswordResponse:
        if entry.encrypted_payload is None:
            raise TypesMismatchError("Legacy password must be migrated in the client.")
        if entry.owner_id is None:
            raise TypesMismatchError("Password entry has no owner.")
        encrypted_payload = _encode_fernet(entry.encrypted_payload)
        wrapped_key = _encode(access.wrapped_key)
        assert encrypted_payload is not None and wrapped_key is not None
        return EncryptedPasswordResponse(
            id=entry.id,
            owner_id=entry.owner_id,
            owner_username=owner_username,
            access=EntryPermission(access.permission),
            encryption_version=entry.encryption_version,
            encrypted_payload=encrypted_payload,
            wrapped_key=wrapped_key,
            encrypted_preferences=_encode_fernet(access.encrypted_preferences),
            created=entry.created,
            updated=entry.updated,
            deleted=entry.deleted,
        )

    async def create(
        self,
        context: AuthContext,
        *,
        encrypted_payload: str,
        wrapped_key: str,
        encrypted_preferences: str | None = None,
        encrypted_attachments: list[str] | None = None,
    ) -> EncryptedPasswordResponse:
        attachment_payloads = _decode_attachment_payloads(encrypted_attachments or [])
        entry = PasswordModel(
            owner_id=context.user.id,
            encryption_version=3,
            encrypted_payload=_decode_fernet(
                encrypted_payload, label="encrypted payload"
            ),
            password_name=None,
            kind="opaque",
            username=None,
            password_value=None,
            description=None,
            url=None,
            totp_secret=None,
            tags=None,
            custom_fields=None,
            folder=None,
            password_history=None,
            favorite=False,
            backed_up=False,
        )
        self.session.add(entry)
        await self.session.flush()
        access = PasswordAccessModel(
            password_id=entry.id,
            user_id=context.user.id,
            permission=EntryPermission.owner,
            wrapped_key=_decode_wrapped_key(wrapped_key),
            encrypted_preferences=(
                _decode_fernet(encrypted_preferences, label="encrypted preferences")
                if encrypted_preferences is not None
                else None
            ),
            favorite=False,
            granted_by=context.user.id,
        )
        self.session.add(access)
        self.session.add_all(
            PasswordAttachmentModel(
                password_id=entry.id,
                encrypted_payload=payload,
                filename=None,
                content=None,
                content_type=None,
                size_bytes=len(payload),
            )
            for payload in attachment_payloads
        )
        await self.session.flush()
        return self._response(entry, access)

    async def get(
        self, context: AuthContext, password_id: int
    ) -> EncryptedPasswordResponse:
        entry, access = await self._entry_and_access(context, password_id)
        return self._response(entry, access)

    async def list_passwords(
        self, context: AuthContext, *, deleted: bool = False
    ) -> list[EncryptedPasswordResponse]:
        statement = (
            select(PasswordModel, PasswordAccessModel, UserModel.username)
            .join(
                PasswordAccessModel,
                PasswordAccessModel.password_id == PasswordModel.id,
            )
            .join(UserModel, UserModel.id == PasswordModel.owner_id)
            .where(
                PasswordAccessModel.user_id == context.user.id,
                PasswordModel.deleted.is_not(None)
                if deleted
                else PasswordModel.deleted.is_(None),
                PasswordModel.encryption_version == 3,
            )
            .order_by(PasswordModel.updated.desc())
        )
        return [
            self._response(entry, access, owner_username)
            for entry, access, owner_username in await self.session.execute(statement)
        ]

    async def list_legacy(self, context: AuthContext) -> list[LegacyPasswordResponse]:
        rows = (
            await self.session.execute(
                select(PasswordModel, PasswordAccessModel)
                .join(
                    PasswordAccessModel,
                    PasswordAccessModel.password_id == PasswordModel.id,
                )
                .where(
                    PasswordAccessModel.user_id == context.user.id,
                    PasswordAccessModel.permission == "owner",
                    PasswordModel.encryption_version < 3,
                )
                .order_by(PasswordModel.id)
            )
        ).all()
        result: list[LegacyPasswordResponse] = []
        for entry, owner_access in rows:
            attachments = (
                await self.session.execute(
                    select(PasswordAttachmentModel).where(
                        PasswordAttachmentModel.password_id == entry.id
                    )
                )
            ).scalars()
            legacy_attachments = []
            for attachment in attachments:
                if attachment.filename is None or attachment.content is None:
                    raise TypesMismatchError("Legacy attachment data is incomplete.")
                filename = _encode_fernet(attachment.filename)
                content = _encode_fernet(attachment.content)
                assert filename is not None and content is not None
                legacy_attachments.append(
                    LegacyAttachmentResponse(
                        id=attachment.id,
                        filename=filename,
                        content_type=_encode_fernet(attachment.content_type),
                        content=content,
                    )
                )
            recipients = (
                await self.session.execute(
                    select(
                        PasswordAccessModel.user_id,
                        UserModel.public_key,
                        PasswordAccessModel.favorite,
                    )
                    .join(UserModel, UserModel.id == PasswordAccessModel.user_id)
                    .where(PasswordAccessModel.password_id == entry.id)
                )
            ).all()
            wrapped_key = _encode(owner_access.wrapped_key)
            assert wrapped_key is not None
            result.append(
                LegacyPasswordResponse(
                    id=entry.id,
                    encryption_version=entry.encryption_version,
                    wrapped_key=wrapped_key,
                    password_name=entry.password_name,
                    kind=entry.kind,
                    username=entry.username,
                    password_value=_encode_fernet(entry.password_value),
                    url=_encode_fernet(entry.url),
                    totp_secret=_encode_fernet(entry.totp_secret),
                    description=entry.description,
                    tags=_encode_fernet(entry.tags),
                    custom_fields=_encode_fernet(entry.custom_fields),
                    folder=_encode_fernet(entry.folder),
                    password_history=_encode_fernet(entry.password_history),
                    favorite=owner_access.favorite,
                    backed_up=entry.backed_up,
                    attachments=legacy_attachments,
                    recipients=[
                        self._legacy_recipient(*recipient) for recipient in recipients
                    ],
                )
            )
        return result

    @staticmethod
    def _legacy_recipient(
        user_id: int, public_key: bytes, favorite: bool
    ) -> LegacyRecipient:
        encoded = _encode(public_key)
        assert encoded is not None
        return LegacyRecipient(user_id=user_id, public_key=encoded, favorite=favorite)

    async def migrate(
        self,
        context: AuthContext,
        password_id: int,
        payload: PasswordMigrationPayload,
    ) -> EncryptedPasswordResponse:
        entry, owner_access = await self._entry_and_access(
            context, password_id, deleted=None
        )
        if owner_access.permission != "owner":
            raise Forbidden("Owner access is required.")
        if entry.encryption_version >= 3:
            return self._response(entry, owner_access)

        accesses = (
            (
                await self.session.execute(
                    select(PasswordAccessModel).where(
                        PasswordAccessModel.password_id == password_id
                    )
                )
            )
            .scalars()
            .all()
        )
        wrapped_keys = {
            item.user_id: _decode_wrapped_key(item.wrapped_key)
            for item in payload.wrapped_keys
        }
        if set(wrapped_keys) != {access.user_id for access in accesses}:
            raise TypesMismatchError(
                "Wrapped keys must cover every existing recipient."
            )
        preferences = {
            item.user_id: _decode_fernet(
                item.encrypted_preferences, label="encrypted preferences"
            )
            for item in payload.preferences
        }
        if set(preferences) != {access.user_id for access in accesses}:
            raise TypesMismatchError(
                "Encrypted preferences must cover every existing recipient."
            )

        attachments = (
            (
                await self.session.execute(
                    select(PasswordAttachmentModel).where(
                        PasswordAttachmentModel.password_id == password_id
                    )
                )
            )
            .scalars()
            .all()
        )
        decoded_attachments = _decode_attachment_payloads(
            [item.encrypted_payload for item in payload.attachments]
        )
        migrated_attachments = {
            item.id: decoded
            for item, decoded in zip(
                payload.attachments, decoded_attachments, strict=True
            )
        }
        if set(migrated_attachments) != {attachment.id for attachment in attachments}:
            raise TypesMismatchError(
                "Migrated attachments must cover every legacy attachment."
            )

        entry.encrypted_payload = _decode_fernet(
            payload.encrypted_payload, label="encrypted payload"
        )
        entry.encryption_version = 3
        entry.password_name = None
        entry.password_value = None
        entry.kind = "opaque"
        entry.username = None
        entry.url = None
        entry.totp_secret = None
        entry.description = None
        entry.tags = None
        entry.custom_fields = None
        entry.folder = None
        entry.password_history = None
        entry.favorite = False
        entry.backed_up = False
        for access in accesses:
            access.wrapped_key = wrapped_keys[access.user_id]
            access.favorite = False
            access.encrypted_preferences = preferences[access.user_id]
        for attachment in attachments:
            encrypted_attachment = migrated_attachments[attachment.id]
            attachment.encrypted_payload = encrypted_attachment
            attachment.filename = None
            attachment.content_type = None
            attachment.content = None
            attachment.size_bytes = len(encrypted_attachment)
        await self.session.flush()
        await self.session.refresh(entry)
        return self._response(entry, owner_access)

    async def update(
        self,
        context: AuthContext,
        password_id: int,
        *,
        encrypted_payload: str,
        encrypted_preferences: str | None = None,
        encrypted_attachments: list[str] | None = None,
    ) -> EncryptedPasswordResponse:
        entry, access = await self._entry_and_access(context, password_id)
        if access.permission not in (EntryPermission.owner, SharePermission.write):
            raise Forbidden("Write access is required.")
        if entry.encryption_version != 3:
            raise TypesMismatchError("Legacy password must be migrated in the client.")
        payload = _decode_fernet(encrypted_payload, label="encrypted payload")
        preferences = (
            _decode_fernet(encrypted_preferences, label="encrypted preferences")
            if encrypted_preferences is not None
            else None
        )
        if encrypted_attachments is not None:
            await self.replace_attachments(
                context, password_id, encrypted_payloads=encrypted_attachments
            )
        entry.encrypted_payload = payload
        if preferences is not None:
            access.encrypted_preferences = preferences
            access.favorite = False
        entry.updated = datetime.now(UTC).replace(tzinfo=None)
        await self.session.flush()
        return self._response(entry, access)

    async def set_preferences(
        self,
        context: AuthContext,
        password_id: int,
        *,
        encrypted_preferences: str,
    ) -> EncryptedPasswordResponse:
        entry, access = await self._entry_and_access(context, password_id)
        access.encrypted_preferences = _decode_fernet(
            encrypted_preferences, label="encrypted preferences"
        )
        await self.session.flush()
        return self._response(entry, access)

    async def set_deleted(
        self, context: AuthContext, password_id: int, *, deleted: bool
    ) -> EncryptedPasswordResponse:
        entry, access = await self._entry_and_access(
            context, password_id, deleted=not deleted
        )
        if access.permission not in (EntryPermission.owner, SharePermission.write):
            raise Forbidden("Write access is required.")
        now = datetime.now(UTC).replace(tzinfo=None)
        entry.deleted = now if deleted else None
        entry.updated = now
        await self.session.flush()
        return self._response(entry, access)

    async def delete(self, context: AuthContext, password_id: int) -> None:
        entry, access = await self._entry_and_access(context, password_id, deleted=True)
        if access.permission != EntryPermission.owner:
            raise Forbidden("Only the owner can permanently delete a password.")
        await self.session.delete(entry)

    async def share(
        self,
        context: AuthContext,
        password_id: int,
        user_id: int,
        *,
        permission: SharePermission,
        wrapped_key: str,
    ) -> ShareGrant:
        entry, actor_access = await self._entry_and_access(context, password_id)
        if actor_access.permission != EntryPermission.owner:
            raise Forbidden("Only the owner can manage sharing.")
        target = await self.session.get(UserModel, user_id)
        if target is None or not target.active or target.id == context.user.id:
            raise NotFound("Share target not found.")
        access = await self.session.get(PasswordAccessModel, (entry.id, user_id))
        if access is None:
            access = PasswordAccessModel(
                password_id=entry.id,
                user_id=user_id,
                permission=permission,
                wrapped_key=_decode_wrapped_key(wrapped_key),
                favorite=False,
                granted_by=context.user.id,
            )
            self.session.add(access)
        else:
            access.permission = permission
            access.wrapped_key = _decode_wrapped_key(wrapped_key)
            access.granted_by = context.user.id
        await self.session.flush()
        return ShareGrant(
            user_id=target.id,
            username=target.username,
            role=UserRole(target.role),
            permission=permission,
        )

    async def list_shares(
        self, context: AuthContext, password_id: int
    ) -> list[ShareGrant]:
        _, actor_access = await self._entry_and_access(context, password_id)
        if actor_access.permission != EntryPermission.owner:
            raise Forbidden("Only the owner can manage sharing.")
        rows = await self.session.execute(
            select(PasswordAccessModel, UserModel)
            .join(UserModel, UserModel.id == PasswordAccessModel.user_id)
            .where(
                PasswordAccessModel.password_id == password_id,
                PasswordAccessModel.permission != EntryPermission.owner,
            )
            .order_by(UserModel.username)
        )
        return [
            ShareGrant(
                user_id=user.id,
                username=user.username,
                role=UserRole(user.role),
                permission=SharePermission(access.permission),
            )
            for access, user in rows
        ]

    async def revoke_share(
        self, context: AuthContext, password_id: int, user_id: int
    ) -> None:
        _, actor_access = await self._entry_and_access(context, password_id)
        if actor_access.permission != EntryPermission.owner:
            raise Forbidden("Only the owner can manage sharing.")
        access = await self.session.get(PasswordAccessModel, (password_id, user_id))
        if access is None or access.permission == EntryPermission.owner:
            raise NotFound("Share not found.")
        await self.session.delete(access)

    @staticmethod
    def _attachment_response(
        attachment: PasswordAttachmentModel,
    ) -> EncryptedAttachmentResponse:
        if attachment.encrypted_payload is None:
            raise TypesMismatchError(
                "Legacy attachment must be migrated in the client."
            )
        payload = _encode_fernet(attachment.encrypted_payload)
        assert payload is not None
        return EncryptedAttachmentResponse(
            id=attachment.id,
            password_id=attachment.password_id,
            encrypted_payload=payload,
            size_bytes=attachment.size_bytes,
            created=attachment.created,
        )

    async def list_attachments(
        self, context: AuthContext, password_id: int
    ) -> list[EncryptedAttachmentResponse]:
        await self._entry_and_access(context, password_id)
        attachments = (
            await self.session.execute(
                select(PasswordAttachmentModel)
                .where(
                    PasswordAttachmentModel.password_id == password_id,
                    PasswordAttachmentModel.encrypted_payload.is_not(None),
                )
                .order_by(PasswordAttachmentModel.created)
            )
        ).scalars()
        return [self._attachment_response(attachment) for attachment in attachments]

    async def add_attachment(
        self, context: AuthContext, password_id: int, *, encrypted_payload: str
    ) -> EncryptedAttachmentResponse:
        _, access = await self._entry_and_access(context, password_id)
        if access.permission not in (EntryPermission.owner, SharePermission.write):
            raise Forbidden("Write access is required.")
        payload = _decode_fernet(encrypted_payload, label="encrypted attachment")
        if len(payload) > _MAX_ATTACHMENT_CIPHERTEXT:
            raise TypesMismatchError("Attachment ciphertext is too large.")
        count, used = (
            await self.session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(PasswordAttachmentModel.size_bytes), 0),
                ).where(PasswordAttachmentModel.password_id == password_id)
            )
        ).one()
        if count >= _MAX_ATTACHMENTS_PER_ENTRY:
            raise TypesMismatchError(
                "This entry already has the maximum of 20 attachments."
            )
        if used + len(payload) > _MAX_TOTAL_ATTACHMENT_CIPHERTEXT:
            raise TypesMismatchError(
                "Attachment ciphertext would exceed the entry limit."
            )
        attachment = PasswordAttachmentModel(
            password_id=password_id,
            encrypted_payload=payload,
            filename=None,
            content=None,
            content_type=None,
            size_bytes=len(payload),
        )
        self.session.add(attachment)
        await self.session.flush()
        return self._attachment_response(attachment)

    async def replace_attachments(
        self,
        context: AuthContext,
        password_id: int,
        *,
        encrypted_payloads: list[str],
    ) -> list[EncryptedAttachmentResponse]:
        _, access = await self._entry_and_access(context, password_id)
        if access.permission not in (EntryPermission.owner, SharePermission.write):
            raise Forbidden("Write access is required.")
        payloads = _decode_attachment_payloads(encrypted_payloads)

        await self.session.execute(
            delete(PasswordAttachmentModel).where(
                PasswordAttachmentModel.password_id == password_id
            )
        )
        attachments = [
            PasswordAttachmentModel(
                password_id=password_id,
                encrypted_payload=payload,
                filename=None,
                content=None,
                content_type=None,
                size_bytes=len(payload),
            )
            for payload in payloads
        ]
        self.session.add_all(attachments)
        await self.session.flush()
        return [self._attachment_response(attachment) for attachment in attachments]

    async def get_attachment(
        self, context: AuthContext, password_id: int, attachment_id: int
    ) -> EncryptedAttachmentResponse:
        await self._entry_and_access(context, password_id)
        attachment = await self.session.get(PasswordAttachmentModel, attachment_id)
        if attachment is None or attachment.password_id != password_id:
            raise NotFound("Attachment not found.")
        return self._attachment_response(attachment)

    async def delete_attachment(
        self, context: AuthContext, password_id: int, attachment_id: int
    ) -> None:
        _, access = await self._entry_and_access(context, password_id)
        if access.permission not in (EntryPermission.owner, SharePermission.write):
            raise Forbidden("Write access is required.")
        attachment = await self.session.get(PasswordAttachmentModel, attachment_id)
        if attachment is None or attachment.password_id != password_id:
            raise NotFound("Attachment not found.")
        await self.session.delete(attachment)
