import asyncio
import json
import os
from collections.abc import AsyncIterator

import httpx
import pytest

from helpers import (
    encrypt,
    generate_key_derivation,
    hash_master_password,
    verify_key_check,
)
from tests.support import (
    MASTER_PASSWORD,
    NEW_MASTER_PASSWORD,
    admin_connection,
    apply_runtime_schema,
    auth,
    client_for_database,
    ensure_database,
    reset_schema,
    run_alembic,
    unlock,
)

V145_HEAD = "9c0d1e2f3a4b"
MIGRATION_DB = os.environ["POSTGRES_DB"].removesuffix("_test") + "_migration_test"
CIPHERTEXT_COLUMNS = (
    "SELECT id, password_name, password_value, url, totp_secret, tags, "
    "custom_fields, folder, password_history, deleted FROM passwords ORDER BY id"
)


async def _alembic(*args: str) -> str:
    return await asyncio.to_thread(run_alembic, *args, database=MIGRATION_DB)


async def _start_v146() -> None:
    await asyncio.to_thread(apply_runtime_schema, MIGRATION_DB)


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
    await ensure_database(MIGRATION_DB)
    await asyncio.to_thread(reset_schema, MIGRATION_DB)
    await _alembic("upgrade", "head")
    yield MIGRATION_DB


@pytest.fixture
async def legacy_client(legacy_db: str) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for_database(legacy_db) as http:
        yield http


async def test_release_keeps_the_v145_alembic_head() -> None:
    output = await asyncio.to_thread(run_alembic, "heads")
    assert output.split() == [V145_HEAD, "(head)"], (
        "A new Alembic revision makes v1.4.5 crash-loop after the one-click "
        "updater rolls back. The updater must meet the contract in CONTRIBUTING.md "
        "('Schema changes and the updater') before a revision is added."
    )


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

    await _start_v146()

    conn = await admin_connection(MIGRATION_DB)
    try:
        assert [tuple(r) for r in await conn.fetch(CIPHERTEXT_COLUMNS)] == before
        assert await conn.fetch("SELECT * FROM password_attachments") == (
            attachments_before
        )
        assert await conn.fetchval("SELECT key_check FROM master_password") is None
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == (
            V145_HEAD
        )
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


async def test_v146_database_stays_bootable_by_v145(
    legacy_client: httpx.AsyncClient,
) -> None:
    conn = await admin_connection(MIGRATION_DB)
    try:
        key, _ = await _seed_v145_vault(conn)
    finally:
        await conn.close()
    await _start_v146()
    await _start_v146()
    assert await unlock(legacy_client) == key

    output = await _alembic("upgrade", "head")
    assert "Running upgrade" not in output
    assert V145_HEAD in await _alembic("current")

    conn = await admin_connection(MIGRATION_DB)
    try:
        salt, token = await conn.fetchrow("SELECT salt, key_check FROM master_password")
        assert verify_key_check(key, token, salt)
        column = await conn.fetchrow(
            "SELECT is_nullable, column_default FROM information_schema.columns "
            "WHERE table_name = 'master_password' AND column_name = 'key_check'"
        )
        assert column["is_nullable"] == "YES"
        assert column["column_default"] is None
        rows = await conn.fetch(
            "SELECT id, created, updated, deleted, salt, hash_key FROM master_password"
        )
        assert len(rows) == 1
    finally:
        await conn.close()
