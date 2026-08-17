import base64
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.exceptions import Forbidden, NotFound
from crud.auth import AuthContext
from crud.encrypted_password import EncryptedPasswordCRUD
from helpers import encrypt, generate_entry_key, wrap_entry_key
from models import BaseModel, InstanceStateModel, UserModel
from schemas import SharePermission


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


def encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


async def user_context(session: AsyncSession, username: str, role: str) -> AuthContext:
    user = UserModel(
        username=username,
        role=role,
        salt=b"0" * 16,
        public_key=b"1" * 32,
        encrypted_private_key=b"unused",
    )
    session.add(user)
    await session.flush()
    return AuthContext(user=user, private_key=None, token_hash="test-session")


@pytest.mark.asyncio
async def test_opaque_entry_sharing_enforces_acl_without_human_server_keys(
    session: AsyncSession,
) -> None:
    owner = await user_context(session, "owner", "admin")
    member = await user_context(session, "member", "member")
    admin = await user_context(session, "admin2", "admin")
    passwords = EncryptedPasswordCRUD(session)
    entry_key = generate_entry_key()
    owner_ciphertext = encrypt(entry_key, b"owner ciphertext")
    changed_ciphertext = encrypt(entry_key, b"changed ciphertext")
    preferences = encrypt(entry_key, b"owner preferences")

    created = await passwords.create(
        owner,
        encrypted_payload=owner_ciphertext.decode(),
        wrapped_key=encoded(wrap_entry_key(owner.user.public_key, entry_key)),
        encrypted_preferences=preferences.decode(),
    )

    with pytest.raises(NotFound):
        await passwords.get(member, created.id)
    with pytest.raises(NotFound):
        await passwords.get(admin, created.id)

    await passwords.share(
        owner,
        created.id,
        member.user.id,
        permission=SharePermission.read,
        wrapped_key=encoded(wrap_entry_key(member.user.public_key, entry_key)),
    )
    shared = await passwords.get(member, created.id)
    assert shared.encrypted_payload == owner_ciphertext.decode()
    assert shared.access == "read"
    assert member.private_key is None

    with pytest.raises(Forbidden, match="Write"):
        await passwords.update(
            member, created.id, encrypted_payload=changed_ciphertext.decode()
        )

    await passwords.share(
        owner,
        created.id,
        member.user.id,
        permission=SharePermission.write,
        wrapped_key=encoded(wrap_entry_key(member.user.public_key, entry_key)),
    )
    changed = await passwords.update(
        member, created.id, encrypted_payload=changed_ciphertext.decode()
    )
    assert changed.encrypted_payload == changed_ciphertext.decode()

    await passwords.revoke_share(owner, created.id, member.user.id)
    with pytest.raises(NotFound):
        await passwords.get(member, created.id)
