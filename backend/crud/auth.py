import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from api.exceptions import Forbidden, NotFound, TypesMismatchError, Unauthorized
from crud.base import BaseCRUD
from crud.master_password import fetch_master_password
from helpers import (
    create_user_keypair,
    decrypt,
    decrypt_bytes,
    decrypt_user_private_key,
    encrypt,
    encrypt_user_private_key,
    generate_entry_key,
    generate_key_derivation,
    hash_master_password,
    verify_master_password,
    wrap_entry_key,
)
from models import (
    InstanceStateModel,
    PasswordAccessModel,
    PasswordAttachmentModel,
    PasswordModel,
    SessionModel,
    SettingsModel,
    UserModel,
)
from schemas import (
    AuthSessionResponse,
    AuthStatus,
    AuthUser,
    ShareTarget,
    UserCreateResponse,
    UserRole,
)
from validators import validate_master_password_strength

_SESSION_LIFETIME = timedelta(hours=12)
_OPTIONAL_ENCRYPTED_FIELDS = (
    "url",
    "totp_secret",
    "tags",
    "custom_fields",
    "folder",
    "password_history",
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class AuthContext:
    user: UserModel
    private_key: bytes
    token_hash: str


class AuthCRUD(BaseCRUD):
    @staticmethod
    def _to_user(model: UserModel) -> AuthUser:
        return AuthUser(
            id=model.id,
            username=model.username,
            role=UserRole(model.role),
            active=model.active,
            must_change_password=model.must_change_password,
        )

    async def status(self) -> AuthStatus:
        user_count = await self.session.scalar(
            select(func.count()).select_from(UserModel)
        )
        legacy = await fetch_master_password(self.session) is not None
        return AuthStatus(
            initialized=bool(user_count), legacy_vault=legacy and not user_count
        )

    async def _new_session(
        self, user: UserModel, key_derivation: bytes
    ) -> AuthSessionResponse:
        await self.session.execute(
            delete(SessionModel).where(SessionModel.expires_at <= _now())
        )
        token = secrets.token_urlsafe(32)
        self.session.add(
            SessionModel(
                user_id=user.id,
                token_hash=_token_hash(token),
                expires_at=_now() + _SESSION_LIFETIME,
            )
        )
        await self.session.flush()
        return AuthSessionResponse(
            user=self._to_user(user),
            token=token,
            key_derivation=key_derivation.decode(),
        )

    async def _migrate_legacy_vault(self, user: UserModel, legacy_key: bytes) -> None:
        passwords = (
            await self.session.execute(select(PasswordModel).order_by(PasswordModel.id))
        ).scalars()
        for password in passwords:
            entry_key = generate_entry_key()
            value = decrypt(legacy_key, password.password_value)
            if value is None:
                raise TypesMismatchError(
                    f"Could not decrypt legacy entry '{password.password_name}'."
                )
            password.password_value = encrypt(entry_key, value.encode())
            for field in _OPTIONAL_ENCRYPTED_FIELDS:
                token = getattr(password, field)
                if token is None:
                    continue
                plaintext = decrypt(legacy_key, token)
                if plaintext is None:
                    raise TypesMismatchError(
                        f"Could not decrypt legacy entry '{password.password_name}'."
                    )
                setattr(password, field, encrypt(entry_key, plaintext.encode()))

            attachments = (
                await self.session.execute(
                    select(PasswordAttachmentModel).where(
                        PasswordAttachmentModel.password_id == password.id
                    )
                )
            ).scalars()
            for attachment in attachments:
                filename = decrypt_bytes(legacy_key, attachment.filename)
                content = decrypt_bytes(legacy_key, attachment.content)
                content_type = (
                    decrypt_bytes(legacy_key, attachment.content_type)
                    if attachment.content_type is not None
                    else None
                )
                if filename is None or content is None:
                    raise TypesMismatchError(
                        f"Could not decrypt attachment for '{password.password_name}'."
                    )
                attachment.filename = encrypt(entry_key, filename)
                attachment.content = encrypt(entry_key, content)
                attachment.content_type = (
                    encrypt(entry_key, content_type)
                    if content_type is not None
                    else None
                )

            password.owner_id = user.id
            password.encryption_version = 2
            self.session.add(
                PasswordAccessModel(
                    password_id=password.id,
                    user_id=user.id,
                    permission="owner",
                    wrapped_key=wrap_entry_key(
                        user.public_key, entry_key, str(password.id).encode()
                    ),
                    favorite=password.favorite,
                    granted_by=user.id,
                )
            )

        settings = (
            await self.session.execute(
                select(SettingsModel).where(SettingsModel.user_id.is_(None))
            )
        ).scalars()
        for model in settings:
            model.user_id = user.id

    async def bootstrap(
        self, username: str, master_password: str
    ) -> AuthSessionResponse:
        state = (
            await self.session.execute(
                select(InstanceStateModel)
                .where(InstanceStateModel.id == 1)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if state is None:
            raise NotFound("Instance state is missing. Run database migrations.")
        user_count = await self.session.scalar(
            select(func.count()).select_from(UserModel)
        )
        if state.bootstrapped_at is not None or user_count:
            raise Forbidden("CipherMoth is already initialized.")

        username = username.strip().lower()
        legacy = await fetch_master_password(self.session)
        if legacy is not None:
            if not verify_master_password(master_password, legacy.hash_key):
                raise Forbidden("Current master password is incorrect.")
            salt = legacy.salt
            password_hash = legacy.hash_key
        else:
            try:
                validate_master_password_strength(master_password)
            except ValueError as exc:
                raise TypesMismatchError(str(exc)) from exc
            salt = os.urandom(16)
            password_hash = hash_master_password(master_password)

        key_derivation = generate_key_derivation(salt, master_password)
        public_key, encrypted_private_key = create_user_keypair(key_derivation)
        user = UserModel(
            username=username,
            role=UserRole.admin,
            active=True,
            must_change_password=False,
            salt=salt,
            hash_key=password_hash,
            public_key=public_key,
            encrypted_private_key=encrypted_private_key,
        )
        self.session.add(user)
        await self.session.flush()

        if legacy is not None:
            await self._migrate_legacy_vault(user, key_derivation)
            await self.session.delete(legacy)

        state.bootstrapped_at = _now()
        await self.session.flush()
        return await self._new_session(user, key_derivation)

    async def login(self, username: str, master_password: str) -> AuthSessionResponse:
        user = (
            await self.session.execute(
                select(UserModel).where(UserModel.username == username.strip().lower())
            )
        ).scalar_one_or_none()
        if user is None or not verify_master_password(master_password, user.hash_key):
            raise Unauthorized("Invalid username or master password.")
        if not user.active:
            raise Unauthorized("User is disabled.")
        if user.role == UserRole.service:
            raise Forbidden("Service users cannot use interactive login.")

        key_derivation = generate_key_derivation(user.salt, master_password)
        try:
            decrypt_user_private_key(key_derivation, user.encrypted_private_key)
        except ValueError as exc:
            raise Unauthorized("Invalid username or master password.") from exc
        return await self._new_session(user, key_derivation)

    async def create_user(
        self,
        actor: UserModel,
        *,
        username: str,
        temporary_password: str | None,
        role: UserRole,
    ) -> UserCreateResponse:
        if not actor.active or actor.role != UserRole.admin:
            raise Forbidden("Administrator access is required.")
        username = username.strip().lower()
        existing = await self.session.scalar(
            select(UserModel).where(UserModel.username == username)
        )
        if existing is not None:
            raise TypesMismatchError("A user with that username already exists.")

        credential = (
            secrets.token_urlsafe(32)
            if role == UserRole.service
            else temporary_password
        )
        if credential is None:
            raise TypesMismatchError("A temporary password is required.")
        salt = os.urandom(16)
        key_derivation = generate_key_derivation(salt, credential)
        public_key, encrypted_private_key = create_user_keypair(key_derivation)
        user = UserModel(
            username=username,
            role=role,
            active=True,
            must_change_password=role != UserRole.service,
            salt=salt,
            hash_key=hash_master_password(credential),
            public_key=public_key,
            encrypted_private_key=encrypted_private_key,
            service_token_hash=(
                _token_hash(credential) if role == UserRole.service else None
            ),
        )
        self.session.add(user)
        await self.session.flush()
        return UserCreateResponse(
            **self._to_user(user).model_dump(),
            service_token=credential if role == UserRole.service else None,
        )

    async def resolve_service_token(self, token: str) -> AuthContext:
        token_hash = _token_hash(token)
        user = await self.session.scalar(
            select(UserModel).where(
                UserModel.service_token_hash == token_hash,
                UserModel.role == UserRole.service,
                UserModel.active.is_(True),
            )
        )
        if user is None:
            raise Unauthorized("Invalid service token.")
        key_derivation = generate_key_derivation(user.salt, token)
        try:
            private_key = decrypt_user_private_key(
                key_derivation, user.encrypted_private_key
            )
        except ValueError as exc:
            raise Unauthorized("Invalid service token.") from exc
        return AuthContext(user=user, private_key=private_key, token_hash=token_hash)

    async def resolve_session(self, token: str, key_derivation: str) -> AuthContext:
        token_hash = _token_hash(token)
        model = await self.session.scalar(
            select(SessionModel).where(SessionModel.token_hash == token_hash)
        )
        if model is None or model.expires_at <= _now():
            if model is not None:
                await self.session.delete(model)
            raise Unauthorized("Invalid or expired session.")
        user = await self.session.get(UserModel, model.user_id)
        if user is None or not user.active:
            raise Unauthorized("Invalid or expired session.")
        try:
            private_key = decrypt_user_private_key(
                key_derivation, user.encrypted_private_key
            )
        except ValueError as exc:
            raise Unauthorized("Invalid user key.") from exc
        return AuthContext(user=user, private_key=private_key, token_hash=token_hash)

    async def logout(self, token_hash: str) -> None:
        await self.session.execute(
            delete(SessionModel).where(SessionModel.token_hash == token_hash)
        )

    async def change_password(
        self,
        context: AuthContext,
        current_password: str,
        new_password: str,
    ) -> AuthSessionResponse:
        user = context.user
        if not verify_master_password(current_password, user.hash_key):
            raise Forbidden("Current master password is incorrect.")
        salt = os.urandom(16)
        key_derivation = generate_key_derivation(salt, new_password)
        user.salt = salt
        user.hash_key = hash_master_password(new_password)
        user.encrypted_private_key = encrypt_user_private_key(
            key_derivation, context.private_key
        )
        user.must_change_password = False
        await self.session.execute(
            delete(SessionModel).where(SessionModel.user_id == user.id)
        )
        await self.session.flush()
        return await self._new_session(user, key_derivation)

    async def list_users(self, actor: UserModel) -> list[AuthUser]:
        if not actor.active or actor.role != UserRole.admin:
            raise Forbidden("Administrator access is required.")
        users = (
            await self.session.execute(select(UserModel).order_by(UserModel.username))
        ).scalars()
        return [self._to_user(user) for user in users]

    async def list_share_targets(self, actor: UserModel) -> list[ShareTarget]:
        users = (
            await self.session.execute(
                select(UserModel)
                .where(UserModel.active.is_(True), UserModel.id != actor.id)
                .order_by(UserModel.username)
            )
        ).scalars()
        return [
            ShareTarget(id=user.id, username=user.username, role=UserRole(user.role))
            for user in users
        ]

    async def update_user(
        self,
        actor: UserModel,
        user_id: int,
        *,
        role: UserRole | None = None,
        active: bool | None = None,
    ) -> AuthUser:
        if not actor.active or actor.role != UserRole.admin:
            raise Forbidden("Administrator access is required.")
        state = await self.session.scalar(
            select(InstanceStateModel)
            .where(InstanceStateModel.id == 1)
            .with_for_update()
        )
        if state is None:
            raise NotFound("Instance state is missing. Run database migrations.")
        user = await self.session.get(UserModel, user_id)
        if user is None:
            raise NotFound("User not found.")
        current_role = UserRole(user.role)
        next_role = role or current_role
        if (current_role == UserRole.service) != (next_role == UserRole.service):
            raise Forbidden("Service user type cannot be changed.")

        removes_active_admin = (
            user.active
            and user.role == UserRole.admin
            and (active is False or (role is not None and role != UserRole.admin))
        )
        if removes_active_admin:
            other_admins = await self.session.scalar(
                select(func.count())
                .select_from(UserModel)
                .where(
                    UserModel.id != user.id,
                    UserModel.active.is_(True),
                    UserModel.role == UserRole.admin,
                )
            )
            if not other_admins:
                raise Forbidden("Cannot remove the last active administrator.")

        if role is not None:
            user.role = role
        if active is not None:
            user.active = active
        if not user.active or user.role == UserRole.service:
            await self.session.execute(
                delete(SessionModel).where(SessionModel.user_id == user.id)
            )
        await self.session.flush()
        return self._to_user(user)
