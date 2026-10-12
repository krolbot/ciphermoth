from collections.abc import Awaitable, Callable

import httpx
import pytest

from helpers import create_encrypted_zip
from main import app
from settings import get_api_settings
from tests.support import (
    MASTER_PASSWORD,
    NEW_MASTER_PASSWORD,
    Headers,
    auth,
    bump_patch,
    control_files,
    create_legacy_vault,
    create_vault,
    db_execute,
    db_snapshot,
    entry,
    forged_keys,
    forged_tokens,
    key_auth,
    legacy_unlock,
    unlock,
    update_control_dir,
)

Spec = Callable[[httpx.AsyncClient, Headers, dict], Awaitable[httpx.Response]]

PUBLIC_ROUTES = {
    ("GET", "/api/master_password/status"),
    ("POST", "/api/master_password/check"),
    ("POST", "/api/master_password/unlock"),
    ("POST", "/api/master_password/lock"),
    ("POST", "/api/master_password/create"),
    ("GET", "/api/meta"),
    ("GET", "/api/updates/apply/status"),
}

SETTINGS_BODY = {
    "inactivity_ms": 300_000,
    "warn_before_ms": 30_000,
    "hidden_ms": 120_000,
    "debounce_ms": 500,
    "clipboard_clear_ms": 15_000,
    "update_check_enabled": False,
}

CSV_BODY = b"name,username,password,url\ncsv-entry,someone,csv-Pass-1,https://x.test\n"


def _alpha() -> dict:
    return entry("alpha", username="moth@example.com")


PROTECTED_ROUTES: dict[tuple[str, str], Spec] = {
    ("GET", "/api/master_password/session"): lambda c, h, x: c.get(
        "/master_password/session", headers=h
    ),
    ("GET", "/api/passwords"): lambda c, h, x: c.get("/passwords", headers=h),
    ("GET", "/api/passwords/trash"): lambda c, h, x: c.get(
        "/passwords/trash", headers=h
    ),
    ("GET", "/api/passwords/{password_name}"): lambda c, h, x: c.get(
        "/passwords/alpha", headers=h
    ),
    ("POST", "/api/passwords/create"): lambda c, h, x: c.post(
        "/passwords/create", json=entry("delta"), headers=h
    ),
    ("PATCH", "/api/passwords/update"): lambda c, h, x: c.patch(
        "/passwords/update",
        json={"password": _alpha(), "new_password": {**_alpha(), "url": "x.test"}},
        headers=h,
    ),
    ("PATCH", "/api/passwords/{password_name}/favorite"): lambda c, h, x: c.patch(
        "/passwords/alpha/favorite", json={"favorite": True}, headers=h
    ),
    ("DELETE", "/api/passwords/{password_name}"): lambda c, h, x: c.delete(
        "/passwords/alpha", headers=h
    ),
    ("POST", "/api/passwords/{password_name}/restore"): lambda c, h, x: c.post(
        "/passwords/beta/restore", headers=h
    ),
    ("DELETE", "/api/passwords/{password_name}/purge"): lambda c, h, x: c.delete(
        "/passwords/beta/purge", headers=h
    ),
    ("GET", "/api/passwords/{password_name}/attachments"): lambda c, h, x: c.get(
        "/passwords/alpha/attachments", headers=h
    ),
    ("POST", "/api/passwords/{password_name}/attachments"): lambda c, h, x: c.post(
        "/passwords/alpha/attachments",
        files={"file": ("new.bin", b"\x00\x01payload", "application/octet-stream")},
        headers=h,
    ),
    (
        "GET",
        "/api/passwords/{password_name}/attachments/{attachment_id}",
    ): lambda c, h, x: c.get(
        f"/passwords/alpha/attachments/{x['attachment_id']}", headers=h
    ),
    (
        "DELETE",
        "/api/passwords/{password_name}/attachments/{attachment_id}",
    ): lambda c, h, x: c.delete(
        f"/passwords/alpha/attachments/{x['attachment_id']}", headers=h
    ),
    ("POST", "/api/passwords/import"): lambda c, h, x: c.post(
        "/passwords/import",
        data={"master_password": MASTER_PASSWORD, "on_conflict": "overwrite"},
        files={"file": ("backup.zip", x["backup_zip"], "application/zip")},
        headers=h,
    ),
    ("POST", "/api/passwords/import/csv"): lambda c, h, x: c.post(
        "/passwords/import/csv",
        data={"on_conflict": "overwrite"},
        files={"file": ("export.csv", CSV_BODY, "text/csv")},
        headers=h,
    ),
    ("POST", "/api/passwords/backup"): lambda c, h, x: c.post(
        "/passwords/backup", json={"master_password": MASTER_PASSWORD}, headers=h
    ),
    ("GET", "/api/settings"): lambda c, h, x: c.get("/settings", headers=h),
    ("PATCH", "/api/settings"): lambda c, h, x: c.patch(
        "/settings", json=SETTINGS_BODY, headers=h
    ),
    ("POST", "/api/updates/apply"): lambda c, h, x: c.post(
        "/updates/apply",
        json={"target": bump_patch(get_api_settings().version)},
        headers=h,
    ),
    ("PATCH", "/api/master_password/update"): lambda c, h, x: c.patch(
        "/master_password/update",
        json={
            "master_password": MASTER_PASSWORD,
            "new_master_password": NEW_MASTER_PASSWORD,
        },
        headers=h,
    ),
}

ROUTE_IDS = [f"{method} {path}" for method, path in PROTECTED_ROUTES]


