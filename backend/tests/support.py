import asyncio
import base64
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import asyncpg
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from crud.runtime_schema import ensure_runtime_schema
from crud.session import engine

BACKEND_DIR = Path(__file__).resolve().parent.parent

MASTER_PASSWORD = "Moth-Test-Vault-2026!"
NEW_MASTER_PASSWORD = "Moth-Rotated-Vault-2027?"
WRONG_MASTER_PASSWORD = "Not-The-Vault-Password-1"

TABLES = ("master_password", "passwords", "password_attachments", "settings")


def update_control_dir() -> Path:
    return Path(os.environ["UPDATE_CONTROL_DIR"])


Headers = list[tuple[bytes, bytes]]


def auth(key: str | bytes | None) -> Headers:
    if key is None:
        return []
    value = key if isinstance(key, bytes) else key.encode("latin-1")
    return [(b"x-ciphermoth-key-derivation", value)]


async def create_vault(
    client: httpx.AsyncClient, master_password: str = MASTER_PASSWORD
) -> str:
    resp = await client.post(
        "/master_password/create", json={"master_password": master_password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["key_derivation"]


async def unlock(
    client: httpx.AsyncClient, master_password: str = MASTER_PASSWORD
) -> str:
    resp = await client.post(
        "/master_password/check", json={"master_password": master_password}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True
    return body["key_derivation"]


def entry(name: str, value: str = "s3cret-Value!", **fields: object) -> dict:
    return {"password_name": name, "password_value": value, **fields}


def forged_keys(real_key: str) -> dict[str, str | bytes | None]:
    raw = base64.urlsafe_b64decode(real_key)
    return {
        "missing": None,
        "empty": "",
        "malformed": "not-a-fernet-key",
        "truncated": real_key[:-4],
        "random-valid-format": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "right-signing-half": base64.urlsafe_b64encode(
            raw[:16] + os.urandom(16)
        ).decode(),
        "right-encryption-half": base64.urlsafe_b64encode(
            os.urandom(16) + raw[16:]
        ).decode(),
        "non-ascii": "ключ-вольта".encode(),
    }


def bump_patch(version: str, delta: int = 1) -> str:
    major, minor, patch = (int(part) for part in version.lstrip("v").split("."))
    return f"v{major}.{minor}.{patch + delta}"


async def db_snapshot() -> dict[str, list[tuple]]:
    snapshot: dict[str, list[tuple]] = {}
    async with engine.connect() as conn:
        for table in TABLES:
            rows = await conn.execute(text(f"SELECT * FROM {table} ORDER BY id"))
            snapshot[table] = [tuple(row) for row in rows.all()]
    return snapshot


async def db_execute(sql: str, **params: object) -> list[tuple]:
    async with engine.begin() as conn:
        result = await conn.execute(text(sql), params)
        return [tuple(row) for row in result.all()] if result.returns_rows else []


def control_files() -> list[str]:
    return sorted(path.name for path in update_control_dir().iterdir())


async def admin_connection(database: str | None = None) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        database=database or os.environ["POSTGRES_DB"],
    )


async def _reset_schema(database: str) -> None:
    conn = await admin_connection(database)
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        await conn.close()


def reset_schema(database: str) -> None:
    asyncio.run(_reset_schema(database))


def engine_url(database: str) -> str:
    return (
        f"postgresql+asyncpg://{os.environ['POSTGRES_USER']}:"
        f"{quote(os.environ['POSTGRES_PASSWORD'])}@{os.environ['POSTGRES_HOST']}:"
        f"{os.environ['POSTGRES_PORT']}/{database}"
    )


async def _apply_runtime_schema(database: str) -> None:
    temporary = create_async_engine(engine_url(database))
    try:
        await ensure_runtime_schema(temporary)
    finally:
        await temporary.dispose()


def apply_runtime_schema(database: str) -> None:
    asyncio.run(_apply_runtime_schema(database))


def run_alembic(*args: str, database: str | None = None) -> str:
    env = dict(os.environ)
    if database:
        env["POSTGRES_DB"] = database
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise RuntimeError(f"alembic {' '.join(args)} failed:\n{output}")
    return output
