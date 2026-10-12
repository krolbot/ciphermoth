import json
import os

import httpx
import pytest
from cryptography.fernet import Fernet

from helpers import encrypt
from tests.integrity import (
    VaultContents,
    VaultIntegrityError,
    assert_same_vault,
    diff_ciphertext,
    diff_vaults,
    raw_vault,
    read_vault,
)
from tests.support import (
    MASTER_PASSWORD,
    NEW_MASTER_PASSWORD,
    create_legacy_vault,
    db_execute,
    engine,
    entry,
    key_auth,
    legacy_unlock,
)

BLOB = os.urandom(4096) + b"\x00\xff"


async def _scan(key: str, **options: object) -> VaultContents:
    async with engine.connect() as conn:
        return await read_vault(conn, key, **options)  # ty: ignore[invalid-argument-type]


async def _rich_vault(client: httpx.AsyncClient) -> str:
    key = await create_legacy_vault(client)
    headers = key_auth(key)
    login = entry(
        "GitHub",
        "first-Value-1",
        username="moth@example.com",
        url="https://github.com",
        totp_secret="JBSWY3DPEHPK3PXP",
        description="work",
        tags=["dev", "ops"],
        custom_fields=[{"label": "PIN", "value": "1234", "hidden": True}],
        folder="Work",
        favorite=True,
    )
    for item in (
        login,
        entry("Notes ✉", "  body\n\n", kind="note"),
        entry("Old", "old-Value-1"),
    ):
        assert (
            await client.post("/passwords/create", json=item, headers=headers)
        ).is_success
    for value in ("second-Value-2", "third-Value-3"):
        resp = await client.patch(
            "/passwords/update",
            json={
                "password": login,
                "new_password": {**login, "password_value": value},
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/passwords/GitHub/attachments",
        files={"file": ("scan ț.bin", BLOB, "application/octet-stream")},
        headers=headers,
    )
    assert resp.status_code == 200
    assert (await client.delete("/passwords/Old", headers=headers)).is_success
    return key


async def test_a_healthy_vault_scans_clean_and_matches_the_api(
    client: httpx.AsyncClient,
) -> None:
    key = await _rich_vault(client)

    vault = await _scan(key, master_password=MASTER_PASSWORD)

    assert vault.key_check == "valid"
    assert vault.master_rows == 1
    github = vault.active["GitHub"]
    assert github.value == "third-Value-3"
    assert [h[0] for h in github.history] == ["second-Value-2", "first-Value-1"]
    assert github.custom_fields == (("PIN", "1234", True),)
    assert github.tags == ("dev", "ops")
    assert github.favorite
    [attachment] = github.attachments
    assert attachment.filename == "scan ț.bin"
    assert attachment.size_bytes == len(BLOB)
    assert vault.active["Notes ✉"].value == "  body\n\n"
    assert [e.name for e in vault.trash] == ["Old"]

    listing = (await client.get("/passwords", headers=key_auth(key))).json()
    for item in listing:
        scanned = vault.active[item["password_name"]]
        assert scanned.value == item["password_value"]
        assert scanned.url == item["url"]
        assert list(scanned.tags) == item["tags"]


async def test_the_wrong_key_reports_every_encrypted_value(
    client: httpx.AsyncClient,
) -> None:
    await _rich_vault(client)

    vault = await _scan(Fernet.generate_key().decode(), strict=False)

    assert vault.key_check == "invalid"
    failing = {(p.table, p.column) for p in vault.problems}
    assert ("passwords", "password_value") in failing
    assert ("passwords", "tags") in failing
    assert ("password_attachments", "content") in failing
    with pytest.raises(VaultIntegrityError):
        await _scan(Fernet.generate_key().decode())


@pytest.mark.parametrize(
    ("sql", "plaintext", "column"),
    [
        (
            "UPDATE passwords SET url = :token WHERE password_name = 'GitHub'",
            None,
            "url",
        ),
        (
            "UPDATE passwords SET tags = :token WHERE password_name = 'GitHub'",
            b"not json",
            "tags",
        ),
        (
            "UPDATE passwords SET tags = :token WHERE password_name = 'GitHub'",
            b'{"a": 1}',
            "tags",
        ),
        (
            "UPDATE passwords SET tags = :token WHERE password_name = 'GitHub'",
            b"[1]",
            "tags",
        ),
        (
            "UPDATE passwords SET custom_fields = :token "
            "WHERE password_name = 'GitHub'",
            b'[{"label": 5}]',
            "custom_fields",
        ),
        (
            "UPDATE passwords SET password_history = :token "
            "WHERE password_name = 'GitHub'",
            b'[{"value": "x", "changed_at": "yesterday"}]',
            "password_history",
        ),
        (
            "UPDATE passwords SET folder = :token WHERE password_name = 'GitHub'",
            b"\xff\xfe",
            "folder",
        ),
        ("UPDATE password_attachments SET size_bytes = 1", None, "size_bytes"),
        (
            "UPDATE passwords SET kind = 'card' WHERE password_name = 'GitHub'",
            None,
            "kind",
        ),
        (
            "UPDATE passwords SET updated = created - interval '1 day' "
            "WHERE password_name = 'GitHub'",
            None,
            "updated",
        ),
    ],
)
async def test_damage_the_app_would_hide_is_reported(
    client: httpx.AsyncClient, sql: str, plaintext: bytes | None, column: str
) -> None:
    key = await _rich_vault(client)
    token = (
        encrypt(Fernet.generate_key(), b"foreign")
        if plaintext is None
        else encrypt(key, plaintext)
    )
    await db_execute(sql, token=token)

    with pytest.raises(VaultIntegrityError) as raised:
        await _scan(key)

    assert [p.column for p in raised.value.problems] == [column]


async def test_a_flipped_ciphertext_byte_is_reported(client: httpx.AsyncClient) -> None:
    key = await _rich_vault(client)
    [(token,)] = await db_execute(
        "SELECT password_value FROM passwords WHERE password_name = 'GitHub'"
    )
    flipped = bytearray(token)
    flipped[len(flipped) // 2] ^= 0x01
    await db_execute(
        "UPDATE passwords SET password_value = :t WHERE password_name = 'GitHub'",
        t=bytes(flipped),
    )

    with pytest.raises(VaultIntegrityError, match="password_value"):
        await _scan(key)


async def test_orphaned_attachments_and_duplicate_rows_are_reported(
    client: httpx.AsyncClient,
) -> None:
    key = await _rich_vault(client)
    await db_execute(
        "INSERT INTO master_password (salt, hash_key) SELECT salt, hash_key "
        "FROM master_password"
    )
    async with engine.begin() as conn:
        await conn.exec_driver_sql("SET LOCAL session_replication_role = replica")
        await conn.exec_driver_sql("UPDATE password_attachments SET password_id = 999")

    vault = await _scan(key, strict=False)

    reasons = sorted(str(p) for p in vault.problems)
    assert any("password_id: no such entry" in r for r in reasons)
    assert any("master_password[None].*: 2 rows" in r for r in reasons)


async def test_rotation_keeps_every_plaintext_and_replaces_every_token(
    client: httpx.AsyncClient,
) -> None:
    key = await _rich_vault(client)
    before = await _scan(key)
    async with engine.connect() as conn:
        tokens_before = await raw_vault(conn)

    resp = await client.patch(
        "/master_password/update",
        json={
            "master_password": MASTER_PASSWORD,
            "new_master_password": NEW_MASTER_PASSWORD,
        },
        headers=key_auth(key),
    )
    assert resp.status_code == 200, resp.text
    new_key = await legacy_unlock(client, NEW_MASTER_PASSWORD)

    after = await _scan(new_key, master_password=NEW_MASTER_PASSWORD)
    assert_same_vault(before, after)
    assert after.key_check == "valid"
    async with engine.connect() as conn:
        changed = diff_ciphertext(tokens_before, await raw_vault(conn))
        tokens_after = await raw_vault(conn)
    non_null = sum(
        1
        for table, columns in (
            (
                "passwords",
                (
                    "password_value",
                    "url",
                    "totp_secret",
                    "tags",
                    "custom_fields",
                    "folder",
                    "password_history",
                ),
            ),
            ("password_attachments", ("filename", "content", "content_type")),
        )
        for row in tokens_after[table].values()
        for column in columns
        if row[column] is not None
    )
    assert len(changed) == non_null
    with pytest.raises(VaultIntegrityError):
        await _scan(key)


async def test_a_backup_restore_is_lossy_exactly_where_documented(
    client: httpx.AsyncClient,
) -> None:
    key = await _rich_vault(client)
    original = await _scan(key)
    resp = await client.post(
        "/passwords/backup",
        json={"master_password": MASTER_PASSWORD},
        headers=key_auth(key),
    )
    archive = resp.content
    await db_execute(
        "TRUNCATE master_password, passwords, password_attachments, settings "
        "RESTART IDENTITY CASCADE"
    )
    new_key = await create_legacy_vault(client)
    resp = await client.post(
        "/passwords/import",
        data={"master_password": MASTER_PASSWORD},
        files={"file": ("b.zip", archive, "application/zip")},
        headers=key_auth(new_key),
    )
    assert resp.status_code == 200, resp.text
    restored = await _scan(new_key)

    github = original.active["GitHub"]
    attached = sorted(a.identity for a in github.attachments)
    differences = diff_vaults(original, restored)
    assert differences == sorted(
        [
            f"(False, 'GitHub', None) attachments: {attached!r} != []",
            f"(False, 'GitHub', None) history: {github.history!r} != ()",
            f"missing after: {(True, 'Old', original.trash[0].deleted)}",
        ]
    )
    assert_same_vault(
        original,
        restored,
        compare=[
            f
            for f in (
                "kind",
                "username",
                "description",
                "value",
                "url",
                "totp_secret",
                "tags",
                "custom_fields",
                "folder",
                "favorite",
            )
        ],
        attachments=False,
        trash=False,
    )


async def test_diff_rejects_unknown_fields() -> None:
    empty = VaultContents(None, 0, "absent", (), ())
    with pytest.raises(ValueError, match="nonsense"):
        diff_vaults(empty, empty, compare=["nonsense"])
    assert json.dumps(diff_vaults(empty, empty)) == "[]"


async def test_strictness_options_report_what_the_app_tolerates(
    client: httpx.AsyncClient,
) -> None:
    key = await _rich_vault(client)
    await db_execute("UPDATE master_password SET key_check = NULL")
    assert (await _scan(key)).key_check == "absent"
    with pytest.raises(VaultIntegrityError, match="key_check: absent"):
        await _scan(key, require_key_check=True)

    await db_execute("UPDATE passwords SET kind = '' WHERE password_name = 'Old'")
    with pytest.raises(VaultIntegrityError, match="kind"):
        await _scan(key)
