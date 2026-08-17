import base64
import hashlib
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.exceptions import Forbidden, TypesMismatchError, Unauthorized
from crud.auth import AuthCRUD, _rekey_message, decode_client_key_material
from helpers import (
    create_user_keypair,
    decrypt_user_private_key,
    encrypt,
    encrypt_user_private_key,
    generate_key_derivation,
)
from models import (
    BaseModel,
    InstanceStateModel,
    SessionModel,
    UserModel,
)
from schemas import AuthSessionResponse, UserRole


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
) -> tuple[AuthSessionResponse, dict]:
    material = client_material(password, salt)
    login = await crud.bootstrap(
        username,
        salt=material["salt"],
        public_key=material["public_key"],
        encrypted_private_key=material["encrypted_private_key"],
        auth_public_key=material["auth_public_key"],
        encrypted_auth_private_key=material["encrypted_auth_private_key"],
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
