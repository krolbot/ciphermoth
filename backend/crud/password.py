import csv
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import pyzipper
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from api.exceptions import Forbidden, NotFound, TypesMismatchError
from crud.auth import AuthContext
from crud.base import BaseCRUD
from helpers import (
    create_encrypted_zip,
    decrypt,
    decrypt_optional,
    encrypt,
    encrypt_optional,
    generate_entry_key,
    unwrap_entry_key,
    verify_master_password,
    wrap_entry_key,
)
from models import (
    PasswordAccessModel,
    PasswordAttachmentModel,
    PasswordModel,
    UserModel,
)
from schemas import (
    CustomField,
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
    UserRole,
)
from validators import normalize_totp_secret

_MAX_JSON_BYTES = 50 * 1024 * 1024
_HISTORY_LIMIT = 10
_PERMISSION_RANK = {"read": 1, "write": 2, "owner": 3}

_CSV_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "title", "account", "login_name", "item name"),
    "username": ("username", "login_username", "user", "email", "login", "e-mail"),
    "value": ("password", "login_password", "pass"),
    "url": ("url", "uri", "login_uri", "website", "web site", "site", "link"),
    "description": ("notes", "note", "description", "comment", "comments", "extra"),
    "folder": ("folder", "grouping", "group", "category", "collection"),
    "totp_secret": (
        "totp",
        "login_totp",
        "otpauth",
        "otp",
        "2fa",
        "otp_auth",
        "totpauth",
    ),
}


@dataclass
class PasswordGrant:
    model: PasswordModel
    access: PasswordAccessModel
    owner_username: str
    entry_key: bytes


