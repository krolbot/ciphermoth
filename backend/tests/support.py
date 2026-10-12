import asyncio
import base64
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import asyncpg
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
)

from crud.engine import Database
from crud.runtime_schema import ensure_runtime_schema
from helpers import generate_key_derivation
from main import app, get_application
from models import SETTINGS_DEFAULTS
from vault_sessions import Instant, VaultSessions, system_clock

BACKEND_DIR = Path(__file__).resolve().parent.parent

MASTER_PASSWORD = "Moth-Test-Vault-2026!"
NEW_MASTER_PASSWORD = "Moth-Rotated-Vault-2027?"
WRONG_MASTER_PASSWORD = "Not-The-Vault-Password-1"

TABLES = ("master_password", "passwords", "password_attachments", "settings")

engine = app.state.database.engine


def fresh_vault_sessions(clock: Callable[[], Instant] = system_clock) -> VaultSessions:
    return VaultSessions(
        idle_timeout_ms=SETTINGS_DEFAULTS["inactivity_ms"],
        clock=clock,
    )


def update_control_dir() -> Path:
    return Path(os.environ["UPDATE_CONTROL_DIR"])


Headers = list[tuple[bytes, bytes]]


def auth(token: str | bytes | None) -> Headers:
    """Headers for a vault session token, the credential current clients use."""
    if token is None:
        return []
    value = token if isinstance(token, bytes) else token.encode("latin-1")
    return [(b"x-ciphermoth-session", value)]


def key_auth(key: str | bytes | None) -> Headers:
    """Headers for the deprecated vault key credential of v1.4.x clients."""
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
    body = resp.json()
    assert "key_derivation" not in body
    return body["session_token"]


async def unlock(
    client: httpx.AsyncClient, master_password: str = MASTER_PASSWORD
) -> str:
    resp = await client.post(
        "/master_password/unlock", json={"master_password": master_password}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True
    assert "key_derivation" not in body
    return body["session_token"]


async def legacy_unlock(
    client: httpx.AsyncClient, master_password: str = MASTER_PASSWORD
) -> str:
    resp = await client.post(
        "/master_password/check", json={"master_password": master_password}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True
    return body["key_derivation"]


async def stored_vault_key(master_password: str = MASTER_PASSWORD) -> str:
    """The vault key, derived from the stored salt without asking the API."""
    [(salt,)] = await db_execute("SELECT salt FROM master_password ORDER BY id LIMIT 1")
    return generate_key_derivation(bytes(salt), master_password).decode()


async def create_legacy_vault(
    client: httpx.AsyncClient, master_password: str = MASTER_PASSWORD
) -> str:
    await create_vault(client, master_password)
    return await legacy_unlock(client, master_password)


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


async def forged_tokens(
    client: httpx.AsyncClient, real_token: str, vault_key: str
) -> dict[str, Headers]:
    """Session credentials that must never open the vault whose live session is
    ``real_token``."""
    locked = await unlock(client)
    resp = await client.post("/master_password/lock", headers=auth(locked))
    assert resp.status_code == 200, resp.text
    return {
        "missing": [],
        "empty": [(b"x-ciphermoth-session", b"")],
        "bearer prefixed": auth("Bearer " + real_token),
        "malformed": auth("not a session token"),
        "random": auth(secrets.token_urlsafe(32)),
        "truncated": auth(real_token[:-1]),
        "extended": auth(real_token + "A"),
        "case flipped": auth(real_token.swapcase()),
        "padded": auth(real_token + "="),
        "non-ascii": auth("сессия-токен".encode()),
        "in Authorization": [(b"authorization", b"Bearer " + real_token.encode())],
        "vault key as token": auth(vault_key),
        "token as vault key": key_auth(real_token),
        "locked": auth(locked),
    }


def bump_patch(version: str, delta: int = 1) -> str:
    major, minor, patch = (int(part) for part in version.lstrip("v").split("."))
    return f"v{major}.{minor}.{patch + delta}"


def previous_version(version: str) -> str:
    major, minor, patch = (int(part) for part in version.lstrip("v").split("."))
    if patch:
        return f"v{major}.{minor}.{patch - 1}"
    if minor:
        return f"v{major}.{minor - 1}.99"
    return f"v{major - 1}.99.99"


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


def updater_alive(protocol: int = 2, age: int = 0, running: bool = True) -> None:
    beat = (datetime.now(UTC) - timedelta(seconds=age)).isoformat()
    (update_control_dir() / "updater.json").write_text(
        json.dumps(
            {
                "protocol": protocol,
                "version": "1.5.1",
                "heartbeat_at": beat,
                "running": running,
                "busy": False,
            }
        )
    )


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


async def ensure_database(database: str) -> None:
    conn = await admin_connection()
    try:
        if not await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", database
        ):
            await conn.execute(f'CREATE DATABASE "{database}"')
    finally:
        await conn.close()


@asynccontextmanager
async def database_engine(database: str) -> AsyncIterator[AsyncEngine]:
    other = create_async_engine(engine_url(database))
    try:
        yield other
    finally:
        await other.dispose()


@asynccontextmanager
async def client_for_database(database: str) -> AsyncIterator[httpx.AsyncClient]:
    """An API client of a separate app instance, with its own vault sessions,
    whose requests run against ``database`` instead of the default test
    database."""
    other = Database(engine_url(database))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=get_application(database=other)),
            base_url="http://testserver/api",
            timeout=60,
        ) as http:
            yield http
    finally:
        await other.dispose()


@dataclass
class ApiServer:
    process: subprocess.Popen
    base_url: str


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def api_server(log_path: Path) -> Iterator[ApiServer]:
    """A real uvicorn process serving the app against the test database."""
    port = _free_port()
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--port", str(port)],
            cwd=BACKEND_DIR,
            env=dict(os.environ),
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        base_url = f"http://127.0.0.1:{port}/api"
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    if httpx.get(f"{base_url}/meta", timeout=1).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if process.poll() is not None or time.monotonic() > deadline:
                    output = log_path.read_text(errors="replace")
                    raise RuntimeError(f"Test API server did not start:\n{output}")
                time.sleep(0.2)
            yield ApiServer(process, base_url)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
