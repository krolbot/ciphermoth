import asyncio
import os
import random
import signal
import time
from pathlib import Path

import asyncpg
import httpx
import pytest

from crud.session import engine
from helpers import verify_master_password
from tests.integrity import VaultContents, assert_same_vault, raw_vault, read_vault
from tests.support import (
    MASTER_PASSWORD,
    NEW_MASTER_PASSWORD,
    ApiServer,
    admin_connection,
    api_server,
    db_execute,
)

KEY_HEADER = "x-ciphermoth-key-derivation"


async def _seed(base_url: str, entries: int = 40) -> str:
    async with httpx.AsyncClient(base_url=base_url, timeout=60) as http:
        resp = await http.post(
            "/master_password/create", json={"master_password": MASTER_PASSWORD}
        )
        key = resp.json()["key_derivation"]
        headers = {KEY_HEADER: key}
        for i in range(entries):
            resp = await http.post(
                "/passwords/create",
                json={
                    "password_name": f"entry-{i:03d}",
                    "password_value": f"value-{i}",
                    "url": f"https://site-{i}.test",
                    "tags": ["a", "b"],
                },
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
        resp = await http.post(
            "/passwords/entry-000/attachments",
            files={"file": ("a.bin", os.urandom(200_000), "application/octet-stream")},
            headers=headers,
        )
        assert resp.status_code == 200
        return key


async def _state() -> tuple[dict, list]:
    async with engine.connect() as conn:
        return await raw_vault(conn), await db_execute("SELECT * FROM settings")


async def _scan(key: str) -> VaultContents:
    async with engine.connect() as conn:
        return await read_vault(conn, key)


async def _wait_for_lock_wait(statement: str, timeout: float = 30) -> int:
    conn = await admin_connection()
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pid = await conn.fetchval(
                "SELECT pid FROM pg_stat_activity WHERE datname = current_database() "
                "AND wait_event_type = 'Lock' AND query LIKE $1",
                f"{statement}%",
            )
            if pid:
                return pid
            await asyncio.sleep(0.05)
    finally:
        await conn.close()
    raise AssertionError(f"no session blocked on {statement!r}")


async def _wait_until_gone(pid: int, timeout: float = 30) -> None:
    conn = await admin_connection()
    try:
        deadline = time.monotonic() + timeout
        while await conn.fetchval("SELECT 1 FROM pg_stat_activity WHERE pid = $1", pid):
            assert time.monotonic() < deadline, f"backend {pid} still running"
            await asyncio.sleep(0.05)
    finally:
        await conn.close()


def _kill(server: ApiServer) -> None:
    server.process.send_signal(signal.SIGKILL)
    server.process.wait(timeout=10)


async def _send_and_kill_when_blocked(
    server: ApiServer, blocker: asyncpg.Connection, send, statement: str
) -> None:
    request = asyncio.create_task(send())
    pid = await _wait_for_lock_wait(statement)
    _kill(server)
    await blocker.execute("ROLLBACK")
    await _wait_until_gone(pid)
    with pytest.raises(httpx.TransportError):
        await request


async def _lock_row(name: str) -> asyncpg.Connection:
    blocker = await admin_connection()
    await blocker.execute("BEGIN")
    await blocker.execute(
        "SELECT 1 FROM passwords WHERE password_name = $1 FOR UPDATE", name
    )
    return blocker


async def test_killing_the_server_mid_rotation_leaves_the_old_vault(
    tmp_path: Path,
) -> None:
    with api_server(tmp_path / "server.log") as server:
        key = await _seed(server.base_url)
        before_raw, before_settings = await _state()
        before = await _scan(key)
        blocker = await _lock_row("entry-039")
        try:
            async with httpx.AsyncClient(base_url=server.base_url, timeout=60) as http:
                await _send_and_kill_when_blocked(
                    server,
                    blocker,
                    lambda: http.patch(
                        "/master_password/update",
                        json={
                            "master_password": MASTER_PASSWORD,
                            "new_master_password": NEW_MASTER_PASSWORD,
                        },
                        headers={KEY_HEADER: key},
                    ),
                    "UPDATE passwords",
                )
        finally:
            await blocker.close()

    assert await _state() == (before_raw, before_settings)
    assert_same_vault(before, await _scan(key))
    [(hash_key,)] = await db_execute("SELECT hash_key FROM master_password")
    assert verify_master_password(MASTER_PASSWORD, hash_key)


async def test_killing_the_server_mid_import_writes_nothing(tmp_path: Path) -> None:
    with api_server(tmp_path / "server.log") as server:
        key = await _seed(server.base_url, entries=5)
        before = await _state()
        rows = "\n".join(f"import-{i:04d},pass-{i}" for i in range(2000))
        csv = f"name,password\nentry-004,overwritten\n{rows}\n".encode()
        blocker = await admin_connection()
        await blocker.execute("BEGIN")
        await blocker.execute(
            "INSERT INTO passwords (password_name, password_value) "
            "VALUES ('import-1999', 'x')"
        )
        try:
            async with httpx.AsyncClient(base_url=server.base_url, timeout=60) as http:
                await _send_and_kill_when_blocked(
                    server,
                    blocker,
                    lambda: http.post(
                        "/passwords/import/csv",
                        data={"on_conflict": "overwrite"},
                        files={"file": ("x.csv", csv, "text/csv")},
                        headers={KEY_HEADER: key},
                    ),
                    "INSERT INTO passwords",
                )
        finally:
            await blocker.close()

    assert await _state() == before


@pytest.mark.stress
async def test_rotations_killed_at_random_points_are_all_or_nothing(
    tmp_path: Path,
) -> None:
    passwords = [MASTER_PASSWORD, NEW_MASTER_PASSWORD]
    rng = random.Random(1729)
    with api_server(tmp_path / "seed.log") as server:
        key = await _seed(server.base_url, entries=150)
    reference = await _scan(key)
    current = 0
    outcomes = {"old": 0, "new": 0}

    for attempt in range(25):
        with api_server(tmp_path / f"server-{attempt}.log") as server:
            async with httpx.AsyncClient(base_url=server.base_url, timeout=60) as http:
                resp = await http.post(
                    "/master_password/check",
                    json={"master_password": passwords[current]},
                )
                key = resp.json()["key_derivation"]
                request = asyncio.create_task(
                    http.patch(
                        "/master_password/update",
                        json={
                            "master_password": passwords[current],
                            "new_master_password": passwords[1 - current],
                        },
                        headers={KEY_HEADER: key},
                    )
                )
                await asyncio.sleep(rng.uniform(0.0, 2.5))
                _kill(server)
                try:
                    await request
                except httpx.TransportError:
                    pass
        await asyncio.sleep(0.5)

        [(hash_key,)] = await db_execute("SELECT hash_key FROM master_password")
        if verify_master_password(passwords[1 - current], hash_key):
            current = 1 - current
            outcomes["new"] += 1
        else:
            assert verify_master_password(passwords[current], hash_key)
            outcomes["old"] += 1
        with api_server(tmp_path / f"check-{attempt}.log") as server:
            async with httpx.AsyncClient(base_url=server.base_url, timeout=60) as http:
                resp = await http.post(
                    "/master_password/check",
                    json={"master_password": passwords[current]},
                )
        assert_same_vault(reference, await _scan(resp.json()["key_derivation"]))

    assert outcomes["old"] and outcomes["new"], outcomes