class PasswordCRUD(BaseCRUD):
    async def _get_grant(
        self,
        password_id: int,
        context: AuthContext,
        *,
        deleted: bool = False,
        permission: str = "read",
    ) -> PasswordGrant:
        trashed = (
            PasswordModel.deleted.is_not(None)
            if deleted
            else PasswordModel.deleted.is_(None)
        )
        row = (
            await self.session.execute(
                select(PasswordModel, PasswordAccessModel, UserModel.username)
                .join(
                    PasswordAccessModel,
                    PasswordAccessModel.password_id == PasswordModel.id,
                )
                .join(UserModel, UserModel.id == PasswordModel.owner_id)
                .where(
                    PasswordModel.id == password_id,
                    PasswordAccessModel.user_id == context.user.id,
                    trashed,
                )
            )
        ).one_or_none()
        if row is None:
            raise NotFound("Password not found.")
        model, access, owner_username = row
        if _PERMISSION_RANK[access.permission] < _PERMISSION_RANK[permission]:
            raise Forbidden(f"{permission.capitalize()} access is required.")
        try:
            entry_key = unwrap_entry_key(
                context.private_key,
                access.wrapped_key,
                str(access.password_id).encode(),
            )
        except ValueError as exc:
            raise TypesMismatchError("Could not unlock password entry.") from exc
        return PasswordGrant(model, access, owner_username, entry_key)

    def _decrypt_or_raise(self, entry_key: bytes, model: PasswordModel) -> str:
        decrypted = decrypt(entry_key, model.password_value)
        if decrypted is None:
            raise TypesMismatchError(f"Invalid key for '{model.password_name}'.")
        return decrypted

    @staticmethod
    def _encode_json(entry_key: bytes, data: list) -> bytes | None:
        return encrypt(entry_key, json.dumps(data).encode()) if data else None

    @staticmethod
    def _decode_json_list(entry_key: bytes, token: bytes | None) -> list:
        raw = decrypt_optional(entry_key, token)
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def _decode_custom_fields(
        self, entry_key: bytes, model: PasswordModel
    ) -> list[CustomField]:
        return self._normalize_custom_fields(
            self._decode_json_list(entry_key, model.custom_fields)
        )

    def _apply_fields(
        self,
        model: PasswordModel,
        entry_key: bytes,
        password: Password,
    ) -> None:
        model.kind = password.kind
        model.username = password.username
        model.url = encrypt_optional(entry_key, password.url)
        model.totp_secret = encrypt_optional(entry_key, password.totp_secret)
        model.description = password.description
        model.tags = self._encode_json(entry_key, password.tags)
        model.custom_fields = self._encode_json(
            entry_key, [field.model_dump() for field in password.custom_fields]
        )
        model.folder = encrypt_optional(entry_key, password.folder)

    def _to_response(
        self, grant: PasswordGrant, attachment_count: int = 0
    ) -> PasswordResponse:
        model = grant.model
        key = grant.entry_key
        if model.owner_id is None:
            raise TypesMismatchError("Password entry has not been migrated.")
        return PasswordResponse(
            id=model.id,
            owner_id=model.owner_id,
            owner_username=grant.owner_username,
            access=EntryPermission(grant.access.permission),
            password_name=model.password_name,
            kind=model.kind,
            username=model.username,
            password_value=self._decrypt_or_raise(key, model),
            url=decrypt_optional(key, model.url),
            totp_secret=decrypt_optional(key, model.totp_secret),
            description=model.description,
            tags=self._decode_json_list(key, model.tags),
            custom_fields=self._decode_custom_fields(key, model),
            folder=decrypt_optional(key, model.folder),
            favorite=grant.access.favorite,
            backed_up=model.backed_up,
            updated=model.updated,
            deleted=model.deleted,
            password_history=self._decode_json_list(key, model.password_history),
            attachment_count=attachment_count,
        )

    async def _attachment_counts(self, password_ids: list[int]) -> dict[int, int]:
        if not password_ids:
            return {}
        rows = (
            await self.session.execute(
                select(PasswordAttachmentModel.password_id, func.count())
                .where(PasswordAttachmentModel.password_id.in_(password_ids))
                .group_by(PasswordAttachmentModel.password_id)
            )
        ).all()
        return {password_id: count for password_id, count in rows}

    async def _list_grants(
        self, context: AuthContext, *, deleted: bool = False, owner_only: bool = False
    ) -> list[PasswordGrant]:
        trashed = (
            PasswordModel.deleted.is_not(None)
            if deleted
            else PasswordModel.deleted.is_(None)
        )
        query = (
            select(PasswordModel, PasswordAccessModel, UserModel.username)
            .join(
                PasswordAccessModel,
                PasswordAccessModel.password_id == PasswordModel.id,
            )
            .join(UserModel, UserModel.id == PasswordModel.owner_id)
            .where(PasswordAccessModel.user_id == context.user.id, trashed)
        )
        if owner_only:
            query = query.where(PasswordAccessModel.permission == "owner")
        query = query.order_by(
            PasswordModel.deleted.desc()
            if deleted
            else PasswordModel.password_name.asc()
        )
        rows = (await self.session.execute(query)).all()
        grants: list[PasswordGrant] = []
        for model, access, owner_username in rows:
            try:
                key = unwrap_entry_key(
                    context.private_key,
                    access.wrapped_key,
                    str(access.password_id).encode(),
                )
            except ValueError as exc:
                raise TypesMismatchError("Could not unlock password entry.") from exc
            grants.append(PasswordGrant(model, access, owner_username, key))
        return grants

    async def get_passwords(self, context: AuthContext) -> list[PasswordResponse]:
        grants = await self._list_grants(context)
        counts = await self._attachment_counts([grant.model.id for grant in grants])
        return [
            self._to_response(grant, counts.get(grant.model.id, 0)) for grant in grants
        ]

    async def get_trash(self, context: AuthContext) -> list[PasswordResponse]:
        grants = await self._list_grants(context, deleted=True, owner_only=True)
        counts = await self._attachment_counts([grant.model.id for grant in grants])
        return [
            self._to_response(grant, counts.get(grant.model.id, 0)) for grant in grants
        ]

    async def get_password(
        self, password_id: int, context: AuthContext
    ) -> PasswordResponse:
        return self._to_response(await self._get_grant(password_id, context))

    async def create_password(
        self, password: Password, context: AuthContext
    ) -> PasswordCreate:
        entry_key = generate_entry_key()
        model = PasswordModel(
            owner_id=context.user.id,
            encryption_version=2,
            password_name=password.password_name,
            password_value=encrypt(entry_key, password.password_value.encode()),
            favorite=False,
        )
        self._apply_fields(model, entry_key, password)
        self.session.add(model)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise TypesMismatchError(
                "A password with that name already exists."
            ) from exc
        self.session.add(
            PasswordAccessModel(
                password_id=model.id,
                user_id=context.user.id,
                permission="owner",
                wrapped_key=wrap_entry_key(
                    context.user.public_key, entry_key, str(model.id).encode()
                ),
                favorite=password.favorite,
                granted_by=context.user.id,
            )
        )
        await self.session.flush()
        return PasswordCreate(
            id=model.id, created=True, detail="Password created successfully."
        )

    async def update_password(
        self, password_id: int, new_password: Password, context: AuthContext
    ) -> PasswordUpdate:
        grant = await self._get_grant(password_id, context, permission="write")
        model = grant.model
        key = grant.entry_key
        if model.password_name != new_password.password_name:
            conflict = await self.session.scalar(
                select(PasswordModel).where(
                    PasswordModel.owner_id == model.owner_id,
                    PasswordModel.password_name == new_password.password_name,
                    PasswordModel.deleted.is_(None),
                )
            )
            if conflict is not None:
                raise TypesMismatchError("A password with that name already exists.")
            model.password_name = new_password.password_name

        old_value = self._decrypt_or_raise(key, model)
        if old_value != new_password.password_value:
            if new_password.kind == "login":
                history = self._decode_json_list(key, model.password_history)
                history.insert(
                    0,
                    {"value": old_value, "changed_at": datetime.now(UTC).isoformat()},
                )
                del history[_HISTORY_LIMIT:]
                model.password_history = encrypt(key, json.dumps(history).encode())
            model.password_value = encrypt(key, new_password.password_value.encode())
        self._apply_fields(model, key, new_password)
        grant.access.favorite = new_password.favorite
        model.backed_up = False
        await self.session.flush()
        return PasswordUpdate(updated=True, detail="Password updated successfully.")

    async def set_favorite(
        self, password_id: int, favorite: bool, context: AuthContext
    ) -> PasswordUpdate:
        grant = await self._get_grant(password_id, context)
        grant.access.favorite = favorite
        await self.session.flush()
        detail = "Added to favorites." if favorite else "Removed from favorites."
        return PasswordUpdate(updated=True, detail=detail)

    async def delete_password(
        self, password_id: int, context: AuthContext
    ) -> PasswordDelete:
        grant = await self._get_grant(password_id, context, permission="owner")
        grant.model.deleted = datetime.now(UTC).replace(tzinfo=None)
        await self.session.flush()
        return PasswordDelete(deleted=True, detail="Password moved to trash.")

    async def restore_password(
        self, password_id: int, context: AuthContext
    ) -> PasswordUpdate:
        grant = await self._get_grant(
            password_id, context, deleted=True, permission="owner"
        )
        conflict = await self.session.scalar(
            select(PasswordModel).where(
                PasswordModel.owner_id == context.user.id,
                PasswordModel.password_name == grant.model.password_name,
                PasswordModel.deleted.is_(None),
            )
        )
        if conflict is not None:
            raise TypesMismatchError(
                "An active password with that name already exists."
            )
        grant.model.deleted = None
        await self.session.flush()
        return PasswordUpdate(updated=True, detail="Password restored from trash.")

    async def purge_password(
        self, password_id: int, context: AuthContext
    ) -> PasswordDelete:
        grant = await self._get_grant(
            password_id, context, deleted=True, permission="owner"
        )
        await self.session.delete(grant.model)
        await self.session.flush()
        return PasswordDelete(deleted=True, detail="Password permanently deleted.")

    async def list_shares(
        self, password_id: int, context: AuthContext
    ) -> list[ShareGrant]:
        await self._get_grant(password_id, context, permission="owner")
        rows = (
            await self.session.execute(
                select(PasswordAccessModel, UserModel)
                .join(UserModel, UserModel.id == PasswordAccessModel.user_id)
                .where(
                    PasswordAccessModel.password_id == password_id,
                    PasswordAccessModel.permission != "owner",
                )
                .order_by(UserModel.username)
            )
        ).all()
        return [
            ShareGrant(
                user_id=user.id,
                username=user.username,
                role=UserRole(user.role),
                permission=SharePermission(access.permission),
            )
            for access, user in rows
        ]

    async def set_share(
        self,
        password_id: int,
        user_id: int,
        permission: SharePermission,
        context: AuthContext,
    ) -> ShareGrant:
        owner_grant = await self._get_grant(password_id, context, permission="owner")
        target = await self.session.get(UserModel, user_id)
        if target is None or not target.active:
            raise NotFound("Active user not found.")
        if target.id == context.user.id:
            raise Forbidden("Owner access cannot be changed.")
        access = await self.session.get(PasswordAccessModel, (password_id, user_id))
        wrapped_key = wrap_entry_key(
            target.public_key, owner_grant.entry_key, str(password_id).encode()
        )
        if access is None:
            access = PasswordAccessModel(
                password_id=password_id,
                user_id=user_id,
                permission=permission,
                wrapped_key=wrapped_key,
                granted_by=context.user.id,
            )
            self.session.add(access)
        else:
            if access.permission == "owner":
                raise Forbidden("Owner access cannot be changed.")
            access.permission = permission
            access.wrapped_key = wrapped_key
            access.granted_by = context.user.id
        await self.session.flush()
        return ShareGrant(
            user_id=target.id,
            username=target.username,
            role=UserRole(target.role),
            permission=permission,
        )

    async def revoke_share(
        self, password_id: int, user_id: int, context: AuthContext
    ) -> None:
        await self._get_grant(password_id, context, permission="owner")
        access = await self.session.get(PasswordAccessModel, (password_id, user_id))
        if access is None:
            raise NotFound("Share not found.")
        if access.permission == "owner":
            raise Forbidden("Owner access cannot be revoked.")
        await self.session.delete(access)
        await self.session.flush()

    async def _verify_password(
        self, context: AuthContext, master_password: str
    ) -> None:
        if not verify_master_password(master_password, context.user.hash_key):
            raise Forbidden("Incorrect master password.")

    async def create_backup(self, master_password: str, context: AuthContext) -> bytes:
        await self._verify_password(context, master_password)
        grants = await self._list_grants(context, owner_only=True)
        entries: list[dict[str, object]] = [
            {
                "name": grant.model.password_name,
                "kind": grant.model.kind,
                "username": grant.model.username,
                "value": self._decrypt_or_raise(grant.entry_key, grant.model),
                "url": decrypt_optional(grant.entry_key, grant.model.url),
                "totp_secret": decrypt_optional(
                    grant.entry_key, grant.model.totp_secret
                ),
                "description": grant.model.description,
                "tags": self._decode_json_list(grant.entry_key, grant.model.tags),
                "custom_fields": [
                    field.model_dump()
                    for field in self._decode_custom_fields(
                        grant.entry_key, grant.model
                    )
                ],
                "folder": decrypt_optional(grant.entry_key, grant.model.folder),
                "favorite": grant.access.favorite,
            }
            for grant in grants
        ]
        for grant in grants:
            grant.model.backed_up = True
        await self.session.flush()
        return create_encrypted_zip(entries, master_password)

    async def _load_existing(self, context: AuthContext) -> dict[str, PasswordGrant]:
        grants = await self._list_grants(context, owner_only=True)
        return {grant.model.password_name: grant for grant in grants}

    async def _upsert_entry(
        self,
        *,
        existing: dict[str, PasswordGrant],
        context: AuthContext,
        on_conflict: OnConflict,
        password: Password,
    ) -> str:
        current = existing.get(password.password_name)
        if current is None:
            created = await self.create_password(password, context)
            current = await self._get_grant(created.id, context)
            existing[password.password_name] = current
            return "imported"
        if on_conflict == OnConflict.skip:
            return "skipped"
        current.model.password_value = encrypt(
            current.entry_key, password.password_value.encode()
        )
        current.model.password_history = None
        self._apply_fields(current.model, current.entry_key, password)
        current.access.favorite = password.favorite
        current.model.backed_up = False
        return "overwritten"

    async def import_passwords(
        self,
        file_bytes: bytes,
        master_password: str,
        context: AuthContext,
        on_conflict: OnConflict,
    ) -> PasswordImportResult:
        await self._verify_password(context, master_password)
        try:
            with pyzipper.AESZipFile(io.BytesIO(file_bytes), "r") as archive:
                archive.setpassword(master_password.encode())
                with archive.open("ciphermoth_backup.json") as entry:
                    raw = entry.read(_MAX_JSON_BYTES + 1)
            if len(raw) > _MAX_JSON_BYTES:
                raise TypesMismatchError("Backup content is too large.")
        except TypesMismatchError:
            raise
        except Exception as exc:
            raise TypesMismatchError("Could not read CipherMoth backup file.") from exc
        try:
            entries = json.loads(raw)["passwords"]
            if not isinstance(entries, list):
                raise ValueError
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise TypesMismatchError("Invalid backup file format.") from exc

        existing = await self._load_existing(context)
        counts = {"imported": 0, "skipped": 0, "overwritten": 0}
        for entry in entries:
            try:
                name, value = entry["name"], entry["value"]
            except (KeyError, TypeError):
                continue
            if not name or not value:
                continue
            raw_tags = entry.get("tags")
            payload = Password(
                password_name=name,
                password_value=value,
                kind="note" if entry.get("kind") == "note" else "login",
                username=entry.get("username"),
                url=entry.get("url"),
                totp_secret=entry.get("totp_secret"),
                description=entry.get("description"),
                tags=raw_tags if isinstance(raw_tags, list) else [],
                custom_fields=self._normalize_custom_fields(entry.get("custom_fields")),
                folder=entry.get("folder"),
                favorite=bool(entry.get("favorite", False)),
            )
            outcome = await self._upsert_entry(
                existing=existing,
                context=context,
                on_conflict=on_conflict,
                password=payload,
            )
            counts[outcome] += 1
        await self.session.flush()
        return self._result(counts)

    async def import_passwords_csv(
        self,
        file_bytes: bytes,
        context: AuthContext,
        on_conflict: OnConflict,
    ) -> PasswordImportResult:
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise TypesMismatchError("CSV file must be UTF-8 encoded.") from exc
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise TypesMismatchError("CSV file has no header row.")
        column_for = self._map_csv_columns(reader.fieldnames)
        if "name" not in column_for or "value" not in column_for:
            raise TypesMismatchError(
                "CSV must have a name/title column and a password column."
            )

        existing = await self._load_existing(context)
        counts = {"imported": 0, "skipped": 0, "overwritten": 0}
        for row in reader:
            name = (row.get(column_for["name"]) or "").strip()
            value = row.get(column_for["value"]) or ""
            if not name or not value:
                continue
            payload = Password(
                password_name=name,
                password_value=value,
                kind="login",
                username=self._csv_cell(row, column_for, "username"),
                url=self._csv_cell(row, column_for, "url"),
                totp_secret=self._csv_totp(row, column_for),
                description=self._csv_cell(row, column_for, "description"),
                folder=self._csv_cell(row, column_for, "folder"),
            )
            outcome = await self._upsert_entry(
                existing=existing,
                context=context,
                on_conflict=on_conflict,
                password=payload,
            )
            counts[outcome] += 1
        await self.session.flush()
        return self._result(counts)

    @staticmethod
    def _normalize_custom_fields(raw: object) -> list[CustomField]:
        if not isinstance(raw, list):
            return []
        return [
            CustomField(
                label=str(item.get("label")),
                value=str(item.get("value", "")),
                hidden=bool(item.get("hidden", False)),
            )
            for item in raw
            if isinstance(item, dict) and item.get("label")
        ]

    @staticmethod
    def _map_csv_columns(fieldnames: Sequence[str]) -> dict[str, str]:
        normalized = {(name or "").strip().lower(): name for name in fieldnames}
        column_for: dict[str, str] = {}
        for field, aliases in _CSV_FIELD_ALIASES.items():
            for alias in aliases:
                if alias in normalized:
                    column_for[field] = normalized[alias]
                    break
        return column_for

    @staticmethod
    def _csv_cell(
        row: dict[str, str], column_for: dict[str, str], field: str
    ) -> str | None:
        column = column_for.get(field)
        if not column:
            return None
        value = (row.get(column) or "").strip()
        return value or None

    @staticmethod
    def _csv_totp(row: dict[str, str], column_for: dict[str, str]) -> str | None:
        raw = PasswordCRUD._csv_cell(row, column_for, "totp_secret")
        try:
            return normalize_totp_secret(raw)
        except ValueError:
            return None

    @staticmethod
    def _result(counts: dict[str, int]) -> PasswordImportResult:
        return PasswordImportResult(
            imported=counts["imported"],
            skipped=counts["skipped"],
            overwritten=counts["overwritten"],
            total=counts["imported"] + counts["skipped"] + counts["overwritten"],
        )
