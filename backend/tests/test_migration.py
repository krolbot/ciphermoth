import asyncio
import json
import os
from collections.abc import AsyncIterator
from urllib.parse import quote

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.endpoints.deps import get_session
from helpers import (
    encrypt,
    generate_key_derivation,
    hash_master_password,
    verify_key_check,
    verify_master_password,
)
from main import app
from tests.support import (
    MASTER_PASSWORD,
    NEW_MASTER_PASSWORD,
    admin_connection,
    auth,
    reset_schema,
    run_alembic,
    unlock,
)

PRE_PATCH_REVISION = "9c0d1e2f3a4b"
MIGRATION_DB = os.environ["POSTGRES_DB"].removesuffix("_test") + "_migration_test"
CIPHERTEXT_COLUMNS = (
    "SELECT id, password_name, password_value, url, totp_secret, tags, "
    "custom_fields, folder, password_history, deleted FROM passwords ORDER BY id"
)


async def _alembic(*args: str) -> str:
    return await asyncio.to_thread(run_alembic, *args, database=MIGRATION_DB)


async def _seed_v145_vault(conn) -> tuple[str, bytes]:
    salt = os.urandom(16)
    key = generate_key_derivation(salt, MASTER_PASSWORD)
    await conn.execute(
        "INSERT INTO master_password (salt, hash_key) VALUES ($1, $2)",
        salt,
        hash_master_password(MASTER_PASSWORD),
    )
    history = json.dumps([{"value": "older", "changed_at": "2026-01-01T00:00:00"}])
    await conn.execute(
        "INSERT INTO passwords (password_name, password_value, username, url, "
        "totp_secret, tags, folder, password_history, favorite) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, true)",
        "legacy login",
        encrypt(key, b"legacy-Value-1"),
        "moth@example.com",
        encrypt(key, b"https://legacy.test"),
        encrypt(key, b"JBSWY3DPEHPK3PXP"),
        encrypt(key, json.dumps(["old"]).encode()),
        encrypt(key, b"Archive"),
        encrypt(key, history.encode()),
    )
    await conn.execute(
        "INSERT INTO passwords (password_name, password_value, kind, deleted) "
        "VALUES ($1, $2, 'note', now())",
        "trashed note",
        encrypt(key, b"note body\n"),
    )
    blob = os.urandom(2048) + b"\xff\x00"
    await conn.execute(
        "INSERT INTO password_attachments (password_id, filename, content, "
        "content_type, size_bytes) VALUES (1, $1, $2, $3, $4)",
        encrypt(key, b"scan.bin"),
        encrypt(key, blob),
        encrypt(key, b"application/octet-stream"),
        len(blob),
    )
    return key.decode(), blob


@pytest.fixture
async def legacy_db() -> AsyncIterator[str]:
    conn = await admin_connection()
    try:
        if not await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", MIGRATION_DB
        ):
            await conn.execute(f'CREATE DATABASE "{MIGRATION_DB}"')
    finally:
        await conn.close()
    await asyncio.to_thread(reset_schema, MIGRATION_DB)
    await _alembic("upgrade", PRE_PATCH_REVISION)
    yield MIGRATION_DB


@pytest.fixture
async def legacy_client(legacy_db: str) -> AsyncIterator[httpx.AsyncClient]:
    url = (
        f"postgresql+asyncpg://{os.environ['POSTGRES_USER']}:"
        f"{quote(os.environ['POSTGRES_PASSWORD'])}@{os.environ['POSTGRES_HOST']}:"
        f"{os.environ['POSTGRES_PORT']}/{legacy_db}"
    )
    legacy_engine = create_async_engine(url)
    sessions = async_sessionmaker(
        legacy_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def legacy_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = legacy_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver/api",
            timeout=60,
        ) as http:
            yield http
    finally:
        app.dependency_overrides.pop(get_session, None)
        await legacy_engine.dispose()


async def test_upgrade_from_v145_keeps_ciphertext_and_unlocks(
    legacy_client: httpx.AsyncClient,
) -> None:
    conn = await admin_connection(MIGRATION_DB)
    try:
        key, blob = await _seed_v145_vault(conn)
        before = [tuple(r) for r in await conn.fetch(CIPHERTEXT_COLUMNS)]
        attachments_before = await conn.fetch("SELECT * FROM password_attachments")
    finally:
        await conn.close()

    output = await _alembic("upgrade", "head")
    assert "0d1e2f3a4b5c" in output

    conn = await admin_connection(MIGRATION_DB)
    try:
        assert [tuple(r) for r in await conn.fetch(CIPHERTEXT_COLUMNS)] == before
        assert await conn.fetch("SELECT * FROM password_attachments") == (
            attachments_before
        )
        assert await conn.fetchval("SELECT key_check FROM master_password") is None
    finally:
        await conn.close()

    resp = await legacy_client.get("/passwords", headers=auth(key))
    assert resp.status_code == 403
    assert resp.json()["code"] == "invalid_key"

    assert await unlock(legacy_client) == key

    resp = await legacy_client.get("/passwords", headers=auth(key))
    assert resp.status_code == 200, resp.text
    [login] = resp.json()
    assert login["password_name"] == "legacy login"
    assert login["password_value"] == "legacy-Value-1"
    assert login["url"] == "https://legacy.test"
    assert login["tags"] == ["old"]
    assert login["folder"] == "Archive"
    assert login["password_history"][0]["value"] == "older"
    assert login["attachment_count"] == 1
    trash = await legacy_client.get("/passwords/trash", headers=auth(key))
    assert trash.json()[0]["password_value"] == "note body\n"
    download = await legacy_client.get(
        "/passwords/legacy login/attachments/1", headers=auth(key)
    )
    assert download.content == blob

    resp = await legacy_client.patch(
        "/master_password/update",
        json={
            "master_password": MASTER_PASSWORD,
            "new_master_password": NEW_MASTER_PASSWORD,
        },
        headers=auth(key),
    )
    assert resp.status_code == 200, resp.text
    new_key = await unlock(legacy_client, NEW_MASTER_PASSWORD)
    download = await legacy_client.get(
        "/passwords/legacy login/attachments/1", headers=auth(new_key)
    )
    assert download.content == blob


async def test_downgrade_to_v145_schema_leaves_a_usable_vault(
    legacy_client: httpx.AsyncClient,
) -> None:
    conn = await admin_connection(MIGRATION_DB)
    try:
        key, _ = await _seed_v145_vault(conn)
    finally:
        await conn.close()
    await _alembic("upgrade", "head")
    assert await unlock(legacy_client) == key

    conn = await admin_connection(MIGRATION_DB)
    try:
        token = await conn.fetchval("SELECT key_check FROM master_password")
        assert verify_key_check(key, token)
        before = [tuple(r) for r in await conn.fetch(CIPHERTEXT_COLUMNS)]
    finally:
        await conn.close()

    await _alembic("downgrade", PRE_PATCH_REVISION)

    conn = await admin_connection(MIGRATION_DB)
    try:
        columns = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'master_password'"
        )
        assert "key_check" not in {c["column_name"] for c in columns}
        assert [tuple(r) for r in await conn.fetch(CIPHERTEXT_COLUMNS)] == before
        salt, hash_key = await conn.fetchrow(
            "SELECT salt, hash_key FROM master_password"
        )
        assert verify_master_password(MASTER_PASSWORD, hash_key)
        derived = generate_key_derivation(salt, MASTER_PASSWORD)
        assert Fernet(derived).decrypt(before[0][2]) == b"legacy-Value-1"
    finally:
        await conn.close()

    await _alembic("upgrade", "head")
