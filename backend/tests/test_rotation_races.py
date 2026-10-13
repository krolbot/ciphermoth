import asyncio

import httpx
import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

import crud.master_password
import crud.password
from helpers import create_encrypted_zip
from main import app
from tests.support import (
    MASTER_PASSWORD,
    NEW_MASTER_PASSWORD,
    auth,
    create_vault,
    db_execute,
    db_snapshot,
    entry,
    stored_vault_key,
    unlock,
)

ROTATE = {
    "master_password": MASTER_PASSWORD,
    "new_master_password": NEW_MASTER_PASSWORD,
}
OTHER_PASSWORD = "Moth-Other-Rotation-2028#"
GATE_SECONDS = 10


class FirstDerivationWaits:
    """Hold the first Argon2id derivation of the test until released (at most
    GATE_SECONDS, so a failing test cannot leave a request holding the vault),
    so a request can be stopped between its first transaction and its last."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
        original = crud.master_password.derive_key

        async def derive_key(salt: bytes, password: str) -> bytes:
            self.calls += 1
            if self.calls == 1:
                self.entered.set()
                await asyncio.wait_for(self.release.wait(), GATE_SECONDS)
            return await original(salt, password)

        monkeypatch.setattr(crud.master_password, "derive_key", derive_key)


def _decrypts(key: str, tokens: list[bytes]) -> bool:
    try:
        for token in tokens:
            Fernet(key).decrypt(token)
    except InvalidToken:
        return False
    return True


async def _tokens() -> list[bytes]:
    return [row[0] for row in await db_execute("SELECT password_value FROM passwords")]


async def _names(client: httpx.AsyncClient, password: str) -> list[str]:
    resp = await client.get("/passwords", headers=auth(await unlock(client, password)))
    assert resp.status_code == 200, resp.text
    return [item["password_name"] for item in resp.json()]


async def test_an_unlock_overtaken_by_a_rotation_opens_no_session(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await create_vault(client)
    await client.post("/passwords/create", json=entry("kept"), headers=auth(token))
    waits = FirstDerivationWaits(monkeypatch)

    stale = asyncio.create_task(
        client.post(
            "/master_password/unlock", json={"master_password": MASTER_PASSWORD}
        )
    )
    await waits.entered.wait()
    resp = await client.patch(
        "/master_password/update", json=ROTATE, headers=auth(token)
    )
    assert resp.status_code == 200, resp.text
    waits.release.set()
    resp = await stale

    assert resp.status_code == 200, resp.text
    assert resp.json()["valid"] is False
    assert resp.json()["session_token"] is None
    assert len(app.state.vault_sessions) == 0


@pytest.mark.parametrize("entries", [0, 3], ids=["empty", "populated"])
async def test_of_two_concurrent_rotations_only_the_first_applies(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, entries: int
) -> None:
    token = await create_vault(client)
    for i in range(entries):
        await client.post("/passwords/create", json=entry(f"e{i}"), headers=auth(token))
    other = await unlock(client)
    waits = FirstDerivationWaits(monkeypatch)

    late = asyncio.create_task(
        client.patch(
            "/master_password/update",
            json={
                "master_password": MASTER_PASSWORD,
                "new_master_password": OTHER_PASSWORD,
            },
            headers=auth(other),
        )
    )
    await waits.entered.wait()
    first = await client.patch(
        "/master_password/update", json=ROTATE, headers=auth(token)
    )
    waits.release.set()
    late_resp = await late

    assert first.status_code == 200, first.text
    assert late_resp.status_code == 401, late_resp.text
    assert late_resp.json()["code"] == "invalid_session"
    assert _decrypts(await stored_vault_key(NEW_MASTER_PASSWORD), await _tokens())
    resp = await client.post(
        "/master_password/unlock", json={"master_password": OTHER_PASSWORD}
    )
    assert resp.json()["valid"] is False
    assert await _names(client, NEW_MASTER_PASSWORD) == [
        f"e{i}" for i in range(entries)
    ]


async def test_writes_go_on_while_a_rotation_derives_its_keys(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await create_vault(client)
    writer = await unlock(client)
    waits = FirstDerivationWaits(monkeypatch)

    rotation = asyncio.create_task(
        client.patch("/master_password/update", json=ROTATE, headers=auth(token))
    )
    await waits.entered.wait()
    try:
        during = await asyncio.wait_for(
            client.post(
                "/passwords/create",
                json=entry("during", "written-During-1"),
                headers=auth(writer),
            ),
            timeout=5,
        )
    finally:
        waits.release.set()
        rotated = await rotation

    assert during.status_code == 200, during.text
    assert rotated.status_code == 200
    resp = await client.get(
        "/passwords/during", headers=auth(await unlock(client, NEW_MASTER_PASSWORD))
    )
    assert resp.json()["password_value"] == "written-During-1"
    assert _decrypts(await stored_vault_key(NEW_MASTER_PASSWORD), await _tokens())


async def test_a_rotation_whose_final_commit_fails_changes_nothing(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await create_vault(client)
    await client.post("/passwords/create", json=entry("kept"), headers=auth(token))
    before = await db_snapshot()
    original = AsyncSession.commit
    calls = 0

    async def commit(self: AsyncSession) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("the final commit failed")
        await original(self)

    monkeypatch.setattr(AsyncSession, "commit", commit)
    resp = await client.patch(
        "/master_password/update", json=ROTATE, headers=auth(token)
    )
    monkeypatch.undo()

    assert calls == 2
    assert resp.status_code == 500
    assert await db_snapshot() == before
    assert (await client.get("/passwords", headers=auth(token))).status_code == 200
    assert await _names(client, MASTER_PASSWORD) == ["kept"]


class FirstPasswordCheckWaits:
    """Hold the first master password check of a backup or an import."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
        original = crud.password.password_matches

        async def password_matches(password: str, hashed: str) -> bool:
            self.calls += 1
            if self.calls == 1:
                self.entered.set()
                await asyncio.wait_for(self.release.wait(), GATE_SECONDS)
            return await original(password, hashed)

        monkeypatch.setattr(crud.password, "password_matches", password_matches)


