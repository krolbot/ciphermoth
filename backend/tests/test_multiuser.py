import base64
import io
import json

import httpx
import pytest
import pyzipper

from main import app
from tests.support import auth, entry

ADMIN_PASSWORD = "Moth-Admin-Password-2026!"
MEMBER_PASSWORD = "Moth-Member-Password-2026!"


async def bootstrap(
    client: httpx.AsyncClient,
) -> tuple[dict, list[tuple[bytes, bytes]]]:
    response = await client.post(
        "/auth/bootstrap",
        json={"username": "owner", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body["user"], auth(body["session_token"])


async def login(
    client: httpx.AsyncClient, username: str, password: str
) -> tuple[dict, list[tuple[bytes, bytes]]]:
    response = await client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    return body["user"], auth(body["session_token"])


async def mcp_post(
    client: httpx.AsyncClient,
    token: str,
    payload: dict[str, object],
    protocol: str | None = None,
) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if protocol:
        headers["MCP-Protocol-Version"] = protocol
    return await client.post("http://testserver/mcp", headers=headers, json=payload)


@pytest.mark.asyncio
async def test_users_and_entry_acl_are_deny_by_default(
    client: httpx.AsyncClient,
) -> None:
    owner, owner_headers = await bootstrap(client)
    created = await client.post(
        "/passwords/create", json=entry("shared", "original"), headers=owner_headers
    )
    assert created.status_code == 200, created.text
    [owned] = (await client.get("/passwords", headers=owner_headers)).json()
    [owned_access] = (
        await client.get("/passwords/access", headers=owner_headers)
    ).json()
    assert owned_access["entry_id"] == owned["id"]
    assert owned_access["owner_id"] == owner["id"]
    assert owned_access["owner_username"] == "owner"
    assert owned_access["access"] == "owner"

    response = await client.post(
        "/users",
        json={
            "username": "member",
            "role": "member",
            "temporary_password": MEMBER_PASSWORD,
        },
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text
    member = response.json()
    _, member_headers = await login(client, "member", MEMBER_PASSWORD)
    assert (await client.get("/passwords", headers=member_headers)).json() == []
    assert (await client.get("/passwords", headers=auth(None))).status_code == 401

    granted = await client.put(
        f"/passwords/{owned['id']}/shares/{member['id']}",
        json={"permission": "read"},
        headers=owner_headers,
    )
    assert granted.status_code == 200, granted.text
    [shared] = (await client.get("/passwords", headers=member_headers)).json()
    [shared_access] = (
        await client.get("/passwords/access", headers=member_headers)
    ).json()
    assert shared_access["entry_id"] == shared["id"]
    assert shared_access["access"] == "read"
    assert shared["password_value"] == "original"

    denied = await client.patch(
        "/passwords/update",
        json={
            "password": {"password_name": "shared"},
            "new_password": entry("shared", "changed"),
        },
        headers=member_headers,
    )
    assert denied.status_code == 403

    upgraded = await client.put(
        f"/passwords/{owned['id']}/shares/{member['id']}",
        json={"permission": "write"},
        headers=owner_headers,
    )
    assert upgraded.status_code == 200, upgraded.text
    changed = await client.patch(
        "/passwords/update",
        json={
            "password": {"password_name": "shared"},
            "new_password": entry("shared", "changed"),
        },
        headers=member_headers,
    )
    assert changed.status_code == 200, changed.text
    assert (await client.get("/passwords/shared", headers=owner_headers)).json()[
        "password_value"
    ] == "changed"


@pytest.mark.asyncio
async def test_admin_lifecycle_revokes_memory_sessions(
    client: httpx.AsyncClient,
) -> None:
    _owner, owner_headers = await bootstrap(client)
    created = await client.post(
        "/users",
        json={
            "username": "member",
            "role": "member",
            "temporary_password": MEMBER_PASSWORD,
        },
        headers=owner_headers,
    )
    member = created.json()
    _, member_headers = await login(client, "member", MEMBER_PASSWORD)
    assert (await client.get("/auth/me", headers=member_headers)).status_code == 200

    revoked = await client.post(
        f"/users/{member['id']}/sessions/revoke", headers=owner_headers
    )
    assert revoked.status_code == 200, revoked.text
    assert (await client.get("/auth/me", headers=member_headers)).status_code == 401

    _, member_headers = await login(client, "member", MEMBER_PASSWORD)
    disabled = await client.patch(
        f"/users/{member['id']}", json={"active": False}, headers=owner_headers
    )
    assert disabled.status_code == 200, disabled.text
    assert (await client.get("/auth/me", headers=member_headers)).status_code == 401
    refused = await client.post(
        "/auth/login", json={"username": "member", "password": MEMBER_PASSWORD}
    )
    assert refused.status_code == 200
    assert refused.json()["valid"] is False


@pytest.mark.asyncio
async def test_primary_vault_owner_cannot_be_deleted(
    client: httpx.AsyncClient,
) -> None:
    owner, owner_headers = await bootstrap(client)
    created = await client.post(
        "/users",
        json={
            "username": "second-admin",
            "role": "admin",
            "temporary_password": MEMBER_PASSWORD,
        },
        headers=owner_headers,
    )
    assert created.status_code == 200, created.text
    _, second_headers = await login(client, "second-admin", MEMBER_PASSWORD)

    deleted = await client.delete(f"/users/{owner['id']}", headers=second_headers)
    assert deleted.status_code == 403
    assert "primary vault owner" in deleted.json()["detail"].lower()
    assert (await client.get("/auth/me", headers=owner_headers)).status_code == 200


async def _mcp_service_acl_flow(client: httpx.AsyncClient) -> None:
    _owner, owner_headers = await bootstrap(client)
    await client.post(
        "/passwords/create", json=entry("shared", "secret"), headers=owner_headers
    )
    [owned] = (await client.get("/passwords", headers=owner_headers)).json()
    service_response = await client.post(
        "/users",
        json={"username": "assistant", "role": "service"},
        headers=owner_headers,
    )
    assert service_response.status_code == 200, service_response.text
    service = service_response.json()
    token = service.pop("service_token")
    assert token
    grant = await client.put(
        f"/passwords/{owned['id']}/shares/{service['id']}",
        json={"permission": "read"},
        headers=owner_headers,
    )
    assert grant.status_code == 200, grant.text

    initialized = await mcp_post(
        client,
        token,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        },
    )
    assert initialized.status_code == 200, initialized.text
    protocol = initialized.json()["result"]["protocolVersion"]
    listed = await mcp_post(
        client,
        token,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "list_entries", "arguments": {}},
        },
        protocol,
    )
    assert listed.status_code == 200, listed.text
    [listed_entry] = listed.json()["result"]["structuredContent"]["result"]
    assert listed_entry["id"] == owned["id"]
    assert listed_entry["access"] == "read"

    denied = await mcp_post(
        client,
        token,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "update_entry",
                "arguments": {
                    "entry_id": owned["id"],
                    "changes": {"password_value": "changed"},
                },
            },
        },
        protocol,
    )
    assert denied.json()["result"]["isError"] is True

    await client.patch(
        f"/users/{service['id']}", json={"active": False}, headers=owner_headers
    )
    revoked = await mcp_post(
        client,
        token,
        {"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        protocol,
    )
    assert revoked.status_code == 401


@pytest.mark.asyncio
async def test_mcp_service_uses_the_same_explicit_acl(
    client: httpx.AsyncClient,
) -> None:
    async with app.state.mcp_server.session_manager.run():
        await _mcp_service_acl_flow(client)


@pytest.mark.asyncio
async def test_legacy_migration_backup_restores_history_trash_attachments_and_grants(
    client: httpx.AsyncClient,
) -> None:
    _owner, owner_headers = await bootstrap(client)
    service_response = await client.post(
        "/users",
        json={"username": "assistant", "role": "service"},
        headers=owner_headers,
    )
    assert service_response.status_code == 200, service_response.text
    service = service_response.json()
    other_response = await client.post(
        "/users",
        json={
            "username": "other",
            "role": "member",
            "temporary_password": MEMBER_PASSWORD,
        },
        headers=owner_headers,
    )
    assert other_response.status_code == 200, other_response.text
    _, other_headers = await login(client, "other", MEMBER_PASSWORD)
    collision = await client.post(
        "/passwords/create",
        json=entry("migrated", "belongs-to-other"),
        headers=other_headers,
    )
    assert collision.status_code == 200, collision.text

    attachment = b"migration attachment"
    stamp = "2026-10-20T12:00:00Z"
    row = {
        "legacy_id": 41,
        "owner_username": "owner",
        "access": "owner",
        "created": stamp,
        "updated": stamp,
        "deleted": None,
        "name": "migrated",
        "kind": "login",
        "username": "legacy-user",
        "value": "legacy-value",
        "url": "https://example.test",
        "totp_secret": None,
        "description": "from PostgreSQL",
        "tags": ["legacy"],
        "custom_fields": [{"label": "PIN", "value": "1234", "hidden": True}],
        "folder": "Migration",
        "favorite": True,
        "password_history": [{"value": "older-value", "changed_at": stamp}],
        "shares": [{"username": "assistant", "role": "service", "permission": "write"}],
        "attachments": [
            {
                "filename": "proof.txt",
                "content_type": "text/plain",
                "created": stamp,
                "data": base64.urlsafe_b64encode(attachment).decode().rstrip("="),
            }
        ],
    }
    trashed = {
        **row,
        "legacy_id": 42,
        "name": "migrated-trash",
        "deleted": "2026-10-21T12:00:00Z",
        "shares": [],
        "attachments": [],
    }
    payload = json.dumps(
        {"migration_version": 1, "exported_at": stamp, "passwords": [row, trashed]}
    ).encode()
    archive = io.BytesIO()
    with pyzipper.AESZipFile(
        archive,
        "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as backup:
        backup.setpassword(ADMIN_PASSWORD.encode())
        backup.setencryption(pyzipper.WZ_AES, nbits=256)
        backup.writestr("ciphermoth_backup.json", payload)

    wrong_archive = io.BytesIO()
    wrong_payload = json.dumps(
        {
            "migration_version": 1,
            "exported_at": stamp,
            "passwords": [{**row, "owner_username": "other"}],
        }
    ).encode()
    with pyzipper.AESZipFile(
        wrong_archive,
        "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as backup:
        backup.setpassword(ADMIN_PASSWORD.encode())
        backup.setencryption(pyzipper.WZ_AES, nbits=256)
        backup.writestr("ciphermoth_backup.json", wrong_payload)
    wrong_owner = await client.post(
        "/passwords/import",
        files={"file": ("migration.zip", wrong_archive.getvalue(), "application/zip")},
        data={"master_password": ADMIN_PASSWORD, "on_conflict": "skip"},
        headers=owner_headers,
    )
    assert wrong_owner.status_code == 403, wrong_owner.text
    assert (await client.get("/passwords", headers=owner_headers)).json() == []

    imported = await client.post(
        "/passwords/import",
        files={"file": ("migration.zip", archive.getvalue(), "application/zip")},
        data={"master_password": ADMIN_PASSWORD, "on_conflict": "skip"},
        headers=owner_headers,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json() == {
        "imported": 1,
        "skipped": 0,
        "overwritten": 0,
        "total": 2,
        "ignored": 0,
        "ignored_rows": [],
        "renamed": 1,
        "renamed_rows": [
            {
                "where": "entry 1",
                "name": "migrated",
                "reason": (
                    "imported as 'migrated (2)' because that active name is already "
                    "in use"
                ),
            }
        ],
        "trashed": 1,
        "attachments": 1,
        "grants_restored": 1,
        "settings_restored": False,
    }

    [active] = (await client.get("/passwords", headers=owner_headers)).json()
    assert active["password_name"] == "migrated (2)"
    assert active["password_history"] == [
        {"value": "older-value", "changed_at": "2026-10-20T12:00:00Z"}
    ]
    assert active["attachment_count"] == 1
    [share] = (
        await client.get(f"/passwords/{active['id']}/shares", headers=owner_headers)
    ).json()
    assert share["user_id"] == service["id"]
    assert share["permission"] == "write"
    [trash] = (await client.get("/passwords/trash", headers=owner_headers)).json()
    assert trash["password_name"] == "migrated-trash"
    [described] = (
        await client.get("/passwords/migrated (2)/attachments", headers=owner_headers)
    ).json()
    downloaded = await client.get(
        f"/passwords/migrated (2)/attachments/{described['id']}", headers=owner_headers
    )
    assert downloaded.content == attachment


@pytest.mark.asyncio
async def test_backup_import_cannot_overwrite_another_owners_entry(
    client: httpx.AsyncClient,
) -> None:
    _owner, owner_headers = await bootstrap(client)
    created_entry = await client.post(
        "/passwords/create",
        json=entry("protected", "owner-value"),
        headers=owner_headers,
    )
    assert created_entry.status_code == 200, created_entry.text
    backup = await client.post(
        "/passwords/backup",
        json={"master_password": ADMIN_PASSWORD},
        headers=owner_headers,
    )
    assert backup.status_code == 200, backup.text

    created_user = await client.post(
        "/users",
        json={
            "username": "member",
            "role": "member",
            "temporary_password": MEMBER_PASSWORD,
        },
        headers=owner_headers,
    )
    assert created_user.status_code == 200, created_user.text
    _, member_headers = await login(client, "member", MEMBER_PASSWORD)
    imported = await client.post(
        "/passwords/import",
        files={"file": ("backup.cmbackup", backup.content, "application/octet-stream")},
        data={"master_password": ADMIN_PASSWORD, "on_conflict": "overwrite"},
        headers=member_headers,
    )
    assert imported.status_code == 403, imported.text

    [owned] = (await client.get("/passwords", headers=owner_headers)).json()
    assert owned["password_name"] == "protected"
    assert owned["password_value"] == "owner-value"
    assert (await client.get("/passwords", headers=member_headers)).json() == []


@pytest.mark.asyncio
async def test_csv_import_renames_instead_of_overwriting_a_shared_entry(
    client: httpx.AsyncClient,
) -> None:
    _owner, owner_headers = await bootstrap(client)
    assert (
        await client.post(
            "/passwords/create",
            json=entry("shared-name", "owner-value"),
            headers=owner_headers,
        )
    ).status_code == 200
    [owned] = (await client.get("/passwords", headers=owner_headers)).json()
    created_user = await client.post(
        "/users",
        json={
            "username": "member",
            "role": "member",
            "temporary_password": MEMBER_PASSWORD,
        },
        headers=owner_headers,
    )
    member = created_user.json()
    _, member_headers = await login(client, "member", MEMBER_PASSWORD)
    grant = await client.put(
        f"/passwords/{owned['id']}/shares/{member['id']}",
        json={"permission": "read"},
        headers=owner_headers,
    )
    assert grant.status_code == 200, grant.text

    imported = await client.post(
        "/passwords/import/csv",
        files={
            "file": (
                "entries.csv",
                b"name,password\nshared-name,member-value\n",
                "text/csv",
            )
        },
        data={"on_conflict": "overwrite"},
        headers=member_headers,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["renamed"] == 1

    owner_entry = await client.get("/passwords/shared-name", headers=owner_headers)
    assert owner_entry.json()["password_value"] == "owner-value"
    member_entries = (await client.get("/passwords", headers=member_headers)).json()
    assert {item["password_name"] for item in member_entries} == {
        "shared-name",
        "shared-name (2)",
    }


@pytest.mark.asyncio
async def test_member_backup_import_cannot_restore_global_settings(
    client: httpx.AsyncClient,
) -> None:
    _owner, owner_headers = await bootstrap(client)
    before = {
        "inactivity_ms": 300_000,
        "warn_before_ms": 30_000,
        "hidden_ms": 120_000,
        "debounce_ms": 500,
        "clipboard_clear_ms": 15_000,
        "update_check_enabled": False,
    }
    assert (
        await client.patch("/settings", json=before, headers=owner_headers)
    ).status_code == 200
    backup = await client.post(
        "/passwords/backup",
        json={"master_password": ADMIN_PASSWORD},
        headers=owner_headers,
    )
    after = {**before, "inactivity_ms": 600_000, "update_check_enabled": True}
    assert (
        await client.patch("/settings", json=after, headers=owner_headers)
    ).status_code == 200

    created = await client.post(
        "/users",
        json={
            "username": "member",
            "role": "member",
            "temporary_password": MEMBER_PASSWORD,
        },
        headers=owner_headers,
    )
    assert created.status_code == 200, created.text
    _, member_headers = await login(client, "member", MEMBER_PASSWORD)
    imported = await client.post(
        "/passwords/import",
        files={"file": ("backup.cmbackup", backup.content, "application/octet-stream")},
        data={"master_password": ADMIN_PASSWORD, "on_conflict": "skip"},
        headers=member_headers,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["settings_restored"] is False
    assert (await client.get("/settings", headers=owner_headers)).json() == after
