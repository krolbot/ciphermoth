import asyncio
import io
from collections.abc import Awaitable, Callable

import httpx
import pytest

from crud.password import PasswordCRUD
from helpers import create_encrypted_zip
from tests.support import (
    MASTER_PASSWORD,
    NEW_MASTER_PASSWORD,
    Headers,
    admin_connection,
    auth,
    create_vault,
    db_execute,
    db_snapshot,
    entry,
    unlock,
)

ALPHA = entry("alpha", "alpha-Value-1", username="moth")
SETTINGS = {
    "inactivity_ms": 300_000,
    "warn_before_ms": 30_000,
    "hidden_ms": 120_000,
    "debounce_ms": 500,
    "clipboard_clear_ms": 15_000,
    "update_check_enabled": False,
}
ROTATE = {
    "master_password": MASTER_PASSWORD,
    "new_master_password": NEW_MASTER_PASSWORD,
}

Write = Callable[[httpx.AsyncClient, Headers], Awaitable[httpx.Response]]


def _upload(name: str, data: bytes = b"attached") -> dict:
    return {"files": {"file": (name, data, "application/octet-stream")}}


WRITES: dict[str, Write] = {
    "create": lambda c, h: c.post("/passwords/create", json=entry("new"), headers=h),
    "update": lambda c, h: c.patch(
        "/passwords/update",
        json={"password": ALPHA, "new_password": {**ALPHA, "password_value": "v2"}},
        headers=h,
    ),
    "favorite": lambda c, h: c.patch(
        "/passwords/alpha/favorite", json={"favorite": True}, headers=h
    ),
    "delete": lambda c, h: c.delete("/passwords/alpha", headers=h),
    "restore": lambda c, h: c.post("/passwords/trashed/restore", headers=h),
    "purge": lambda c, h: c.delete("/passwords/trashed/purge", headers=h),
    "attachment-add": lambda c, h: c.post(
        "/passwords/alpha/attachments", headers=h, **_upload("b.bin")
    ),
    "attachment-delete": lambda c, h: c.delete(
        "/passwords/alpha/attachments/1", headers=h
    ),
    "import-zip": lambda c, h: c.post(
        "/passwords/import",
        data={"master_password": MASTER_PASSWORD, "on_conflict": "overwrite"},
        files={
            "file": (
                "b.zip",
                create_encrypted_zip(
                    [{"name": "alpha", "value": "z"}, {"name": "zip", "value": "z"}],
                    MASTER_PASSWORD,
                ),
                "application/zip",
            )
        },
        headers=h,
    ),
    "import-csv": lambda c, h: c.post(
        "/passwords/import/csv",
        data={"on_conflict": "overwrite"},
        files={"file": ("x.csv", b"name,password\nalpha,c\ncsv,c\n", "text/csv")},
        headers=h,
    ),
    "settings": lambda c, h: c.patch("/settings", json=SETTINGS, headers=h),
    "rotation": lambda c, h: c.patch("/master_password/update", json=ROTATE, headers=h),
    "backup": lambda c, h: c.post(
        "/passwords/backup", json={"master_password": MASTER_PASSWORD}, headers=h
    ),
}


async def _populated_vault(client: httpx.AsyncClient) -> Headers:
    headers = auth(await create_vault(client))
    for item in (ALPHA, entry("trashed")):
        assert (
            await client.post("/passwords/create", json=item, headers=headers)
        ).is_success
    assert (await client.delete("/passwords/trashed", headers=headers)).is_success
    resp = await client.post(
        "/passwords/alpha/attachments", headers=headers, **_upload("a.bin")
    )
    assert resp.status_code == 200
    return headers


