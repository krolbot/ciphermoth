from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.exceptions import Forbidden, NotFound
from crud.auth import AuthCRUD
from crud.password import PasswordCRUD
from models import BaseModel, InstanceStateModel, UserModel
from schemas import Password, SharePermission, UserRole


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


async def _create_context(
    auth: AuthCRUD,
    session: AsyncSession,
    actor: UserModel,
    username: str,
    role: UserRole,
):
    temporary = f"temporary password for {username} 123!"
    await auth.create_user(
        actor,
        username=username,
        temporary_password=temporary,
        role=role,
    )
    login = await auth.login(username, temporary)
    context = await auth.resolve_session(login.token, login.key_derivation)
    changed = await auth.change_password(
        context,
        temporary,
        f"permanent password for {username} 456!",
    )
    return await auth.resolve_session(changed.token, changed.key_derivation)


@pytest.mark.asyncio
async def test_entry_sharing_enforces_read_write_and_no_implicit_admin_access(
    session: AsyncSession,
) -> None:
    auth = AuthCRUD(session)
    owner_login = await auth.bootstrap("owner", "correct horse battery staple")
    owner_context = await auth.resolve_session(
        owner_login.token, owner_login.key_derivation
    )
    member_context = await _create_context(
        auth, session, owner_context.user, "member", UserRole.member
    )
    admin_context = await _create_context(
        auth, session, owner_context.user, "admin2", UserRole.admin
    )
    passwords = PasswordCRUD(session)
    entry = Password(password_name="mail", password_value="secret")

    created = await passwords.create_password(entry, owner_context)

    with pytest.raises(NotFound):
        await passwords.get_password(created.id, member_context)
    with pytest.raises(NotFound):
        await passwords.get_password(created.id, admin_context)

    await passwords.set_share(
        created.id, member_context.user.id, SharePermission.read, owner_context
    )
    shared = await passwords.get_password(created.id, member_context)
    assert shared.password_value == "secret"
    assert shared.access == "read"

    changed = entry.model_copy(update={"password_value": "changed"})
    with pytest.raises(Forbidden, match="Write"):
        await passwords.update_password(created.id, changed, member_context)

    await passwords.set_share(
        created.id, member_context.user.id, SharePermission.write, owner_context
    )
    await passwords.update_password(created.id, changed, member_context)
    assert (await passwords.get_password(created.id, owner_context)).password_value == (
        "changed"
    )

    await passwords.revoke_share(created.id, member_context.user.id, owner_context)
    with pytest.raises(NotFound):
        await passwords.get_password(created.id, member_context)
