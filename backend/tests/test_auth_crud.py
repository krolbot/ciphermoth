import base64
import hashlib
import hmac
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.exceptions import Forbidden, TypesMismatchError, Unauthorized
from crud.auth import AuthCRUD, _rekey_message, decode_client_key_material
from crud.master_password import fetch_master_password
from helpers import (
    create_user_keypair,
    decrypt_user_private_key,
    encrypt,
    encrypt_user_private_key,
    generate_key_derivation,
    hash_master_password,
)
from models import (
    BaseModel,
    InstanceStateModel,
    MasterPasswordModel,
    PasswordAccessModel,
    PasswordModel,
    SessionModel,
    UserModel,
)
from schemas import AuthSessionResponse, UserRole
from settings import get_api_settings


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(BaseModel.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(InstanceStateModel(id=1))
        await db.flush()
        yield db
    await engine.dispose()


def client_material(password: str, salt: bytes = b"0123456789abcdef") -> dict:
    key = generate_key_derivation(salt, password)
    public_key, encrypted_private_key = create_user_keypair(key)
    auth_private = Ed25519PrivateKey.generate()
    auth_public_key = auth_private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    encrypted_auth_private_key = encrypt(
        key,
        auth_private.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    return {
        "salt": salt,
        "public_key": public_key,
        "encrypted_private_key": encrypted_private_key,
        "auth_public_key": auth_public_key,
        "encrypted_auth_private_key": encrypted_auth_private_key,
        "auth_private": auth_private,
        "key": key,
    }


async def bootstrap(
    crud: AuthCRUD,
    username: str = "owner",
    password: str = "correct horse battery staple",
    *,
    salt: bytes = b"0123456789abcdef",
    legacy_migration_token: str | None = None,
) -> tuple[AuthSessionResponse, dict]:
    material = client_material(password, salt)
    login = await crud.bootstrap(
        username,
        salt=material["salt"],
        public_key=material["public_key"],
        encrypted_private_key=material["encrypted_private_key"],
        auth_public_key=material["auth_public_key"],
        encrypted_auth_private_key=material["encrypted_auth_private_key"],
        legacy_migration_token=legacy_migration_token,
    )
    return login, material


@pytest.mark.asyncio
async def test_bootstrap_accepts_client_key_material_without_returning_derived_key(
    session: AsyncSession,
) -> None:
    login, material = await bootstrap(AuthCRUD(session))

    payload = login.model_dump()
    assert "key_derivation" not in payload
    assert base64.urlsafe_b64decode(login.salt + "==") == material["salt"]
    assert base64.urlsafe_b64decode(login.public_key + "==") == material["public_key"]
    assert login.encrypted_private_key.encode() == material["encrypted_private_key"]


@pytest.mark.asyncio
async def test_human_login_uses_one_time_signature_challenge(
    session: AsyncSession,
) -> None:
    auth_private = Ed25519PrivateKey.generate()
    auth_public = auth_private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    encrypted_auth_private = encrypt(
        generate_key_derivation(b"0123456789abcdef", "local-only password"),
        auth_private.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    material = client_material("local-only password")
    crud = AuthCRUD(session)
    await crud.bootstrap(
        "owner",
        salt=material["salt"],
        public_key=material["public_key"],
        encrypted_private_key=material["encrypted_private_key"],
        auth_public_key=auth_public,
        encrypted_auth_private_key=encrypted_auth_private,
    )

    challenge = await crud.create_challenge("owner")
    signature = auth_private.sign(base64.urlsafe_b64decode(challenge.nonce + "=="))
    login = await crud.login(challenge.challenge, signature)

    assert login.user.username == "owner"
    with pytest.raises(Unauthorized):
        await crud.login(challenge.challenge, signature)


def test_client_key_material_rejects_invalid_lengths_and_tokens() -> None:
    with pytest.raises(TypesMismatchError, match="key material"):
        decode_client_key_material("AA", "AA", "AA")


@pytest.mark.asyncio
async def test_only_first_user_can_bootstrap_and_becomes_admin(
    session: AsyncSession,
) -> None:
    crud = AuthCRUD(session)
    login, _ = await bootstrap(crud)

    assert login.user.role == UserRole.admin
    assert login.user.must_change_password is False
    assert login.token
    assert await session.scalar(select(func.count()).select_from(SessionModel)) == 1

    material = client_material("another sufficiently strong password")
    with pytest.raises(Forbidden, match="initialized"):
        await crud.bootstrap(
            "other",
            **material_for_call(material),
        )


def material_for_call(material: dict) -> dict:
    return {
        "salt": material["salt"],
        "public_key": material["public_key"],
        "encrypted_private_key": material["encrypted_private_key"],
        "auth_public_key": material["auth_public_key"],
        "encrypted_auth_private_key": material["encrypted_auth_private_key"],
    }


@pytest.mark.asyncio
async def test_legacy_bootstrap_requires_operator_token_and_existing_vault_salt(
    session: AsyncSession,
) -> None:
    crud = AuthCRUD(session)
    legacy_password = "legacy1!"
    salt = b"fedcba9876543210"
    token = "legacy-migration-token-with-at-least-32-chars"
    settings = get_api_settings()
    previous = settings.ciphermoth_legacy_migration_token
    settings.ciphermoth_legacy_migration_token = token
    session.add(
        MasterPasswordModel(salt=salt, hash_key=hash_master_password(legacy_password))
    )
    await session.flush()

    try:
        material = client_material(legacy_password, salt)
        with pytest.raises(Unauthorized, match="migration token"):
            await crud.bootstrap(
                "owner",
                **material_for_call(material),
                legacy_migration_token="wrong-token",
            )
        with pytest.raises(TypesMismatchError, match="legacy vault"):
            await crud.bootstrap(
                "owner",
                **material_for_call(client_material(legacy_password)),
                legacy_migration_token=token,
            )
        login, _ = await bootstrap(
            crud,
            password=legacy_password,
            salt=salt,
            legacy_migration_token=token,
        )
        assert login.user.role == UserRole.admin
    finally:
        settings.ciphermoth_legacy_migration_token = previous


@pytest.mark.asyncio
async def test_admin_created_human_uses_client_keys_and_service_cannot_login(
    session: AsyncSession,
) -> None:
    crud = AuthCRUD(session)
    owner_login, _ = await bootstrap(crud)
    owner = await session.get(UserModel, owner_login.user.id)
    assert owner is not None

    member_password = "temporary member password 123!"
    member_keys = client_material(member_password, b"abcdef0123456789")
    member = await crud.create_user(
        owner,
        username="member",
        role=UserRole.member,
        **material_for_call(member_keys),
    )
    service = await crud.create_user(
        owner,
        username="future-ai",
        role=UserRole.service,
    )

    assert member.must_change_password is True
    assert service.service_token is not None
    challenge = await crud.create_challenge("member")
    signature = member_keys["auth_private"].sign(
        base64.urlsafe_b64decode(challenge.nonce + "==")
    )
    assert (await crud.login(challenge.challenge, signature)).user.must_change_password
    with pytest.raises(Unauthorized, match="interactive"):
        await crud.create_challenge("future-ai")

    service_model = await session.scalar(
        select(UserModel).where(UserModel.username == "future-ai")
    )
    assert service_model is not None
    assert (
        service_model.service_token_hash
        == hashlib.sha256(service.service_token.encode()).hexdigest()
    )
    assert (
        await crud.resolve_service_token(service.service_token)
    ).user.id == service_model.id
    with pytest.raises(Unauthorized):
        await crud.resolve_service_token("wrong-token")
    with pytest.raises(Forbidden, match="Service user type"):
        await crud.update_user(owner, service_model.id, role=UserRole.member)


@pytest.mark.asyncio
async def test_bootstrap_claims_legacy_entries_without_server_decryption(
    session: AsyncSession,
) -> None:
    password = "correct horse battery staple"
    salt = b"0123456789abcdef"
    legacy_key = generate_key_derivation(salt, password)
    session.add(MasterPasswordModel(salt=salt, hash_key=hash_master_password(password)))
    legacy_entry = PasswordModel(
        password_name="legacy", password_value=encrypt(legacy_key, b"secret")
    )
    session.add(legacy_entry)
    await session.flush()

    migration_token = "legacy-claim-token-with-at-least-32-characters"
    settings = get_api_settings()
    previous = settings.ciphermoth_legacy_migration_token
    settings.ciphermoth_legacy_migration_token = migration_token
    try:
        login, _ = await bootstrap(
            AuthCRUD(session),
            password=password,
            salt=salt,
            legacy_migration_token=migration_token,
        )
    finally:
        settings.ciphermoth_legacy_migration_token = previous
    entry = await session.get(PasswordModel, legacy_entry.id)
    access = await session.get(PasswordAccessModel, (legacy_entry.id, login.user.id))

    assert entry is not None and access is not None
    assert entry.owner_id == login.user.id
    assert entry.encryption_version == 1
    assert entry.password_value == legacy_entry.password_value
    assert access.wrapped_key == b"\x00"
    assert await fetch_master_password(session) is None


@pytest.mark.asyncio
async def test_pre_c3_user_enrolls_auth_by_proving_x25519_key_possession(
    session: AsyncSession,
) -> None:
    crud = AuthCRUD(session)
    material = client_material("existing user password")
    user = UserModel(
        username="existing",
        role=UserRole.member,
        active=True,
        must_change_password=False,
        salt=material["salt"],
        hash_key=b"legacy-password-verifier",
        public_key=material["public_key"],
        encrypted_private_key=material["encrypted_private_key"],
        auth_public_key=None,
        encrypted_auth_private_key=None,
    )
    session.add(user)
    await session.flush()

    challenge = await crud.create_challenge("existing")
    assert challenge.legacy_user
    private_key = X25519PrivateKey.from_private_bytes(
        decrypt_user_private_key(material["key"], material["encrypted_private_key"])
    )
    shared = private_key.exchange(
        X25519PublicKey.from_public_bytes(
            base64.urlsafe_b64decode(challenge.nonce + "==")
        )
    )
    auth_private = Ed25519PrivateKey.generate()
    auth_private_bytes = auth_private.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    login = await crud.login(
        challenge.challenge,
        hmac.digest(shared, challenge.challenge.encode(), "sha256"),
        auth_public_key=auth_private.public_key().public_bytes_raw(),
        encrypted_auth_private_key=encrypt(material["key"], auth_private_bytes),
    )

    await session.refresh(user)
    assert login.user.id == user.id
    assert user.hash_key is None
    assert user.auth_public_key == auth_private.public_key().public_bytes_raw()


@pytest.mark.asyncio
async def test_password_change_revokes_session_without_server_key_derivation(
    session: AsyncSession,
) -> None:
    crud = AuthCRUD(session)
    old_password = "correct horse battery staple"
    new_password = "new correct horse battery staple"
    login, old_material = await bootstrap(crud, password=old_password)
    context = await crud.resolve_session(login.token)
    assert context.private_key is None

    private_key = decrypt_user_private_key(
        old_material["key"], old_material["encrypted_private_key"]
    )
    new_salt = b"fedcba9876543210"
    new_key = generate_key_derivation(new_salt, new_password)
    encrypted_private_key = encrypt_user_private_key(new_key, private_key)
    encrypted_auth_private_key = encrypt(
        new_key,
        old_material["auth_private"].private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    with pytest.raises(Unauthorized, match="rekey proof"):
        await crud.change_password(
            context,
            new_salt=new_salt,
            encrypted_private_key=encrypted_private_key,
            encrypted_auth_private_key=encrypted_auth_private_key,
            proof=b"0" * 64,
        )
    proof = old_material["auth_private"].sign(
        _rekey_message(
            context.token_hash,
            new_salt,
            encrypted_private_key,
            encrypted_auth_private_key,
        )
    )
    changed = await crud.change_password(
        context,
        new_salt=new_salt,
        encrypted_private_key=encrypted_private_key,
        encrypted_auth_private_key=encrypted_auth_private_key,
        proof=proof,
    )

    with pytest.raises(Unauthorized, match="session"):
        await crud.resolve_session(login.token)
    assert (await crud.resolve_session(changed.token)).private_key is None


@pytest.mark.asyncio
async def test_last_active_admin_cannot_be_disabled(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    crud = AuthCRUD(session)
    login, _ = await bootstrap(crud)
    owner = await session.get(UserModel, login.user.id)
    assert owner is not None

    original_scalar = session.scalar
    locked = False

    async def record_lock(statement, *args, **kwargs):
        nonlocal locked
        locked = locked or statement._for_update_arg is not None
        return await original_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(session, "scalar", record_lock)
    with pytest.raises(Forbidden, match="last active administrator"):
        await crud.update_user(owner, owner.id, active=False)
    assert locked
