import asyncio
import hashlib
import io
import json
import os
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import pyzipper
from sqlalchemy import text

from helpers import generate_key_derivation
from tests.integrity import (
    Entry,
    VaultContents,
    assert_same_vault,
    diff_ciphertext,
    raw_vault,
    read_vault,
)
from tests.support import (
    BACKEND_DIR,
    NEW_MASTER_PASSWORD,
    admin_connection,
    apply_runtime_schema,
    auth,
    client_for_database,
    create_vault,
    database_engine,
    db_snapshot,
    ensure_database,
    key_auth,
    reset_schema,
    run_alembic,
)

GOLDEN = Path(__file__).resolve().parents[2] / "testdata" / "golden"
RELEASES = sorted(path.name for path in GOLDEN.iterdir() if path.is_dir())
GOLDEN_DB = os.environ["POSTGRES_DB"].removesuffix("_test") + "_golden_test"
REVISIONS = {
    path.name.split("_", 1)[0]
    for path in (BACKEND_DIR / "migrations" / "ciphermoth" / "versions").glob("*.py")
}
HEAD = run_alembic("heads").split()[0]
ENTRY_FIELDS = {
    "kind": "kind",
    "username": "username",
    "description": "description",
    "password_value": "value",
    "url": "url",
    "totp_secret": "totp_secret",
    "folder": "folder",
    "favorite": "favorite",
    "backed_up": "backed_up",
}


def expected(release: str) -> dict:
    data = json.loads((GOLDEN / release / "expected.json").read_text(encoding="utf-8"))
    assert data["format"] == "ciphermoth-golden/1"
    return data


async def load_fixture(release: str) -> None:
    await ensure_database(GOLDEN_DB)
    await asyncio.to_thread(reset_schema, GOLDEN_DB)
    dump = (GOLDEN / release / "dump.sql").read_text(encoding="utf-8")
    assert hashlib.sha256(dump.encode()).hexdigest() == expected(release)["dump_sha256"]
    conn = await admin_connection(GOLDEN_DB)
    try:
        await conn.execute(dump)
    finally:
        await conn.close()


async def scan(key: str, master_password: str) -> tuple[dict, VaultContents]:
    async with database_engine(GOLDEN_DB) as golden, golden.connect() as conn:
        raw = await raw_vault(conn)
        contents = await read_vault(
            conn, key, master_password=master_password, known_revisions=REVISIONS
        )
    return raw, contents


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def assert_entry_matches(entry: Entry, item: dict) -> None:
    for api_field, attribute in ENTRY_FIELDS.items():
        if api_field in item:
            assert getattr(entry, attribute) == item[api_field], (entry.name, api_field)
    assert list(entry.tags) == item["tags"]
    assert [
        {"label": label, "value": value, "hidden": hidden}
        for label, value, hidden in entry.custom_fields
    ] == item.get("custom_fields", [])
    assert [(v, datetime.fromisoformat(c)) for v, c in entry.history] == [
        (h["value"], datetime.fromisoformat(h["changed_at"]))
        for h in item["password_history"]
    ]
    assert _iso(entry.updated) == item["updated"]
    assert _iso(entry.deleted) == item.get("deleted")


def assert_contents_match(contents: VaultContents, data: dict) -> None:
    assert sorted(contents.active) == sorted(i["password_name"] for i in data["active"])
    for item in data["active"]:
        assert_entry_matches(contents.active[item["password_name"]], item)
    trash = {(e.name, _iso(e.deleted)): e for e in contents.trash}
    assert sorted(trash) == sorted(
        (i["password_name"], i["deleted"]) for i in data["trash"]
    )
    for item in data["trash"]:
        assert_entry_matches(trash[(item["password_name"], item["deleted"])], item)
    by_name = {e.name: e for e in contents.entries}
    for name, files in data["attachments"].items():
        got = sorted(a.identity for a in by_name[name].attachments)
        assert got == sorted(
            (f["filename"], f["content_type"], f["size_bytes"], f["sha256"])
            for f in files
        )
    [settings] = contents.settings
    assert {k: settings[k] for k in data["settings"]} == data["settings"]


