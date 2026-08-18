import base64
import binascii
import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import delete, func, select

from api.exceptions import Forbidden, NotFound, TypesMismatchError, Unauthorized
from crud.base import BaseCRUD
from helpers import (
    create_user_keypair,
    decrypt_user_private_key,
    generate_key_derivation,
)
from models import (
    AuthChallengeModel,
    InstanceStateModel,
    SessionModel,
    UserModel,
)
from schemas import (
    AuthChallengeResponse,
    AuthSessionResponse,
    AuthStatus,
    AuthUser,
    ShareTarget,
    UserCreateResponse,
    UserRole,
)

_SESSION_LIFETIME = timedelta(hours=12)
_CHALLENGE_LIFETIME = timedelta(minutes=5)
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


def decode_client_key_material(
    salt: str, public_key: str, encrypted_private_key: str
) -> tuple[bytes, bytes, bytes]:
    try:

        def decode(value: str) -> bytes:
            return base64.b64decode(
                value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
            )

        salt_bytes = decode(salt)
        public_key_bytes = decode(public_key)
        encrypted_token = decode(encrypted_private_key)
    except (ValueError, binascii.Error) as exc:
        raise TypesMismatchError("Invalid client key material.") from exc
    if (
        len(salt_bytes) != 16
        or len(public_key_bytes) != 32
        or len(encrypted_token) < 73
        or encrypted_token[0] != 0x80
    ):
        raise TypesMismatchError("Invalid client key material.")
    return salt_bytes, public_key_bytes, encrypted_private_key.encode()


def decode_auth_key_material(
    public_key: str, encrypted_private_key: str
) -> tuple[bytes, bytes]:
    try:
        public = base64.b64decode(
            public_key + "=" * (-len(public_key) % 4), altchars=b"-_", validate=True
        )
        encrypted = base64.b64decode(
            encrypted_private_key + "=" * (-len(encrypted_private_key) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, binascii.Error) as exc:
        raise TypesMismatchError("Invalid authentication key material.") from exc
    if len(public) != 32 or len(encrypted) < 73 or encrypted[0] != 0x80:
        raise TypesMismatchError("Invalid authentication key material.")
    return public, encrypted_private_key.encode()


def decode_signature(value: str) -> bytes:
    try:
        signature = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, binascii.Error) as exc:
        raise TypesMismatchError("Invalid authentication proof.") from exc
    if len(signature) not in (32, 64):
        raise TypesMismatchError("Invalid authentication proof.")
    return signature


def _rekey_message(
    token_hash: str,
    new_salt: bytes,
    encrypted_private_key: bytes,
    encrypted_auth_private_key: bytes,
) -> bytes:
    encoded_salt = base64.urlsafe_b64encode(new_salt).rstrip(b"=")
    return b"\n".join(
        (
            b"ciphermoth-rekey-v1",
            token_hash.encode(),
            encoded_salt,
            encrypted_private_key,
            encrypted_auth_private_key,
        )
    )


