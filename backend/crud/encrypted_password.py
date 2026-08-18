import base64
import binascii
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
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
        deleted: bool = False,
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
                if deleted
                else PasswordModel.deleted.is_(None),
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
        encrypted_payload = _encode_fernet(entry.encrypted_payload)
        wrapped_key = _encode(access.wrapped_key)
        if encrypted_payload is None or wrapped_key is None:
            raise TypesMismatchError("Invalid encrypted entry.")
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
            granted_by=context.user.id,
        )
        self.session.add(access)
        self.session.add_all(
            PasswordAttachmentModel(
                password_id=entry.id,
                encrypted_payload=payload,
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

    async def empty_trash(self, context: AuthContext) -> int:
        deleted_ids = (
            await self.session.scalars(
                delete(PasswordModel)
                .where(
                    PasswordModel.owner_id == context.user.id,
                    PasswordModel.deleted.is_not(None),
                )
                .returning(PasswordModel.id)
            )
        ).all()
        await self.session.flush()
        return len(deleted_ids)

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
        payload = _encode_fernet(attachment.encrypted_payload)
        if payload is None:
            raise TypesMismatchError("Invalid encrypted attachment.")
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