async def test_writes_go_on_while_a_backup_checks_the_master_password(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await create_vault(client)
    waits = FirstPasswordCheckWaits(monkeypatch)

    backup = asyncio.create_task(
        client.post(
            "/passwords/backup",
            json={"master_password": MASTER_PASSWORD},
            headers=auth(token),
        )
    )
    await waits.entered.wait()
    try:
        during = await asyncio.wait_for(
            client.post("/passwords/create", json=entry("during"), headers=auth(token)),
            timeout=5,
        )
    finally:
        waits.release.set()
        backed_up = await backup

    assert during.status_code == 200, during.text
    assert backed_up.status_code == 200


async def test_an_import_overtaken_by_a_rotation_writes_nothing(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await create_vault(client)
    await client.post("/passwords/create", json=entry("kept"), headers=auth(token))
    importer = await unlock(client)
    waits = FirstPasswordCheckWaits(monkeypatch)

    imported = asyncio.create_task(
        client.post(
            "/passwords/import",
            data={"master_password": MASTER_PASSWORD, "on_conflict": "skip"},
            files={
                "file": (
                    "b.zip",
                    create_encrypted_zip(
                        [{"name": "late", "value": "late-Value-1"}], MASTER_PASSWORD
                    ),
                    "application/zip",
                )
            },
            headers=auth(importer),
        )
    )
    await waits.entered.wait()
    rotated = await client.patch(
        "/master_password/update", json=ROTATE, headers=auth(token)
    )
    waits.release.set()
    resp = await imported

    assert rotated.status_code == 200, rotated.text
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "invalid_key"
    assert _decrypts(await stored_vault_key(NEW_MASTER_PASSWORD), await _tokens())
    assert await _names(client, NEW_MASTER_PASSWORD) == ["kept"]
