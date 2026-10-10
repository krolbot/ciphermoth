import csv
import io
import json
from pathlib import Path

import httpx
import pytest

from helpers import create_encrypted_zip, encrypt
from tests.support import (
    MASTER_PASSWORD,
    Headers,
    auth,
    create_vault,
    db_execute,
    db_snapshot,
    entry,
)

KIB = 1024


def _csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode()


async def _import_csv(
    client: httpx.AsyncClient,
    headers: Headers,
    data: bytes,
    on_conflict: str = "skip",
) -> httpx.Response:
    return await client.post(
        "/passwords/import/csv",
        data={"on_conflict": on_conflict},
        files={"file": ("export.csv", data, "text/csv")},
        headers=headers,
    )


async def _import_zip(
    client: httpx.AsyncClient,
    headers: Headers,
    entries: list,
    on_conflict: str = "skip",
) -> httpx.Response:
    archive = create_encrypted_zip(entries, MASTER_PASSWORD)
    return await client.post(
        "/passwords/import",
        data={"master_password": MASTER_PASSWORD, "on_conflict": on_conflict},
        files={"file": ("backup.zip", archive, "application/zip")},
        headers=headers,
    )


@pytest.fixture
async def vault(client: httpx.AsyncClient) -> Headers:
    headers = auth(await create_vault(client))
    resp = await client.post(
        "/passwords/create",
        json=entry("existing", "existing-Pass-1", description="keep me"),
        headers=headers,
    )
    assert resp.status_code == 200
    return headers


