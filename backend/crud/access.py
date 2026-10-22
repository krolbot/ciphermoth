from sqlalchemy import delete, or_, select

from crud.attachment import AttachmentCRUD
from crud.auth import AuthContext
from crud.password import PasswordCRUD
from crud.records import find_entry
from errors import Forbidden, InvalidRequest, NotFound
from helpers import VaultKey
from models import EntryAccessModel, EntryModel, UserModel
from schemas import (
    AttachmentResponse,
    EntryAccess,
    EntryPermission,
    OnConflict,
    Password,
    PasswordCreate,
    PasswordDelete,
    PasswordImportResult,
    PasswordResponse,
    PasswordUpdate,
    ShareGrant,
    SharePermission,
    ShareTarget,
)


class EntryACL:
    def __init__(self, session, context: AuthContext) -> None:
        self.session = session
        self.context = context

    async def permission(self, entry_id: int) -> EntryPermission:
        row = (
            await self.session.execute(
                select(EntryModel.owner_id, EntryAccessModel.permission)
                .outerjoin(
                    EntryAccessModel,
                    (EntryAccessModel.entry_id == EntryModel.id)
                    & (EntryAccessModel.user_id == self.context.user.id),
                )
                .where(EntryModel.id == entry_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFound("Password not found.")
        owner_id, grant = row
        if owner_id == self.context.user.id:
            return EntryPermission.owner
        if grant in (SharePermission.read, SharePermission.write):
            return EntryPermission(grant)
        raise NotFound("Password not found.")

    async def require(self, entry_id: int, needed: EntryPermission) -> EntryPermission:
        permission = await self.permission(entry_id)
        if needed == EntryPermission.owner and permission != EntryPermission.owner:
            raise Forbidden("Only the entry owner can perform this action.")
        if needed == EntryPermission.write and permission == EntryPermission.read:
            raise Forbidden("Write access is required.")
        return permission

    async def entry_by_name(
        self,
        name: str,
        key: VaultKey,
        needed: EntryPermission,
        *,
        deleted: bool = False,
        entry_id: int | None = None,
    ) -> EntryModel:
        model, _ = await find_entry(
            self.session, key, name, deleted=deleted, entry_id=entry_id
        )
        await self.require(model.id, needed)
        return model

    async def visible_ids(self, *, deleted: bool) -> list[int]:
        statement = (
            select(EntryModel.id)
            .outerjoin(
                EntryAccessModel,
                (EntryAccessModel.entry_id == EntryModel.id)
                & (EntryAccessModel.user_id == self.context.user.id),
            )
            .where(
                EntryModel.deleted.is_not(None)
                if deleted
                else EntryModel.deleted.is_(None),
                or_(
                    EntryModel.owner_id == self.context.user.id,
                    EntryAccessModel.user_id == self.context.user.id,
                ),
            )
            .distinct()
        )
        return list(await self.session.scalars(statement))

    async def access_map(self, *, deleted: bool = False) -> list[EntryAccess]:
        ids = await self.visible_ids(deleted=deleted)
        if not ids:
            return []
        rows = (
            await self.session.execute(
                select(
                    EntryModel.id,
                    EntryModel.owner_id,
                    UserModel.username,
                    EntryAccessModel.permission,
                )
                .join(UserModel, UserModel.id == EntryModel.owner_id)
                .outerjoin(
                    EntryAccessModel,
                    (EntryAccessModel.entry_id == EntryModel.id)
                    & (EntryAccessModel.user_id == self.context.user.id),
                )
                .where(EntryModel.id.in_(ids))
                .order_by(EntryModel.id)
            )
        ).all()
        return [
            EntryAccess(
                entry_id=entry_id,
                owner_id=owner_id,
                owner_username=owner_username,
                access=(
                    EntryPermission.owner
                    if owner_id == self.context.user.id
                    else EntryPermission(grant)
                ),
            )
            for entry_id, owner_id, owner_username, grant in rows
        ]

    async def list_shares(self, entry_id: int) -> list[ShareGrant]:
        await self.require(entry_id, EntryPermission.owner)
        rows = (
            await self.session.execute(
                select(
                    UserModel.id,
                    UserModel.username,
                    UserModel.role,
                    EntryAccessModel.permission,
                )
                .join(EntryAccessModel, EntryAccessModel.user_id == UserModel.id)
                .where(EntryAccessModel.entry_id == entry_id)
                .order_by(UserModel.username)
            )
        ).all()
        return [
            ShareGrant(
                user_id=user_id,
                username=username,
                role=role,
                permission=permission,
            )
            for user_id, username, role, permission in rows
        ]

    async def set_share(
        self, entry_id: int, user_id: int, permission: SharePermission
    ) -> ShareGrant:
        await self.require(entry_id, EntryPermission.owner)
        entry = await self.session.get_one(EntryModel, entry_id)
        target = await self.session.get(UserModel, user_id)
        if target is None or not target.active:
            raise NotFound("Share target not found.")
        if target.id == entry.owner_id:
            raise InvalidRequest("The owner already has full access.")
        grant = await self.session.get(EntryAccessModel, (entry_id, user_id))
        if grant is None:
            grant = EntryAccessModel(
                entry_id=entry_id,
                user_id=user_id,
                granted_by=self.context.user.id,
                permission=permission,
            )
            self.session.add(grant)
        else:
            grant.permission = permission
            grant.granted_by = self.context.user.id
        await self.session.flush()
        return ShareGrant(
            user_id=target.id,
            username=target.username,
            role=target.role,
            permission=permission,
        )

    async def revoke_share(self, entry_id: int, user_id: int) -> None:
        await self.require(entry_id, EntryPermission.owner)
        deleted = await self.session.execute(
            delete(EntryAccessModel).where(
                EntryAccessModel.entry_id == entry_id,
                EntryAccessModel.user_id == user_id,
            )
        )
        if deleted.rowcount == 0:
            raise NotFound("Share not found.")

    async def relinquish(self, entry_id: int) -> None:
        permission = await self.permission(entry_id)
        if permission == EntryPermission.owner:
            raise Forbidden("The owner cannot relinquish their own entry.")
        await self.session.execute(
            delete(EntryAccessModel).where(
                EntryAccessModel.entry_id == entry_id,
                EntryAccessModel.user_id == self.context.user.id,
            )
        )

    async def share_targets(self) -> list[ShareTarget]:
        users = (
            await self.session.scalars(
                select(UserModel)
                .where(
                    UserModel.active.is_(True),
                    UserModel.id != self.context.user.id,
                )
                .order_by(UserModel.username)
            )
        ).all()
        return [
            ShareTarget(id=user.id, username=user.username, role=user.role)
            for user in users
        ]


class AuthorizedPasswordCRUD(PasswordCRUD):
    def __init__(self, session, context: AuthContext) -> None:
        super().__init__(session, context.owner_id)
        self.context = context
        self.acl = EntryACL(session, context)

    async def load_active(self) -> dict[bytes, EntryModel]:
        models = await self.session.scalars(
            select(EntryModel).where(
                EntryModel.deleted.is_(None),
                EntryModel.owner_id == self.context.owner_id,
            )
        )
        return {model.name_index: model for model in models}

    async def get_passwords(self, key: VaultKey) -> list[PasswordResponse]:
        listed = await self._listed(
            key, deleted=False, entry_ids=await self.acl.visible_ids(deleted=False)
        )
        return await self._with_access(listed, deleted=False)

    async def get_trash(self, key: VaultKey) -> list[PasswordResponse]:
        listed = await self._listed(
            key, deleted=True, entry_ids=await self.acl.visible_ids(deleted=True)
        )
        return await self._with_access(listed, deleted=True)

    async def _with_access(
        self, listed: list[PasswordResponse], *, deleted: bool
    ) -> list[PasswordResponse]:
        access = {
            item.entry_id: item for item in await self.acl.access_map(deleted=deleted)
        }
        return [
            response.model_copy(
                update={
                    "owner_id": access[response.id].owner_id,
                    "owner_username": access[response.id].owner_username,
                    "access": access[response.id].access,
                }
            )
            for response in listed
        ]

    async def get_password(self, password_name: str, key: VaultKey) -> PasswordResponse:
        model = await self.acl.entry_by_name(password_name, key, EntryPermission.read)
        response = await super().get_password(password_name, key)
        owner = await self.session.get_one(UserModel, model.owner_id)
        return response.model_copy(
            update={
                "owner_id": model.owner_id,
                "owner_username": owner.username,
                "access": await self.acl.permission(model.id),
            }
        )

    async def create_password(
        self, password: Password, key: VaultKey
    ) -> PasswordCreate:
        result = await super().create_password(password, key)
        model, _ = await find_entry(self.session, key, password.password_name)
        model.owner_id = self.context.owner_id
        if self.context.user.role == "service":
            self.session.add(
                EntryAccessModel(
                    entry_id=model.id,
                    user_id=self.context.user.id,
                    granted_by=self.context.owner_id,
                    permission=SharePermission.write,
                )
            )
        await self.session.flush()
        return result

    async def update_password(
        self, password_name: str, new_password: Password, key: VaultKey
    ) -> PasswordUpdate:
        await self.acl.entry_by_name(password_name, key, EntryPermission.write)
        return await super().update_password(password_name, new_password, key)

    async def set_favorite(
        self, password_name: str, favorite: bool, key: VaultKey
    ) -> PasswordUpdate:
        await self.acl.entry_by_name(password_name, key, EntryPermission.write)
        return await super().set_favorite(password_name, favorite, key)

    async def delete_password(
        self, password_name: str, key: VaultKey
    ) -> PasswordDelete:
        await self.acl.entry_by_name(password_name, key, EntryPermission.write)
        return await super().delete_password(password_name, key)

    async def restore_password(
        self, password_name: str, key: VaultKey, *, entry_id: int | None = None
    ) -> PasswordUpdate:
        await self.acl.entry_by_name(
            password_name,
            key,
            EntryPermission.write,
            deleted=True,
            entry_id=entry_id,
        )
        return await super().restore_password(password_name, key, entry_id=entry_id)

    async def purge_password(
        self, password_name: str, key: VaultKey, *, entry_id: int | None = None
    ) -> PasswordDelete:
        await self.acl.entry_by_name(
            password_name,
            key,
            EntryPermission.owner,
            deleted=True,
            entry_id=entry_id,
        )
        return await super().purge_password(password_name, key, entry_id=entry_id)

    async def import_passwords_csv(
        self, file_bytes: bytes, key: VaultKey, on_conflict: OnConflict
    ) -> PasswordImportResult:
        return await super().import_passwords_csv(file_bytes, key, on_conflict)


class AuthorizedAttachmentCRUD(AttachmentCRUD):
    def __init__(self, session, context: AuthContext) -> None:
        super().__init__(session)
        self.acl = EntryACL(session, context)

    async def list_attachments(
        self, password_name: str, key: VaultKey
    ) -> list[AttachmentResponse]:
        await self.acl.entry_by_name(password_name, key, EntryPermission.read)
        return await super().list_attachments(password_name, key)

    async def add_attachment(
        self,
        password_name: str,
        filename: str,
        content_type: str | None,
        data: bytes,
        key: VaultKey,
    ) -> AttachmentResponse:
        await self.acl.entry_by_name(password_name, key, EntryPermission.write)
        return await super().add_attachment(
            password_name, filename, content_type, data, key
        )

    async def get_attachment_data(
        self, password_name: str, attachment_id: int, key: VaultKey
    ) -> tuple[str, str | None, bytes]:
        await self.acl.entry_by_name(password_name, key, EntryPermission.read)
        return await super().get_attachment_data(password_name, attachment_id, key)

    async def delete_attachment(
        self, password_name: str, attachment_id: int, key: VaultKey
    ) -> None:
        await self.acl.entry_by_name(password_name, key, EntryPermission.write)
        await super().delete_attachment(password_name, attachment_id, key)