@dataclass(frozen=True)
class AuthContext:
    user: UserModel
    private_key: bytes | None
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
        return AuthStatus(initialized=bool(user_count))

    async def _new_session(self, user: UserModel) -> AuthSessionResponse:
        if user.encrypted_auth_private_key is None:
            raise Forbidden("Interactive authentication is not enrolled.")
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
            salt=base64.urlsafe_b64encode(user.salt).decode().rstrip("="),
            public_key=base64.urlsafe_b64encode(user.public_key).decode().rstrip("="),
            encrypted_private_key=user.encrypted_private_key.decode(),
            encrypted_auth_private_key=user.encrypted_auth_private_key.decode(),
        )

    async def bootstrap(
        self,
        username: str,
        *,
        salt: bytes,
        public_key: bytes,
        encrypted_private_key: bytes,
        auth_public_key: bytes,
        encrypted_auth_private_key: bytes,
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

        user = UserModel(
            username=username,
            role=UserRole.admin,
            active=True,
            must_change_password=False,
            salt=salt,
            public_key=public_key,
            encrypted_private_key=encrypted_private_key,
            auth_public_key=auth_public_key,
            encrypted_auth_private_key=encrypted_auth_private_key,
        )
        self.session.add(user)
        await self.session.flush()

        state.bootstrapped_at = _now()
        await self.session.flush()
        return await self._new_session(user)

    async def create_challenge(self, username: str) -> AuthChallengeResponse:
        now = _now()
        await self.session.execute(
            delete(AuthChallengeModel).where(AuthChallengeModel.expires_at <= now)
        )
        user = await self.session.scalar(
            select(UserModel).where(UserModel.username == username.strip().lower())
        )
        if user is None or not user.active or user.role == UserRole.service:
            raise Unauthorized("Invalid interactive account.")
        if user.auth_public_key is None or user.encrypted_auth_private_key is None:
            raise Unauthorized("Invalid interactive account.")
        nonce = os.urandom(32)

        challenge = secrets.token_urlsafe(32)
        await self.session.execute(
            delete(AuthChallengeModel).where(AuthChallengeModel.user_id == user.id)
        )
        self.session.add(
            AuthChallengeModel(
                token_hash=_token_hash(challenge),
                user_id=user.id,
                nonce=nonce,
                expires_at=now + _CHALLENGE_LIFETIME,
            )
        )
        await self.session.flush()
        return AuthChallengeResponse(
            challenge=challenge,
            nonce=base64.urlsafe_b64encode(nonce).decode().rstrip("="),
            salt=base64.urlsafe_b64encode(user.salt).decode().rstrip("="),
            public_key=base64.urlsafe_b64encode(user.public_key).decode().rstrip("="),
            encrypted_private_key=user.encrypted_private_key.decode(),
            encrypted_auth_private_key=user.encrypted_auth_private_key.decode(),
        )

    async def login(
        self,
        challenge: str,
        signature: bytes,
    ) -> AuthSessionResponse:
        consumed = (
            await self.session.execute(
                delete(AuthChallengeModel)
                .where(
                    AuthChallengeModel.token_hash == _token_hash(challenge),
                    AuthChallengeModel.expires_at > _now(),
                )
                .returning(AuthChallengeModel.user_id, AuthChallengeModel.nonce)
            )
        ).one_or_none()
        if consumed is None:
            raise Unauthorized("Invalid or expired challenge.")
        user_id, nonce = consumed
        user = await self.session.get(UserModel, user_id)
        if user is None or not user.active:
            raise Unauthorized("Invalid or expired challenge.")

        if user.auth_public_key is None or user.encrypted_auth_private_key is None:
            raise Unauthorized("Invalid interactive account.")
        try:
            Ed25519PublicKey.from_public_bytes(user.auth_public_key).verify(
                signature, nonce
            )
        except (InvalidSignature, ValueError) as exc:
            raise Unauthorized("Invalid challenge signature.") from exc
        await self.session.flush()
        return await self._new_session(user)

    async def create_user(
        self,
        actor: UserModel,
        *,
        username: str,
        role: UserRole,
        salt: bytes | None = None,
        public_key: bytes | None = None,
        encrypted_private_key: bytes | None = None,
        auth_public_key: bytes | None = None,
        encrypted_auth_private_key: bytes | None = None,
    ) -> UserCreateResponse:
        if not actor.active or actor.role != UserRole.admin:
            raise Forbidden("Administrator access is required.")
        username = username.strip().lower()
        existing = await self.session.scalar(
            select(UserModel).where(UserModel.username == username)
        )
        if existing is not None:
            raise TypesMismatchError("A user with that username already exists.")

        credential = secrets.token_urlsafe(32) if role == UserRole.service else None
        if role == UserRole.service:
            if credential is None:
                raise TypesMismatchError("Unable to create service credential.")
            salt = os.urandom(16)
            key_derivation = generate_key_derivation(salt, credential)
            public_key, encrypted_private_key = create_user_keypair(key_derivation)
        elif any(
            value is None
            for value in (
                salt,
                public_key,
                encrypted_private_key,
                auth_public_key,
                encrypted_auth_private_key,
            )
        ):
            raise TypesMismatchError(
                "Client key material is required for a human user."
            )
        if salt is None or public_key is None or encrypted_private_key is None:
            raise TypesMismatchError(
                "Human users require client-generated key material."
            )
        user = UserModel(
            username=username,
            role=role,
            active=True,
            must_change_password=role != UserRole.service,
            salt=salt,
            public_key=public_key,
            encrypted_private_key=encrypted_private_key,
            auth_public_key=auth_public_key,
            encrypted_auth_private_key=encrypted_auth_private_key,
            service_token_hash=(
                _token_hash(credential) if credential is not None else None
            ),
            service_owner_id=actor.id if role == UserRole.service else None,
        )
        self.session.add(user)
        await self.session.flush()
        return UserCreateResponse(
            **self._to_user(user).model_dump(),
            service_token=credential,
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

    async def resolve_session(self, token: str) -> AuthContext:
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
        return AuthContext(user=user, private_key=None, token_hash=token_hash)

    async def logout(self, token_hash: str) -> None:
        await self.session.execute(
            delete(SessionModel).where(SessionModel.token_hash == token_hash)
        )

    async def change_password(
        self,
        context: AuthContext,
        *,
        new_salt: bytes,
        encrypted_private_key: bytes,
        encrypted_auth_private_key: bytes,
        proof: bytes,
    ) -> AuthSessionResponse:
        user = context.user
        if user.role == UserRole.service or user.auth_public_key is None:
            raise Forbidden("Interactive authentication is required.")
        try:
            Ed25519PublicKey.from_public_bytes(user.auth_public_key).verify(
                proof,
                _rekey_message(
                    context.token_hash,
                    new_salt,
                    encrypted_private_key,
                    encrypted_auth_private_key,
                ),
            )
        except (InvalidSignature, ValueError) as exc:
            raise Unauthorized("Invalid rekey proof.") from exc
        user.salt = new_salt

        user.encrypted_private_key = encrypted_private_key
        user.encrypted_auth_private_key = encrypted_auth_private_key
        user.must_change_password = False
        await self.session.execute(
            delete(SessionModel).where(SessionModel.user_id == user.id)
        )
        await self.session.flush()
        return await self._new_session(user)

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
            ShareTarget(
                id=user.id,
                username=user.username,
                role=UserRole(user.role),
                public_key=base64.urlsafe_b64encode(user.public_key)
                .decode()
                .rstrip("="),
            )
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