async def _listing(client: httpx.AsyncClient, headers: Headers) -> list[dict]:
    resp = await client.get("/passwords", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.parametrize("size", [128 * KIB + 1, 512 * KIB, 4 * 1024 * KIB])
async def test_csv_cells_larger_than_the_csv_module_default_import(
    client: httpx.AsyncClient, vault: Headers, size: int
) -> None:
    value = "v" * size
    resp = await _import_csv(
        client, vault, _csv([["name", "password"], ["big", value]])
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 1
    got = await client.get("/passwords/big", headers=vault)
    assert got.json()["password_value"] == value


@pytest.mark.parametrize(
    ("column", "field", "limit"),
    [
        ("title", "password_name", 255),
        ("username", "username", 255),
        ("url", "url", 2048),
        ("notes", "description", 1024),
        ("folder", "folder", 200),
    ],
)
async def test_csv_values_over_the_schema_limits_are_refused_and_nothing_is_written(
    client: httpx.AsyncClient, vault: Headers, column: str, field: str, limit: int
) -> None:
    header = ["title", "password", "username", "url", "notes", "folder"]
    good = ["fine", "fine-Pass-1", "u", "https://x.test", "n", "F"]
    bad = ["bad", "bad-Pass-1", "u", "https://x.test", "n", "F"]
    bad[header.index(column)] = "x" * (limit + 1)
    before = await db_snapshot()

    resp = await _import_csv(client, vault, _csv([header, good, bad]))

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "row 3" in detail
    assert column in detail
    assert str(limit) in detail
    assert "x" * 50 not in detail
    assert await db_snapshot() == before
    assert [p["password_name"] for p in await _listing(client, vault)] == ["existing"]


async def test_csv_values_at_the_schema_limits_import_and_read_back(
    client: httpx.AsyncClient, vault: Headers
) -> None:
    row = {
        "title": "n" * 255,
        "password": "p" * 10_000,
        "username": "u" * 255,
        "url": "h" * 2048,
        "notes": "d" * 1024,
        "folder": "f" * 200,
    }
    resp = await _import_csv(client, vault, _csv([list(row), list(row.values())]))

    assert resp.status_code == 200, resp.text
    [imported] = [p for p in await _listing(client, vault) if p["username"]]
    assert imported["password_name"] == row["title"]
    assert imported["password_value"] == row["password"]
    assert imported["url"] == row["url"]
    assert imported["description"] == row["notes"]
    assert imported["folder"] == row["folder"]


async def test_a_failed_csv_import_does_not_overwrite_existing_entries(
    client: httpx.AsyncClient, vault: Headers
) -> None:
    before = await db_snapshot()
    rows = [
        ["name", "password", "notes"],
        ["existing", "overwritten-Pass-2", "changed"],
        ["new", "new-Pass-1", "x" * 1025],
    ]

    resp = await _import_csv(client, vault, _csv(rows), on_conflict="overwrite")

    assert resp.status_code == 400
    assert await db_snapshot() == before


async def test_unparseable_csv_gets_a_clear_error(
    client: httpx.AsyncClient, vault: Headers
) -> None:
    before = await db_snapshot()
    for data in (b"\xff\xfe\x00bad", b"", b"just,a,header\n", b"name\nonly-names\n"):
        resp = await _import_csv(client, vault, data)
        assert resp.status_code == 400, (data, resp.text)
        assert resp.json()["detail"]
    assert await db_snapshot() == before


@pytest.mark.parametrize(
    ("bad_entry", "where"),
    [
        ({"name": "n" * 256, "value": "v"}, "name"),
        ({"name": "a", "value": "v", "description": "d" * 1025}, "description"),
        ({"name": "a", "value": "v", "username": "u" * 256}, "username"),
        ({"name": "a", "value": "v", "url": "h" * 2049}, "url"),
        ({"name": "a", "value": "v", "folder": "f" * 201}, "folder"),
        ({"name": "a", "value": "v", "tags": [f"t{i}" for i in range(21)]}, "tags"),
        ({"name": "a", "value": "v", "tags": "not-a-list"}, "tags"),
        ({"name": "a", "value": "v", "totp_secret": "not base32!"}, "totp_secret"),
        (
            {
                "name": "a",
                "value": "v",
                "custom_fields": [{"label": "pin", "value": "x" * 4097}],
            },
            "custom_fields",
        ),
        (
            {
                "name": "a",
                "value": "v",
                "custom_fields": [{"label": f"f{i}", "value": "x"} for i in range(31)],
            },
            "custom_fields",
        ),
        ({"name": "a", "value": 12345}, "value"),
        ({"name": ["a"], "value": "v"}, "name"),
        ({"name": "a", "value": "v", "username": {"nested": True}}, "username"),
    ],
)
async def test_backup_entries_that_would_poison_the_vault_are_refused(
    client: httpx.AsyncClient, vault: Headers, bad_entry: dict, where: str
) -> None:
    before = await db_snapshot()
    entries = [{"name": "fine", "value": "fine-Pass-1"}, bad_entry]

    resp = await _import_zip(client, vault, entries)

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "entry 2" in detail
    assert where in detail
    assert await db_snapshot() == before
    assert len(await _listing(client, vault)) == 1


async def test_backup_import_normalizes_like_the_create_endpoint(
    client: httpx.AsyncClient, vault: Headers
) -> None:
    resp = await _import_zip(
        client,
        vault,
        [
            {
                "name": "  spaced  ",
                "value": "  keep surrounding spaces  ",
                "kind": "note",
                "tags": [" a ", "a", "b"],
                "totp_secret": "jbsw y3dp ehpk 3pxp",
                "custom_fields": [
                    {"label": " pin ", "value": " 1234 ", "hidden": True},
                    {"label": "", "value": "dropped"},
                ],
                "folder": "",
                "favorite": True,
            }
        ],
    )
    assert resp.status_code == 200, resp.text
    got = (await client.get("/passwords/spaced", headers=vault)).json()
    assert got["password_value"] == "  keep surrounding spaces  "
    assert got["kind"] == "note"
    assert got["tags"] == ["a", "b"]
    assert got["totp_secret"] == "JBSWY3DPEHPK3PXP"
    assert got["custom_fields"] == [{"label": "pin", "value": "1234", "hidden": True}]
    assert got["folder"] is None
    assert got["favorite"] is True


async def test_backup_entries_without_a_name_or_value_are_still_skipped_quietly(
    client: httpx.AsyncClient, vault: Headers
) -> None:
    resp = await _import_zip(
        client,
        vault,
        [
            {"name": "", "value": "v"},
            {"name": "no-value", "value": ""},
            {"value": "v"},
            "not an object",
            None,
            {"name": "kept", "value": "kept-Pass-1"},
        ],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"imported": 1, "skipped": 0, "overwritten": 0, "total": 1}


async def test_a_vault_poisoned_by_an_older_import_can_be_read_and_repaired(
    client: httpx.AsyncClient, vault: Headers
) -> None:
    key = dict(vault)[b"x-ciphermoth-key-derivation"].decode()
    long_name = "n" * 300
    await db_execute(
        "INSERT INTO passwords (password_name, username, description, "
        "password_value, totp_secret, tags, custom_fields, folder) "
        "VALUES (:name, :username, :description, :value, :totp, :tags, :fields, "
        ":folder)",
        name=long_name,
        username="u" * 300,
        description="d" * 2000,
        value=encrypt(key, b"poisoned-Pass-1"),
        totp=encrypt(key, b"not base32!"),
        tags=encrypt(key, json.dumps([1, "ok", "t" * 60]).encode()),
        fields=encrypt(
            key, json.dumps([{"label": "l" * 150, "value": "v" * 5000}]).encode()
        ),
        folder=encrypt(key, ("f" * 300).encode()),
    )

    listing = await _listing(client, vault)
    poisoned = next(p for p in listing if p["password_name"] == long_name)
    assert poisoned["description"] == "d" * 2000
    assert poisoned["password_value"] == "poisoned-Pass-1"
    assert poisoned["totp_secret"] == "not base32!"
    assert poisoned["tags"] == ["1", "ok", "t" * 60]
    assert poisoned["custom_fields"][0]["value"] == "v" * 5000

    resp = await client.patch(
        "/passwords/update",
        json={
            "password": poisoned,
            "new_password": entry("repaired", "poisoned-Pass-1", description="ok"),
        },
        headers=vault,
    )
    assert resp.status_code == 200, resp.text
    names = [p["password_name"] for p in await _listing(client, vault)]
    assert names == ["existing", "repaired"]


CSV_DIR = Path(__file__).resolve().parents[2] / "testdata" / "csv"

THIRD_PARTY_EXPORTS = {
    "chrome.csv": {
        "example.com": {
            "username": "moth@example.com",
            "password_value": "Chr0me-Pass!",
            "url": "https://example.com/login",
            "description": None,
        },
        "bank.test": {
            "username": "moth",
            "password_value": 'pa,ss"word ',
            "url": "https://bank.test/",
            "description": "Branch 12",
        },
    },
    "bitwarden.csv": {
        "GitHub": {
            "username": "moth",
            "password_value": "Bw-Pass-1",
            "url": "https://github.com",
            "description": "multi\nline note",
            "folder": "Work",
            "totp_secret": "JBSWY3DPEHPK3PXP",
        },
        "Mail ✉": {
            "username": "moth@example.com",
            "password_value": "Bw-Pass-2",
            "folder": "Personal",
            "totp_secret": None,
        },
    },
    "keepassxc.csv": {
        "Mail": {
            "username": "moth",
            "password_value": "Kp-Pass-1",
            "url": "https://mail.test",
            "description": None,
            "folder": "Root/Email",
            "totp_secret": "JBSWY3DPEHPK3PXP",
        },
        "Router": {
            "username": "admin",
            "password_value": "Kp-Pass-2 with spaces ",
            "url": "http://192.168.1.1",
            "description": 'Garage "B"',
            "folder": "Root",
        },
    },
    "protonpass.csv": {
        "Proton": {
            "username": "moth@proton.me",
            "password_value": "Pr-Pass-1",
            "url": "https://account.proton.me",
            "totp_secret": "JBSWY3DPEHPK3PXP",
            "folder": None,
        },
        "Forum": {
            "username": "mothman",
            "password_value": "Pr-Pass-2",
            "description": "hello",
        },
    },
}


@pytest.mark.parametrize("export", sorted(THIRD_PARTY_EXPORTS))
async def test_supported_third_party_exports_import(
    client: httpx.AsyncClient, vault: Headers, export: str
) -> None:
    expected = THIRD_PARTY_EXPORTS[export]
    resp = await _import_csv(client, vault, (CSV_DIR / export).read_bytes())

    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == len(expected)
    by_name = {p["password_name"]: p for p in await _listing(client, vault)}
    for name, fields in expected.items():
        got = by_name[name]
        assert got["kind"] == "login"
        for field, value in fields.items():
            assert got[field] == value, (name, field)


async def test_csv_with_old_mac_line_endings_imports(
    client: httpx.AsyncClient, vault: Headers
) -> None:
    resp = await _import_csv(client, vault, b"name,password\rcr-only,cr-Pass-1\r")
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 1
