from sqlalchemy import func, select

from api.exceptions import NotFound, TypesMismatchError
from crud.auth import AuthContext
from crud.base import BaseCRUD
from crud.password import PasswordCRUD, PasswordGrant
from helpers import decrypt, decrypt_bytes, encrypt, encrypt_optional
from models import PasswordAttachmentModel
from schemas import AttachmentResponse

_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
_MAX_ATTACHMENTS_PER_ENTRY = 20
_MAX_TOTAL_BYTES = 25 * 1024 * 1024


class AttachmentCRUD(BaseCRUD):
    async def _grant(
        self, password_id: int, context: AuthContext, permission: str = "read"
    ) -> PasswordGrant:
        return await PasswordCRUD(self.session)._get_grant(
            password_id, context, permission=permission
        )

    async def _get_attachment(
        self, password_id: int, attachment_id: int
    ) -> PasswordAttachmentModel:
        model = await self.session.scalar(
            select(PasswordAttachmentModel).where(
                PasswordAttachmentModel.id == attachment_id,
                PasswordAttachmentModel.password_id == password_id,
            )
        )
        if model is None:
            raise NotFound("Attachment not found.")
        return model

    @staticmethod
    def _to_response(
        model: PasswordAttachmentModel, entry_key: bytes
    ) -> AttachmentResponse:
        filename = decrypt(entry_key, model.filename)
        if filename is None:
            raise TypesMismatchError("Invalid key for attachment.")
        return AttachmentResponse(
            id=model.id,
            filename=filename,
            content_type=(
                decrypt(entry_key, model.content_type)
                if model.content_type is not None
                else None
            ),
            size_bytes=model.size_bytes,
            created=model.created,
        )

    async def list_attachments(
        self, password_id: int, context: AuthContext
    ) -> list[AttachmentResponse]:
        grant = await self._grant(password_id, context)
        models = (
            await self.session.execute(
                select(PasswordAttachmentModel)
                .where(PasswordAttachmentModel.password_id == password_id)
                .order_by(PasswordAttachmentModel.created)
            )
        ).scalars()
        return [self._to_response(model, grant.entry_key) for model in models]

    async def add_attachment(
        self,
        password_id: int,
        filename: str,
        content_type: str | None,
        data: bytes,
        context: AuthContext,
    ) -> AttachmentResponse:
        if not data:
            raise TypesMismatchError("Attachment is empty.")
        if len(data) > _MAX_ATTACHMENT_BYTES:
            raise TypesMismatchError("Attachment too large. Maximum size is 5 MB.")
        grant = await self._grant(password_id, context, "write")

        count = await self.session.scalar(
            select(func.count())
            .select_from(PasswordAttachmentModel)
            .where(PasswordAttachmentModel.password_id == password_id)
        )
        if (count or 0) >= _MAX_ATTACHMENTS_PER_ENTRY:
            raise TypesMismatchError(
                f"This entry already has the maximum of "
                f"{_MAX_ATTACHMENTS_PER_ENTRY} attachments."
            )
        used = await self.session.scalar(
            select(
                func.coalesce(func.sum(PasswordAttachmentModel.size_bytes), 0)
            ).where(PasswordAttachmentModel.password_id == password_id)
        )
        if (used or 0) + len(data) > _MAX_TOTAL_BYTES:
            raise TypesMismatchError(
                "Attachments for this entry would exceed the 25 MB total limit."
            )

        model = PasswordAttachmentModel(
            password_id=password_id,
            filename=encrypt(grant.entry_key, filename.encode()),
            content=encrypt(grant.entry_key, data),
            content_type=encrypt_optional(grant.entry_key, content_type),
            size_bytes=len(data),
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_response(model, grant.entry_key)

    async def get_attachment_data(
        self, password_id: int, attachment_id: int, context: AuthContext
    ) -> tuple[str, str | None, bytes]:
        grant = await self._grant(password_id, context)
        model = await self._get_attachment(password_id, attachment_id)
        filename = decrypt(grant.entry_key, model.filename)
        data = decrypt_bytes(grant.entry_key, model.content)
        if filename is None or data is None:
            raise TypesMismatchError("Invalid key for attachment.")
        content_type = (
            decrypt(grant.entry_key, model.content_type)
            if model.content_type is not None
            else None
        )
        return filename, content_type, data

    async def delete_attachment(
        self, password_id: int, attachment_id: int, context: AuthContext
    ) -> None:
        await self._grant(password_id, context, "write")
        model = await self._get_attachment(password_id, attachment_id)
        await self.session.delete(model)
        await self.session.flush()
