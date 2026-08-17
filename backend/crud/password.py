import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select

from api.exceptions import Forbidden, NotFound, TypesMismatchError
from crud.auth import AuthContext
from crud.base import BaseCRUD
from helpers import (
    decrypt,
    decrypt_optional,
    encrypt,
    encrypt_optional,
    unwrap_entry_key,
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
    Password,
    PasswordResponse,
    PasswordUpdate,
)

_HISTORY_LIMIT = 10
_PERMISSION_RANK = {"read": 1, "write": 2, "owner": 3}


@dataclass
class PasswordGrant:
    model: PasswordModel
    access: PasswordAccessModel
    owner_username: str
    entry_key: bytes


class PasswordCRUD(BaseCRUD):
    @staticmethod
    def _require_service_key(context: AuthContext) -> bytes:
        if context.private_key is None:
            raise Forbidden("Server-side decryption is limited to service identities.")
        return context.private_key

    async def _get_grant(
        self,
        password_id: int,
        context: AuthContext,
        *,
        permission: str = "read",
    ) -> PasswordGrant:
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
                    PasswordModel.deleted.is_(None),
                    PasswordAccessModel.user_id == context.user.id,
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
                self._require_service_key(context),
                access.wrapped_key,
                b"" if model.encryption_version >= 3 else str(password_id).encode(),
            )
        except ValueError as exc:
            raise TypesMismatchError("Could not unlock password entry.") from exc
        return PasswordGrant(model, access, owner_username, entry_key)

    async def _list_grants(self, context: AuthContext) -> list[PasswordGrant]:
        private_key = self._require_service_key(context)
        rows = (
            await self.session.execute(
                select(PasswordModel, PasswordAccessModel, UserModel.username)
                .join(
                    PasswordAccessModel,
                    PasswordAccessModel.password_id == PasswordModel.id,
                )
                .join(UserModel, UserModel.id == PasswordModel.owner_id)
                .where(
                    PasswordAccessModel.user_id == context.user.id,
                    PasswordModel.deleted.is_(None),
                )
                .order_by(PasswordModel.updated.desc())
            )
        ).all()
        grants = []
        for model, access, owner_username in rows:
            try:
                entry_key = unwrap_entry_key(
                    private_key,
                    access.wrapped_key,
                    b"" if model.encryption_version >= 3 else str(model.id).encode(),
                )
            except ValueError as exc:
                raise TypesMismatchError("Could not unlock password entry.") from exc
            grants.append(PasswordGrant(model, access, owner_username, entry_key))
        return grants

    @staticmethod
    def _decode_json_list(key: bytes, token: bytes | None) -> list:
        raw = decrypt_optional(key, token)
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []

    @staticmethod
    def _custom_fields(raw: object) -> list[CustomField]:
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

    def _response(
        self, grant: PasswordGrant, attachment_count: int = 0
    ) -> PasswordResponse:
        model = grant.model
        if model.owner_id is None:
            raise TypesMismatchError("Password entry has no owner.")
        if model.encryption_version >= 3:
            if model.encrypted_payload is None:
                raise TypesMismatchError("Encrypted password payload is missing.")
            cleartext = decrypt(grant.entry_key, model.encrypted_payload)
            if cleartext is None:
                raise TypesMismatchError("Could not decrypt password payload.")
            try:
                payload = json.loads(cleartext)
                password = Password.model_validate(payload)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                raise TypesMismatchError("Invalid encrypted password payload.") from exc
            favorite = False
            if grant.access.encrypted_preferences is not None:
                preferences_raw = decrypt(
                    grant.entry_key, grant.access.encrypted_preferences
                )
                try:
                    preferences = json.loads(preferences_raw or "")
                except json.JSONDecodeError as exc:
                    raise TypesMismatchError(
                        "Invalid encrypted password preferences."
                    ) from exc
                if not isinstance(preferences, dict):
                    raise TypesMismatchError("Invalid encrypted password preferences.")
                favorite = bool(preferences.get("favorite", False))
            password.favorite = favorite
            return PasswordResponse(
                **password.model_dump(),
                id=model.id,
                owner_id=model.owner_id,
                owner_username=grant.owner_username,
                access=EntryPermission(grant.access.permission),
                backed_up=bool(payload.get("backed_up", False)),
                updated=model.updated,
                deleted=model.deleted,
                password_history=payload.get("password_history", []),
                attachment_count=attachment_count,
            )

        if model.password_name is None or model.password_value is None:
            raise TypesMismatchError("Legacy password data is incomplete.")
        password_value = decrypt(grant.entry_key, model.password_value)
        if password_value is None:
            raise TypesMismatchError("Could not decrypt legacy password value.")
        return PasswordResponse(
            id=model.id,
            owner_id=model.owner_id,
            owner_username=grant.owner_username,
            access=EntryPermission(grant.access.permission),
            password_name=model.password_name,
            kind=model.kind,
            username=model.username,
            password_value=password_value,
            url=decrypt_optional(grant.entry_key, model.url),
            totp_secret=decrypt_optional(grant.entry_key, model.totp_secret),
            description=model.description,
            tags=self._decode_json_list(grant.entry_key, model.tags),
            custom_fields=self._custom_fields(
                self._decode_json_list(grant.entry_key, model.custom_fields)
            ),
            folder=decrypt_optional(grant.entry_key, model.folder),
            favorite=grant.access.favorite,
            backed_up=model.backed_up,
            updated=model.updated,
            deleted=model.deleted,
            password_history=self._decode_json_list(
                grant.entry_key, model.password_history
            ),
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

    async def get_passwords(self, context: AuthContext) -> list[PasswordResponse]:
        grants = await self._list_grants(context)
        counts = await self._attachment_counts([grant.model.id for grant in grants])
        return [
            self._response(grant, counts.get(grant.model.id, 0)) for grant in grants
        ]

    async def get_password(
        self, password_id: int, context: AuthContext
    ) -> PasswordResponse:
        grant = await self._get_grant(password_id, context)
        counts = await self._attachment_counts([password_id])
        return self._response(grant, counts.get(password_id, 0))

    async def update_password(
        self, password_id: int, new_password: Password, context: AuthContext
    ) -> PasswordUpdate:
        grant = await self._get_grant(password_id, context, permission="write")
        model = grant.model
        key = grant.entry_key
        if model.encryption_version >= 3:
            if model.encrypted_payload is None:
                raise TypesMismatchError("Encrypted password payload is missing.")
            current_raw = decrypt(key, model.encrypted_payload)
            if current_raw is None:
                raise TypesMismatchError("Could not decrypt password payload.")
            try:
                current = json.loads(current_raw)
            except json.JSONDecodeError as exc:
                raise TypesMismatchError("Invalid encrypted password payload.") from exc
            history = current.get("password_history", [])
            if current.get("password_value") != new_password.password_value:
                if new_password.kind == "login" and current.get("password_value"):
                    history.insert(
                        0,
                        {
                            "value": current["password_value"],
                            "changed_at": datetime.now(UTC).isoformat(),
                        },
                    )
                    del history[_HISTORY_LIMIT:]
            payload = new_password.model_dump(exclude={"favorite"})
            payload.update(password_history=history, backed_up=False)
            model.encrypted_payload = encrypt(key, json.dumps(payload).encode())
            grant.access.encrypted_preferences = encrypt(
                key, json.dumps({"favorite": new_password.favorite}).encode()
            )
        else:
            if model.password_value is None:
                raise TypesMismatchError("Legacy password value is missing.")
            old_value = decrypt(key, model.password_value)
            if old_value != new_password.password_value:
                history = self._decode_json_list(key, model.password_history)
                if new_password.kind == "login" and old_value:
                    history.insert(
                        0,
                        {
                            "value": old_value,
                            "changed_at": datetime.now(UTC).isoformat(),
                        },
                    )
                    del history[_HISTORY_LIMIT:]
                model.password_history = (
                    encrypt(key, json.dumps(history).encode()) if history else None
                )
                model.password_value = encrypt(
                    key, new_password.password_value.encode()
                )
            model.password_name = new_password.password_name
            model.kind = new_password.kind
            model.username = new_password.username
            model.url = encrypt_optional(key, new_password.url)
            model.totp_secret = encrypt_optional(key, new_password.totp_secret)
            model.description = new_password.description
            model.tags = (
                encrypt(key, json.dumps(new_password.tags).encode())
                if new_password.tags
                else None
            )
            model.custom_fields = (
                encrypt(
                    key,
                    json.dumps(
                        [field.model_dump() for field in new_password.custom_fields]
                    ).encode(),
                )
                if new_password.custom_fields
                else None
            )
            model.folder = encrypt_optional(key, new_password.folder)
            model.backed_up = False
        await self.session.flush()
        return PasswordUpdate(updated=True, detail="Password updated successfully.")
