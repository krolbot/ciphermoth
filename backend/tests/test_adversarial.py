import asyncio
import secrets

import httpx
import pytest
from cryptography.fernet import Fernet, InvalidToken

from crud.master_password import MasterPasswordCRUD
from helpers import encrypt
from models import SETTINGS_DEFAULTS
from tests.support import (
    MASTER_PASSWORD,
    NEW_MASTER_PASSWORD,
    auth,
    create_vault,
    db_execute,
    db_snapshot,
    entry,
    retired_key_header,
    stored_vault_key,
    unlock,
)

ROTATE = {
    "master_password": MASTER_PASSWORD,
    "new_master_password": NEW_MASTER_PASSWORD,
}


def _all_decrypt(key: str, tokens: list[bytes]) -> bool:
    try:
        for token in tokens:
            Fernet(key).decrypt(token)
    except InvalidToken:
        return False
    return True


async def _value_tokens() -> list[bytes]:
    return [row[0] for row in await db_execute("SELECT password_value FROM passwords")]


async def test_method_and_path_variants_stay_protected(
    client: httpx.AsyncClient,
) -> None:
    token = await create_vault(client)
    await client.post("/passwords/create", json=entry("alpha"), headers=auth(token))
    for forged, refused in (
        (auth(secrets.token_urlsafe(32)), 401),
        (retired_key_header(await stored_vault_key()), 403),
    ):
        for path in ("/passwords", "/passwords/alpha", "/settings"):
            resp = await client.head(path, headers=forged)
            assert resp.status_code in (refused, 405)
            assert resp.content == b""
        resp = await client.get("/passwords/", headers=forged, follow_redirects=True)
        assert resp.status_code == refused
        resp = await client.options("/passwords/alpha", headers=forged)
        assert resp.status_code in (refused, 405)
        assert "s3cret" not in resp.text


async def test_duplicate_or_misspelled_key_headers_do_not_help(
    client: httpx.AsyncClient,
) -> None:
    await create_vault(client)
    key = await stored_vault_key()
    forged = Fernet.generate_key()
    name = b"x-ciphermoth-key-derivation"
    variants = [
        key.encode() + b"\x00",
        key.encode() + b"!!",
        key[:20].encode() + b"." + key[20:].encode(),
        key.rstrip("=").encode(),
        b" " + forged,
    ]
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    last = alphabet.index(key[42])
    for low_bits in range(1, 4):
        variants.append((key[:42] + alphabet[last ^ low_bits] + "=").encode())
    standard_alphabet = key.replace("-", "+").replace("_", "/")
    if standard_alphabet != key:
        variants.append(standard_alphabet.encode())
    attempts = [
        [(name, forged), (name, b"")],
        [(b"x_ciphermoth_key_derivation", key.encode())],
        [(b"X-CipherMoth-Key-Derivation", forged)],
        [(b"X-CipherMoth-Key-Derivation", key.encode())],
        [(name, key.encode())],
        *([(name, value)] for value in variants),
    ]
    for headers in attempts:
        resp = await client.patch(
            "/settings",
            json={
                "inactivity_ms": 60_000,
                "warn_before_ms": 10_000,
                "hidden_ms": 60_000,
                "debounce_ms": 100,
                "clipboard_clear_ms": 5_000,
                "update_check_enabled": False,
            },
            headers=headers,
        )
        assert resp.status_code in (401, 403), headers
    assert await db_execute("SELECT inactivity_ms FROM settings") == [
        (SETTINGS_DEFAULTS["inactivity_ms"],)
    ]


async def test_concurrent_rotations_with_the_same_key_apply_once(
    client: httpx.AsyncClient,
) -> None:
    token = await create_vault(client)
    await client.post("/passwords/create", json=entry("one"), headers=auth(token))

    first, second = await asyncio.gather(
        client.patch("/master_password/update", json=ROTATE, headers=auth(token)),
        client.patch("/master_password/update", json=ROTATE, headers=auth(token)),
    )

    assert sorted([first.status_code, second.status_code]) == [200, 401]
    await unlock(client, NEW_MASTER_PASSWORD)
    new_key = await stored_vault_key(NEW_MASTER_PASSWORD)
    assert _all_decrypt(new_key, await _value_tokens())


async def test_write_burst_racing_a_rotation_never_corrupts_or_deadlocks(
    client: httpx.AsyncClient,
) -> None:
    token = await create_vault(client)
    writes = [
        client.post("/passwords/create", json=entry(f"e{i}"), headers=auth(token))
        for i in range(20)
    ]
    rotation = client.patch("/master_password/update", json=ROTATE, headers=auth(token))

    responses = await asyncio.gather(*writes[:10], rotation, *writes[10:])

    statuses = [r.status_code for r in responses]
    assert 500 not in statuses, [r.text for r in responses if r.status_code == 500]
    assert responses[10].status_code == 200
    assert set(statuses) <= {200, 401}
    await unlock(client, NEW_MASTER_PASSWORD)
    new_key = await stored_vault_key(NEW_MASTER_PASSWORD)
    assert _all_decrypt(new_key, await _value_tokens())
    created = sum(1 for r in responses if r.status_code == 200) - 1
    assert len(await _value_tokens()) == created


async def test_vault_damaged_before_the_patch_can_be_recovered(
    client: httpx.AsyncClient,
) -> None:
    headers = auth(await create_vault(client))
    await client.post("/passwords/create", json=entry("good"), headers=headers)
    await db_execute(
        "INSERT INTO passwords (password_name, password_value) VALUES (:n, :v)",
        n="planted",
        v=encrypt(Fernet.generate_key(), b"attacker data"),
    )
    listing = await client.get("/passwords", headers=headers)
    assert listing.status_code == 400
    assert "planted" in listing.json()["detail"]
    before = await db_snapshot()
    rotation = await client.patch(
        "/master_password/update", json=ROTATE, headers=headers
    )
    assert rotation.status_code == 400
    assert await db_snapshot() == before

    assert (
        await client.delete("/passwords/planted", headers=headers)
    ).status_code == 200
    resp = await client.delete("/passwords/planted/purge", headers=headers)
    assert resp.status_code == 200

    listing = await client.get("/passwords", headers=headers)
    assert [p["password_name"] for p in listing.json()] == ["good"]
    rotation = await client.patch(
        "/master_password/update", json=ROTATE, headers=headers
    )
    assert rotation.status_code == 200


async def test_unauthenticated_bodies_are_bounded(client: httpx.AsyncClient) -> None:
    await create_vault(client)
    resp = await client.post(
        "/passwords/import/csv",
        content=b"x" * (13 * 1024 * 1024),
        headers={"content-type": "multipart/form-data; boundary=x"},
    )
    assert resp.status_code == 413


async def test_forged_credentials_never_wait_on_vault_locks(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await create_vault(client)
    real_key = await stored_vault_key()
    gate = asyncio.Event()
    original = MasterPasswordCRUD.update_master_password

    async def slow_rotation(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        await gate.wait()
        return result

    monkeypatch.setattr(MasterPasswordCRUD, "update_master_password", slow_rotation)
    rotation = asyncio.create_task(
        client.patch("/master_password/update", json=ROTATE, headers=auth(token))
    )
    await asyncio.sleep(1.5)
    try:
        for forged, refused in (
            (auth(secrets.token_urlsafe(32)), 401),
            (retired_key_header(real_key), 403),
            (retired_key_header(Fernet.generate_key()), 403),
        ):
            resp = await asyncio.wait_for(
                client.get("/passwords", headers=forged), timeout=3
            )
            assert resp.status_code == refused
    finally:
        gate.set()
        assert (await rotation).status_code == 200