@pytest.fixture
def failing_commit(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    async def commit(self) -> None:
        raise RuntimeError("simulated commit failure")

    def arm() -> None:
        monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.commit", commit)

    return arm


@pytest.mark.parametrize("name", sorted(WRITES))
async def test_a_failed_commit_is_never_reported_as_success(
    client: httpx.AsyncClient, failing_commit: Callable[[], None], name: str
) -> None:
    headers = await _populated_vault(client)
    before = await db_snapshot()
    failing_commit()

    resp = await WRITES[name](client, headers)

    assert resp.status_code == 500, resp.text
    assert resp.json() == {"detail": "An internal server error occurred."}
    assert await db_snapshot() == before


@pytest.mark.parametrize("name", sorted(WRITES))
async def test_every_write_is_visible_as_soon_as_it_is_acknowledged(
    client: httpx.AsyncClient, name: str
) -> None:
    headers = await _populated_vault(client)
    before = await db_snapshot()

    resp = await WRITES[name](client, headers)

    assert resp.status_code == 200, resp.text
    assert await db_snapshot() != before


async def test_first_unlock_of_a_legacy_vault_fails_cleanly_if_its_commit_fails(
    client: httpx.AsyncClient, failing_commit: Callable[[], None]
) -> None:
    await _populated_vault(client)
    await db_execute("UPDATE master_password SET key_check = NULL")
    before = await db_snapshot()
    failing_commit()

    resp = await client.post(
        "/master_password/unlock", json={"master_password": MASTER_PASSWORD}
    )

    assert resp.status_code == 500
    assert "session_token" not in resp.text
    assert await db_snapshot() == before


async def test_vault_creation_rolls_back_if_its_commit_fails(
    client: httpx.AsyncClient, failing_commit: Callable[[], None]
) -> None:
    failing_commit()
    resp = await client.post(
        "/master_password/create", json={"master_password": MASTER_PASSWORD}
    )
    assert resp.status_code == 500
    assert "key_derivation" not in resp.text
    assert await db_execute("SELECT id FROM master_password") == []


async def test_an_import_failing_halfway_writes_nothing(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _populated_vault(client)
    before = await db_snapshot()
    original = PasswordCRUD._upsert_entry
    calls = 0

    def upsert_then_fail(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 50:
            raise RuntimeError("simulated failure halfway through")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PasswordCRUD, "_upsert_entry", upsert_then_fail)
    rows = "\n".join(f"row-{i},pass-{i}" for i in range(100))
    resp = await client.post(
        "/passwords/import/csv",
        data={"on_conflict": "overwrite"},
        files={
            "file": ("x.csv", f"name,password\nalpha,x\n{rows}\n".encode(), "text/csv")
        },
        headers=headers,
    )

    assert resp.status_code == 500
    assert calls == 50
    assert await db_snapshot() == before


async def test_a_rotation_failing_halfway_leaves_the_old_vault(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _populated_vault(client)
    for i in range(20):
        await client.post("/passwords/create", json=entry(f"e{i:02d}"), headers=headers)
    before = await db_snapshot()
    from crud.master_password import MasterPasswordCRUD

    original = MasterPasswordCRUD._reencrypt_binary
    calls = 0

    def reencrypt_then_fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated failure during rotation")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        MasterPasswordCRUD, "_reencrypt_binary", staticmethod(reencrypt_then_fail)
    )
    resp = await client.patch("/master_password/update", json=ROTATE, headers=headers)
    monkeypatch.undo()

    assert resp.status_code == 500
    assert await db_snapshot() == before
    assert (await client.get("/passwords", headers=headers)).status_code == 200
    assert (
        await client.get("/passwords", headers=auth(await unlock(client)))
    ).is_success


async def test_concurrent_uploads_cannot_exceed_the_attachment_cap(
    client: httpx.AsyncClient,
) -> None:
    headers = await _populated_vault(client)
    for i in range(18):
        resp = await client.post(
            "/passwords/alpha/attachments", headers=headers, **_upload(f"f{i}.bin")
        )
        assert resp.status_code == 200
    blocker = await admin_connection()
    try:
        await blocker.execute("BEGIN")
        await blocker.execute(
            "SELECT 1 FROM passwords WHERE password_name = 'alpha' FOR UPDATE"
        )
        uploads = asyncio.gather(
            *(
                client.post(
                    "/passwords/alpha/attachments",
                    headers=headers,
                    **_upload(f"race{i}.bin"),
                )
                for i in range(6)
            )
        )
        await _wait_for_blocked_sessions(6)
        await blocker.execute("ROLLBACK")
        responses = await uploads
    finally:
        await blocker.close()

    assert sorted(r.status_code for r in responses) == [200, 400, 400, 400, 400, 400]
    rows = await db_execute("SELECT count(*) FROM password_attachments")
    assert rows == [(20,)]


async def _wait_for_blocked_sessions(count: int, timeout: float = 30) -> None:
    observer = await admin_connection()
    try:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            blocked = await observer.fetchval(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
            if blocked >= count:
                return
            assert asyncio.get_running_loop().time() < deadline, (
                f"only {blocked} of {count} requests waited on the entry lock"
            )
            await asyncio.sleep(0.05)
    finally:
        await observer.close()


async def test_concurrent_uploads_cannot_exceed_the_size_cap(
    client: httpx.AsyncClient,
) -> None:
    headers = await _populated_vault(client)
    four_mb = b"\x00" * (4 * 1024 * 1024)
    for i in range(5):
        resp = await client.post(
            "/passwords/alpha/attachments",
            headers=headers,
            **_upload(f"big{i}", four_mb),
        )
        assert resp.status_code == 200

    responses = await asyncio.gather(
        *(
            client.post(
                "/passwords/alpha/attachments",
                headers=headers,
                **_upload(f"race{i}", b"\x01" * (3 * 1024 * 1024)),
            )
            for i in range(3)
        )
    )

    assert sorted(r.status_code for r in responses) == [200, 400, 400]
    [(total,)] = await db_execute("SELECT sum(size_bytes) FROM password_attachments")
    assert total <= 25 * 1024 * 1024


async def test_concurrent_edits_of_one_entry_lose_no_password(
    client: httpx.AsyncClient,
) -> None:
    headers = await _populated_vault(client)

    responses = await asyncio.gather(
        *(
            client.patch(
                "/passwords/update",
                json={
                    "password": ALPHA,
                    "new_password": {**ALPHA, "password_value": v},
                },
                headers=headers,
            )
            for v in ("edit-B", "edit-C", "edit-D")
        )
    )

    assert [r.status_code for r in responses] == [200, 200, 200]
    got = (await client.get("/passwords/alpha", headers=headers)).json()
    seen = {got["password_value"], *(h["value"] for h in got["password_history"])}
    assert seen == {"alpha-Value-1", "edit-B", "edit-C", "edit-D"}


@pytest.mark.parametrize("attempt", range(3))
async def test_restore_racing_a_create_of_the_same_name_never_fails_with_500(
    client: httpx.AsyncClient, attempt: int
) -> None:
    headers = await _populated_vault(client)

    restore, create = await asyncio.gather(
        client.post("/passwords/trashed/restore", headers=headers),
        client.post("/passwords/create", json=entry("trashed"), headers=headers),
    )

    assert sorted([restore.status_code, create.status_code]) == [200, 400]
    rows = await db_execute(
        "SELECT count(*) FROM passwords WHERE password_name = 'trashed' "
        "AND deleted IS NULL"
    )
    assert rows == [(1,)]


async def test_import_racing_a_create_of_the_same_name_never_fails_with_500(
    client: httpx.AsyncClient,
) -> None:
    headers = await _populated_vault(client)
    csv = "name,password\n" + "\n".join(f"n{i},p{i}" for i in range(200)) + "\nlate,x\n"

    created, imported = await asyncio.gather(
        client.post("/passwords/create", json=entry("late"), headers=headers),
        client.post(
            "/passwords/import/csv",
            files={"file": ("x.csv", csv.encode(), "text/csv")},
            headers=headers,
        ),
    )

    assert created.status_code == 200
    assert imported.status_code in (200, 400), imported.text


async def test_backup_of_a_vault_with_an_undecryptable_entry_fails_without_side_effects(
    client: httpx.AsyncClient,
) -> None:
    headers = await _populated_vault(client)
    await db_execute(
        "UPDATE passwords SET password_value = :v WHERE password_name = 'alpha'",
        v=b"gAAAAA-not-a-token",
    )
    before = await db_snapshot()

    resp = await client.post(
        "/passwords/backup", json={"master_password": MASTER_PASSWORD}, headers=headers
    )

    assert resp.status_code == 400
    assert await db_snapshot() == before
    assert io.BytesIO(resp.content).read(2) != b"PK"
