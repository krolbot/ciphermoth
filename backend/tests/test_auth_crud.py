import hashlib
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.exceptions import Forbidden, TypesMismatchError, Unauthorized
from crud.auth import AuthCRUD
from crud.master_password import fetch_master_password
from helpers import (
    decrypt,
    decrypt_user_private_key,
    encrypt,
    generate_key_derivation,
    hash_master_password,
    unwrap_entry_key,
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
from schemas import UserRole


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


@pytest.mark.asyncio
async def test_only_first_user_can_bootstrap_and_becomes_admin(
    session: AsyncSession,
) -> None:
    crud = AuthCRUD(session)

    login = await crud.bootstrap("owner", "correct horse battery staple")

    assert login.user.role == UserRole.admin
    assert login.user.must_change_password is False
    assert login.token
    assert login.key_derivation
    assert await session.scalar(select(func.count()).select_from(SessionModel)) == 1

    with pytest.raises(Forbidden, match="initialized"):
        await crud.bootstrap("other", "another sufficiently strong password")


@pytest.mark.asyncio
async def test_fresh_bootstrap_rejects_weak_password_but_legacy_accepts_it(
    session: AsyncSession,
) -> None:
    crud = AuthCRUD(session)
    with pytest.raises(TypesMismatchError, match="at least 12"):
        await crud.bootstrap("owner", "weak1!")

    weak_legacy = "legacy1!"
    session.add(
        MasterPasswordModel(
            salt=b"0123456789abcdef",
            hash_key=hash_master_password(weak_legacy),
        )
    )
    await session.flush()
    assert (await crud.bootstrap("owner", weak_legacy)).user.role == UserRole.admin


@pytest.mark.asyncio
async def test_admin_created_human_must_change_password_and_service_cannot_login(
    session: AsyncSession,
) -> None:
    crud = AuthCRUD(session)
    owner_login = await crud.bootstrap("owner", "correct horse battery staple")
    owner = await session.get(UserModel, owner_login.user.id)
    assert owner is not None

    member = await crud.create_user(
        owner,
        username="member",
        temporary_password="temporary member password 123!",
        role=UserRole.member,
    )
    service = await crud.create_user(
        owner,
        username="future-ai",
        temporary_password=None,
        role=UserRole.service,
    )

    assert member.must_change_password is True
    assert service.role == UserRole.service
    assert service.service_token is not None
    member_login = await crud.login("member", "temporary member password 123!")
    assert member_login.user.must_change_password is True

    with pytest.raises(Forbidden, match="interactive"):
        await crud.login("future-ai", service.service_token)
    service_model = await session.scalar(
        select(UserModel).where(UserModel.username == "future-ai")
    )
    assert service_model is not None
    assert (
        service_model.service_token_hash
        == hashlib.sha256(service.service_token.encode()).hexdigest()
    )
    service_context = await crud.resolve_service_token(service.service_token)
    assert service_context.user.id == service_model.id
    with pytest.raises(Unauthorized):
        await crud.resolve_service_token("wrong-token")
    with pytest.raises(Forbidden, match="Service user type"):
        await crud.update_user(owner, service_model.id, role=UserRole.member)


@pytest.mark.asyncio
async def test_bootstrap_reencrypts_legacy_entries_with_per_entry_key(
    session: AsyncSession,
) -> None:
    master_password = "correct horse battery staple"
    salt = b"0123456789abcdef"
    legacy_key = generate_key_derivation(salt, master_password)
    session.add(
        MasterPasswordModel(
            salt=salt,
            hash_key=hash_master_password(master_password),
        )
    )
    legacy_entry = PasswordModel(
        password_name="legacy",
        password_value=encrypt(legacy_key, b"secret"),
    )
    session.add(legacy_entry)
    await session.flush()

    login = await AuthCRUD(session).bootstrap("owner", master_password)

    owner = await session.get(UserModel, login.user.id)
    entry = await session.get(PasswordModel, legacy_entry.id)
    assert owner is not None
    access = await session.get(PasswordAccessModel, (legacy_entry.id, owner.id))
    assert entry is not None
    assert access is not None
    private_key = decrypt_user_private_key(
        login.key_derivation, owner.encrypted_private_key
    )
    entry_key = unwrap_entry_key(
        private_key, access.wrapped_key, str(legacy_entry.id).encode()
    )

    assert entry.owner_id == owner.id
    assert entry.encryption_version == 2
    assert access.permission == "owner"
    assert decrypt(entry_key, entry.password_value) == "secret"
    assert decrypt(legacy_key, entry.password_value) is None
    assert await fetch_master_password(session) is None


@pytest.mark.asyncio
async def test_password_change_revokes_old_session_and_rewraps_private_key(
    session: AsyncSession,
) -> None:
    crud = AuthCRUD(session)
    login = await crud.bootstrap("owner", "correct horse battery staple")
    context = await crud.resolve_session(login.token, login.key_derivation)

    changed = await crud.change_password(
        context,
        "correct horse battery staple",
        "new correct horse battery staple",
    )

    with pytest.raises(Unauthorized, match="session"):
        await crud.resolve_session(login.token, login.key_derivation)
    resolved = await crud.resolve_session(changed.token, changed.key_derivation)
    assert resolved.user.id == login.user.id


@pytest.mark.asyncio
async def test_last_active_admin_cannot_be_disabled(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    crud = AuthCRUD(session)
    login = await crud.bootstrap("owner", "correct horse battery staple")
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