async def seed(client: httpx.AsyncClient, headers: Headers) -> dict:
    for item in (
        _alpha(),
        entry("beta"),
        entry("gamma", "note body\n", kind="note"),
    ):
        resp = await client.post("/passwords/create", json=item, headers=headers)
        assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/passwords/alpha/attachments",
        files={"file": ("doc.bin", b"\x00\xffbinary", "application/octet-stream")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    attachment_id = resp.json()["id"]
    resp = await client.delete("/passwords/beta", headers=headers)
    assert resp.status_code == 200, resp.text
    await client.get("/settings", headers=headers)
    (update_control_dir() / "updater.ready").touch()
    backup_zip = create_encrypted_zip(
        [{"name": "from-backup", "value": "restored-Value-1"}], MASTER_PASSWORD
    )
    return {"attachment_id": attachment_id, "backup_zip": backup_zip}


def _expected_rejection(headers: Headers) -> tuple[int, str]:
    names = {name.lower() for name, _ in headers}
    if b"x-ciphermoth-key-derivation" in names and b"x-ciphermoth-session" not in names:
        return 403, "invalid_key"
    return 401, "invalid_session"


async def _assert_rejected_without_side_effects(
    client: httpx.AsyncClient,
    spec: Spec,
    ctx: dict,
    credentials: dict[str, Headers],
    *,
    expect_code: bool = True,
) -> None:
    before = await db_snapshot()
    files_before = control_files()
    for label, headers in credentials.items():
        resp = await spec(client, headers, ctx)
        status, code = _expected_rejection(headers)
        if expect_code:
            assert resp.status_code == status, (
                f"{label}: {resp.status_code} {resp.text}"
            )
            assert resp.json().get("code") == code, label
        else:
            assert resp.status_code in (401, 403), f"{label}: {resp.text}"
        assert await db_snapshot() == before, f"{label} changed the database"
        assert control_files() == files_before, f"{label} wrote an update request"


def _as_key_headers(keys: dict[str, str | bytes | None]) -> dict[str, Headers]:
    return {label: key_auth(key) for label, key in keys.items()}


def test_every_api_route_is_classified() -> None:
    routes = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api")
        for method in operations
    }
    assert routes == PUBLIC_ROUTES | set(PROTECTED_ROUTES)


@pytest.mark.parametrize("route", list(PROTECTED_ROUTES), ids=ROUTE_IDS)
async def test_forged_session_tokens_are_rejected(
    client: httpx.AsyncClient, route: tuple[str, str]
) -> None:
    token = await create_vault(client)
    ctx = await seed(client, auth(token))
    spec = PROTECTED_ROUTES[route]
    key = await legacy_unlock(client)

    await _assert_rejected_without_side_effects(
        client, spec, ctx, await forged_tokens(client, token, key)
    )

    resp = await spec(client, auth(token), ctx)
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("route", list(PROTECTED_ROUTES), ids=ROUTE_IDS)
async def test_forged_keys_are_rejected(
    client: httpx.AsyncClient, route: tuple[str, str]
) -> None:
    key = await create_legacy_vault(client)
    ctx = await seed(client, key_auth(key))
    spec = PROTECTED_ROUTES[route]

    await _assert_rejected_without_side_effects(
        client, spec, ctx, _as_key_headers(forged_keys(key))
    )

    resp = await spec(client, key_auth(key), ctx)
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("route", list(PROTECTED_ROUTES), ids=ROUTE_IDS)
async def test_sessions_and_keys_from_before_a_rotation_are_rejected(
    client: httpx.AsyncClient, route: tuple[str, str]
) -> None:
    token = await create_vault(client)
    ctx = await seed(client, auth(token))
    other = await unlock(client)
    old_key = await legacy_unlock(client)
    resp = await client.patch(
        "/master_password/update",
        json={
            "master_password": MASTER_PASSWORD,
            "new_master_password": NEW_MASTER_PASSWORD,
        },
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text

    spec = PROTECTED_ROUTES[route]
    await _assert_rejected_without_side_effects(
        client,
        spec,
        ctx,
        {
            "rotating session": auth(token),
            "other session": auth(other),
            "stale key": key_auth(old_key),
        },
    )


@pytest.mark.parametrize("route", list(PROTECTED_ROUTES), ids=ROUTE_IDS)
async def test_legacy_vault_fails_closed_until_unlocked(
    client: httpx.AsyncClient, route: tuple[str, str]
) -> None:
    key = await create_legacy_vault(client)
    token = await unlock(client)
    ctx = await seed(client, auth(token))
    await db_execute("UPDATE master_password SET key_check = NULL")
    spec = PROTECTED_ROUTES[route]

    await _assert_rejected_without_side_effects(
        client,
        spec,
        ctx,
        {"correct-but-unverified": key_auth(key), "open session": auth(token)},
    )

    assert await legacy_unlock(client) == key
    resp = await client.get("/passwords", headers=key_auth(key))
    assert resp.status_code == 200, resp.text
    resp = await spec(client, auth(token), ctx)
    assert resp.status_code == 401, resp.text
    resp = await spec(client, auth(await unlock(client)), ctx)
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("route", list(PROTECTED_ROUTES), ids=ROUTE_IDS)
async def test_uninitialized_vault_rejects_everything(
    client: httpx.AsyncClient, route: tuple[str, str]
) -> None:
    (update_control_dir() / "updater.ready").touch()
    ctx = {"attachment_id": 1, "backup_zip": b"PK"}
    credentials = {
        **_as_key_headers(forged_keys("A" * 43 + "=")),
        "random token": auth("A" * 43),
    }
    await _assert_rejected_without_side_effects(
        client, PROTECTED_ROUTES[route], ctx, credentials, expect_code=False
    )