@pytest.mark.parametrize("release", RELEASES)
async def test_historical_vault_is_intact_before_any_upgrade(release: str) -> None:
    data = expected(release)
    await load_fixture(release)

    _, contents = await scan(data["key"], data["master_password"])

    assert contents.revision == data["alembic_revision"]
    assert contents.key_check == (
        "valid" if "key_check" in data["features"] else "absent"
    )
    assert_contents_match(contents, data)


@pytest.mark.parametrize("release", RELEASES)
async def test_historical_vault_upgrades_unlocks_and_rotates(release: str) -> None:
    data = expected(release)
    await load_fixture(release)
    raw_before, before = await scan(data["key"], data["master_password"])

    await asyncio.to_thread(run_alembic, "upgrade", "head", database=GOLDEN_DB)
    await asyncio.to_thread(apply_runtime_schema, GOLDEN_DB)
    await asyncio.to_thread(apply_runtime_schema, GOLDEN_DB)

    raw_after, after = await scan(data["key"], data["master_password"])
    assert after.revision == HEAD
    assert diff_ciphertext(raw_before, raw_after) == []
    for table, rows in raw_before.items():
        for row_id, row in rows.items():
            assert {k: raw_after[table][row_id][k] for k in row} == row, (table, row_id)
    assert_same_vault(before, after)

    async with client_for_database(GOLDEN_DB) as api:
        stale = await api.get("/passwords", headers=key_auth(data["key"]))
        if "key_check" in data["features"]:
            assert stale.status_code == 200
        else:
            assert stale.status_code == 403
            assert stale.json()["code"] == "invalid_key"

        resp = await api.post(
            "/master_password/check",
            json={"master_password": f"  {data['master_password']}  "},
        )
        assert resp.json() == {"valid": True, "key_derivation": data["key"]}
        resp = await api.get("/passwords", headers=key_auth(data["key"]))
        assert resp.status_code == 200
        resp = await api.post(
            "/master_password/unlock",
            json={"master_password": f"  {data['master_password']}  "},
        )
        assert data["key"] not in resp.text
        headers = auth(resp.json()["session_token"])

        listing = (await api.get("/passwords", headers=headers)).json()
        assert [i["password_name"] for i in listing] == [
            i["password_name"] for i in data["active"]
        ]
        for got, want in zip(listing, data["active"], strict=True):
            assert {k: got[k] for k in want} == want
        trash = (await api.get("/passwords/trash", headers=headers)).json()
        assert sorted(i["password_name"] for i in trash) == sorted(
            i["password_name"] for i in data["trash"]
        )
        settings = (await api.get("/settings", headers=headers)).json()
        assert {k: settings[k] for k in data["settings"]} == data["settings"]
        for name, files in data["attachments"].items():
            if name not in {i["password_name"] for i in listing}:
                continue
            path = f"/passwords/{name.replace('#', '%23')}/attachments"
            for item in (await api.get(path, headers=headers)).json():
                content = (
                    await api.get(f"{path}/{item['id']}", headers=headers)
                ).content
                assert hashlib.sha256(content).hexdigest() in {
                    f["sha256"] for f in files
                }

        resp = await api.patch(
            "/master_password/update",
            json={
                "master_password": data["master_password"],
                "new_master_password": NEW_MASTER_PASSWORD,
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert (await api.get("/passwords", headers=headers)).status_code == 401
        stale = await api.get("/passwords", headers=key_auth(data["key"]))
        assert stale.status_code == 403
        async with database_engine(GOLDEN_DB) as golden, golden.connect() as conn:
            salt = await conn.scalar(text("SELECT salt FROM master_password"))
        new_key = generate_key_derivation(salt, NEW_MASTER_PASSWORD).decode()

    _, rotated = await scan(new_key, NEW_MASTER_PASSWORD)
    assert rotated.key_check == "valid"
    assert_same_vault(before, rotated)


def backup_entries(release: str, password: str) -> list[dict] | None:
    archive = (GOLDEN / release / "backup.zip").read_bytes()
    with pyzipper.AESZipFile(io.BytesIO(archive)) as zf:
        zf.setpassword(password.encode())
        if "ciphermoth_backup.json" not in zf.namelist():
            return None
        return json.loads(zf.read("ciphermoth_backup.json"))["passwords"]


@pytest.mark.parametrize("release", RELEASES)
async def test_historical_backup_restores_into_the_current_release(
    client: httpx.AsyncClient, release: str
) -> None:
    data = expected(release)
    archive = (GOLDEN / release / "backup.zip").read_bytes()
    assert hashlib.sha256(archive).hexdigest() == data["backup_sha256"]
    token = await create_vault(client, data["master_password"])
    before = await db_snapshot()

    resp = await client.post(
        "/passwords/import",
        data={"master_password": data["master_password"]},
        files={"file": ("backup.zip", archive, "application/zip")},
        headers=auth(token),
    )

    entries = backup_entries(release, data["master_password"])
    if entries is None:
        assert resp.status_code == 400
        assert "valid ciphermoth backup" in resp.json()["detail"]
        assert await db_snapshot() == before
        return
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == len(entries)
    restored = {
        p["password_name"]: p
        for p in (await client.get("/passwords", headers=auth(token))).json()
    }
    active = {i["password_name"]: i for i in data["active"]}
    for item in entries:
        got = restored[item["name"]]
        assert (
            got["password_value"]
            == item["value"]
            == active[item["name"]]["password_value"]
        )
        for field in ("username", "url", "totp_secret", "tags", "favorite"):
            assert got[field] == item[field]
        assert got["kind"] == item.get("kind", "login")
        assert got["folder"] == item.get("folder")
        assert got["custom_fields"] == item.get("custom_fields", [])
        assert got["description"] == item["description"]


async def test_the_migration_chain_downgrades_and_upgrades_step_by_step() -> None:
    await ensure_database(GOLDEN_DB)
    await asyncio.to_thread(reset_schema, GOLDEN_DB)
    revisions = [
        line.split(" -> ")[1].split(" ")[0].strip(",")
        for line in run_alembic("history", "-r", "base:head").splitlines()
        if " -> " in line
    ]
    assert revisions[0] == HEAD
    await asyncio.to_thread(run_alembic, "upgrade", "head", database=GOLDEN_DB)
    for _ in revisions:
        await asyncio.to_thread(run_alembic, "downgrade", "-1", database=GOLDEN_DB)
    assert "(head)" not in await asyncio.to_thread(
        run_alembic, "current", database=GOLDEN_DB
    )
    await asyncio.to_thread(run_alembic, "upgrade", "head", database=GOLDEN_DB)
    assert HEAD in await asyncio.to_thread(run_alembic, "current", database=GOLDEN_DB)


async def test_downgrading_to_the_previous_head_keeps_data_it_can_represent() -> None:
    data = expected("v1.1.0")
    await load_fixture("v1.1.0")
    raw_before, before = await scan(data["key"], data["master_password"])

    await asyncio.to_thread(run_alembic, "upgrade", "head", database=GOLDEN_DB)
    await asyncio.to_thread(apply_runtime_schema, GOLDEN_DB)
    await asyncio.to_thread(
        run_alembic, "downgrade", data["alembic_revision"], database=GOLDEN_DB
    )

    raw_after, after = await scan(data["key"], data["master_password"])
    for table, rows in raw_before.items():
        for row_id, row in rows.items():
            assert {k: raw_after[table][row_id][k] for k in row} == row
    assert_same_vault(before, after)


async def test_downgrade_cannot_roll_back_a_vault_that_uses_the_trash() -> None:
    await load_fixture("v1.4.5")
    with pytest.raises(RuntimeError, match="could not create unique index"):
        await asyncio.to_thread(
            run_alembic, "downgrade", "4d5e6f7a8b9c", database=GOLDEN_DB
        )
