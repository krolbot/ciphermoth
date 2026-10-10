import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from api.rate_limit import limiter
from crud.session import engine
from main import app
from tests.support import (
    BACKEND_DIR,
    TABLES,
    reset_schema,
    run_alembic,
    update_control_dir,
)


def pytest_sessionstart(session: pytest.Session) -> None:
    reset_schema(os.environ["POSTGRES_DB"])
    run_alembic("upgrade", "head")


@pytest.fixture(autouse=True)
async def clean_state() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
        )
    limiter.reset()
    control = update_control_dir()
    shutil.rmtree(control, ignore_errors=True)
    control.mkdir(parents=True)
    yield


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver/api", timeout=60
    ) as http:
        yield http


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def live_server_log(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("live-server") / "uvicorn.log"


@pytest.fixture(scope="session")
def live_server(live_server_log: Path) -> Iterator[str]:
    port = _free_port()
    log_file = live_server_log.open("wb")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
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
            if proc.poll() is not None or time.monotonic() > deadline:
                output = live_server_log.read_text(errors="replace")
                raise RuntimeError(f"Test API server did not start:\n{output}")
            time.sleep(0.2)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_file.close()
