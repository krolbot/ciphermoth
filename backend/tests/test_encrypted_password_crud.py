import base64
import json
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.exceptions import NotFound, TypesMismatchError
from cli import CliSession, _encrypted_update
from crud import encrypted_password as encrypted_password_crud
from crud.auth import AuthContext
from crud.encrypted_password import EncryptedPasswordCRUD
from helpers import decrypt, encrypt, generate_entry_key, wrap_entry_key
from models import (
    BaseModel,
    PasswordModel,
    UserModel,
)
from schemas import (
    EncryptedPasswordCreatePayload,
    EntryPermission,
    UserRole,
)


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(BaseModel.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


def encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def test_cli_update_appends_history_and_restore_preserves_backup_history() -> None:
    user_private = X25519PrivateKey.generate()
    entry_key = generate_entry_key()
    session = CliSession(
        master_password="unused",
        headers={},
        vault_key=b"unused",
        private_key=user_private.private_bytes_raw(),
        public_key=user_private.public_key().public_bytes_raw(),
    )
    current = {
        "password_name": "entry",
        "kind": "login",
        "password_value": "old",
        "password_history": [{"value": "older", "changed_at": "2025-01-01"}],
    }
    record = {
        "id": 1,
        "encryption_version": 3,
        "wrapped_key": encoded(
            wrap_entry_key(session.public_key, entry_key, context=b"")
        ),
        "encrypted_payload": encrypt(entry_key, json.dumps(current).encode()).decode(),
        "encrypted_preferences": None,
        "favorite": False,
        "owner_id": 1,
        "access": "owner",
    }

    updated = _encrypted_update(session, record, {**current, "password_value": "new"})
    assert isinstance(updated["encrypted_payload"], str)
    updated_payload = json.loads(
        decrypt(entry_key, updated["encrypted_payload"].encode()) or "{}"
    )
    assert [item["value"] for item in updated_payload["password_history"]] == [
        "older",
        "old",
    ]

    restored = _encrypted_update(
        session,
        record,
        {
            **current,
            "password_value": "restored",
            "password_history": [{"value": "backup", "changed_at": "2024-01-01"}],
            "attachments": [],
        },
        restoring=True,
    )
    assert isinstance(restored["encrypted_payload"], str)
    restored_payload = json.loads(
        decrypt(entry_key, restored["encrypted_payload"].encode()) or "{}"
    )
    assert [item["value"] for item in restored_payload["password_history"]] == [
        "backup"
    ]
    assert "encrypted_preferences" in restored
    assert restored["encrypted_attachments"] == []


def test_create_schema_rejects_oversized_attachment_before_crypto() -> None:
    with pytest.raises(ValueError):
        EncryptedPasswordCreatePayload(
            encrypted_payload="payload",
            wrapped_key="wrapped",
            encrypted_attachments=["x" * 12_000_001],
        )


def test_attachment_decoder_enforces_aggregate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = generate_entry_key()
    values = [encrypt(key, b"one").decode(), encrypt(key, b"two").decode()]
    monkeypatch.setattr(encrypted_password_crud, "_MAX_TOTAL_ATTACHMENT_CIPHERTEXT", 1)
    with pytest.raises(TypesMismatchError):
        encrypted_password_crud._decode_attachment_payloads(values)


@pytest.mark.asyncio
async def test_human_create_persists_only_opaque_vault_data(
    session: AsyncSession,
) -> None:
    user = UserModel(
        username="owner",
        role=UserRole.admin,
        active=True,
        must_change_password=False,
        salt=b"0123456789abcdef",
        public_key=b"p" * 32,
        encrypted_private_key=b"encrypted-private-key",
    )
    session.add(user)
    await session.flush()
    context = AuthContext(user=user, private_key=None, token_hash="test-session")
    entry_key = generate_entry_key()
    ciphertext = encrypt(entry_key, b"opaque payload")
    preferences = encrypt(entry_key, b"opaque preferences")
    initial_attachments = [
        encrypt(entry_key, b"attachment-one").decode(),
        encrypt(entry_key, b"attachment-two").decode(),
    ]
    wrapped_key = wrap_entry_key(user.public_key, entry_key)

    created = await EncryptedPasswordCRUD(session).create(
        context,
        encrypted_payload=ciphertext.decode(),
        wrapped_key=encoded(wrapped_key),
        encrypted_preferences=preferences.decode(),
        encrypted_attachments=initial_attachments,
    )

    stored = await session.get(PasswordModel, created.id)
    assert stored is not None
    assert stored.encryption_version == 3
    assert stored.encrypted_payload == ciphertext

    assert created.encrypted_payload == ciphertext.decode()
    assert created.wrapped_key == encoded(wrapped_key)
    assert created.encrypted_preferences == preferences.decode()
    assert created.access == EntryPermission.owner

    crud = EncryptedPasswordCRUD(session)
    assert [
        item.encrypted_payload
        for item in await crud.list_attachments(context, created.id)
    ] == initial_attachments
    replacements = [
        encrypt(entry_key, f"new-{index}".encode()).decode() for index in range(20)
    ]
    updated_payload = encrypt(entry_key, b"updated payload").decode()
    updated_preferences = encrypt(entry_key, b'{"favorite":true}').decode()
    await crud.update(
        context,
        created.id,
        encrypted_payload=updated_payload,
        encrypted_preferences=updated_preferences,
        encrypted_attachments=replacements,
    )
    updated = await crud.get(context, created.id)
    assert updated.encrypted_payload == updated_payload
    assert updated.encrypted_preferences == updated_preferences
    assert [
        item.encrypted_payload
        for item in await crud.list_attachments(context, created.id)
    ] == replacements

    trashed = await EncryptedPasswordCRUD(session).set_deleted(
        context, created.id, deleted=True
    )
    assert trashed.deleted is not None
    with pytest.raises(NotFound):
        await EncryptedPasswordCRUD(session).get(context, created.id)
    restored = await EncryptedPasswordCRUD(session).set_deleted(
        context, created.id, deleted=False
    )
    assert restored.deleted is None
    await EncryptedPasswordCRUD(session).set_deleted(context, created.id, deleted=True)
    await EncryptedPasswordCRUD(session).delete(context, created.id)
    await session.flush()
    assert await session.get(PasswordModel, created.id) is None
