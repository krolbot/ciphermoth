import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from migration_gate import REFUSED_EXIT, decide, pending_migration
from settings import get_api_settings
from tests.support import (
    BACKEND_DIR,
    admin_connection,
    engine_url,
    ensure_database,
    reset_schema,
    run_alembic,
)
from update_protocol import (
    FIRST_PROTOCOL_2_RELEASE,
    LEGACY_UPDATER_WINDOW_SECONDS,
    MIN_UPDATER_PROTOCOL_LABEL,
    RECREATE_UPDATER_COMMAND,
    REQUIRED_UPDATER_PROTOCOL,
    UNREADABLE_RESULT_WINDOW_SECONDS,
)

ROOT = BACKEND_DIR.parent
VERSION = get_api_settings().version
GATE_DB = os.environ["POSTGRES_DB"].removesuffix("_test") + "_gate_test"
OLDER_HEAD = "8b9c0d1e2f3a"


def _maintenance(control: Path, **fields: object) -> None:
    payload = {
        "protocol": 2,
        "id": "a" * 32,
        "target": VERSION,
        "snapshot_verified": True,
        **fields,
    }
    (control / "maintenance.json").write_text(json.dumps(payload))


def _legacy_result(control: Path, state: str, target: str, age: float = 0) -> None:
    path = control / "result.json"
    path.write_text(
        json.dumps(
            {
                "state": state,
                "detail": "Applying update and restarting",
                "target": target,
                "finished_at": "2026-10-12T10:00:00Z",
            }
        )
    )
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))


def test_nothing_pending_is_always_allowed(tmp_path: Path) -> None:
    _legacy_result(tmp_path, "applying", f"v{VERSION}")
    assert decide(False, tmp_path, VERSION, time.time()) is None


def test_a_manual_update_may_migrate(tmp_path: Path) -> None:
    assert decide(True, tmp_path, VERSION, time.time()) is None


def test_a_capable_updater_with_a_verified_snapshot_may_migrate(
    tmp_path: Path,
) -> None:
    _maintenance(tmp_path)
    assert decide(True, tmp_path, VERSION, time.time()) is None


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"snapshot_verified": False}, "has not verified a database snapshot"),
        ({"snapshot_verified": "true"}, "has not verified a database snapshot"),
        ({"target": "99.0.0"}, "update to v99.0.0 is in progress"),
        ({"protocol": 1}, "speaks protocol 1"),
        ({"protocol": "2"}, "speaks protocol 2"),
    ],
)
def test_an_unsafe_update_may_not_migrate(
    tmp_path: Path, fields: dict, reason: str
) -> None:
    _maintenance(tmp_path, **fields)
    assert reason in (decide(True, tmp_path, VERSION, time.time()) or "")


def test_an_unreadable_maintenance_file_blocks_migrations(tmp_path: Path) -> None:
    (tmp_path / "maintenance.json").write_text("{broken")
    assert "unreadable" in (decide(True, tmp_path, VERSION, time.time()) or "")


@pytest.mark.parametrize("state", ["verifying", "applying"])
@pytest.mark.parametrize("target", [f"v{VERSION}", VERSION])
def test_an_old_updater_applying_this_release_may_not_migrate(
    tmp_path: Path, state: str, target: str
) -> None:
    _legacy_result(tmp_path, state, target)

    reason = decide(True, tmp_path, VERSION, time.time())

    assert reason is not None
    assert "predates updater protocol" in reason
    assert f"CIPHERMOTH_VERSION={FIRST_PROTOCOL_2_RELEASE}" in reason


@pytest.mark.parametrize(
    ("state", "target", "age"),
    [
        ("success", None, 0),
        ("rolled_back", None, 0),
        ("applying", "v0.0.1", 0),
        ("applying", None, LEGACY_UPDATER_WINDOW_SECONDS + 60),
    ],
    ids=["finished", "rolled-back", "other-target", "stale"],
)
def test_old_updater_results_that_are_not_this_update_do_not_block(
    tmp_path: Path, state: str, target: str | None, age: float
) -> None:
    _legacy_result(tmp_path, state, target or f"v{VERSION}", age)
    assert decide(True, tmp_path, VERSION, time.time()) is None


def test_a_v2_result_does_not_count_as_an_old_updater(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_text(
        json.dumps({"state": "applying", "target": f"v{VERSION}", "protocol": 2})
    )
    assert decide(True, tmp_path, VERSION, time.time()) is None


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_an_unreadable_recent_result_of_an_old_updater_blocks(tmp_path: Path) -> None:
    _legacy_result(tmp_path, "applying", f"v{VERSION}")
    (tmp_path / "result.json").chmod(0o000)
    try:
        assert decide(True, tmp_path, VERSION, time.time()) is not None
        later = time.time() + UNREADABLE_RESULT_WINDOW_SECONDS + 1
        assert decide(True, tmp_path, VERSION, later) is None
    finally:
        (tmp_path / "result.json").chmod(0o600)


@pytest.fixture
async def gate_db() -> str:
    await ensure_database(GATE_DB)
    await asyncio.to_thread(reset_schema, GATE_DB)
    return GATE_DB


async def test_an_empty_database_has_nothing_pending(gate_db: str) -> None:
    assert await pending_migration(engine_url(gate_db)) is False


async def test_pending_follows_the_alembic_revision(gate_db: str) -> None:
    await asyncio.to_thread(run_alembic, "upgrade", "head", database=gate_db)
    assert await pending_migration(engine_url(gate_db)) is False
    await asyncio.to_thread(run_alembic, "downgrade", OLDER_HEAD, database=gate_db)
    assert await pending_migration(engine_url(gate_db)) is True


async def test_a_vault_without_alembic_is_pending(gate_db: str) -> None:
    conn = await admin_connection(gate_db)
    try:
        await conn.execute("CREATE TABLE passwords (id int)")
    finally:
        await conn.close()
    assert await pending_migration(engine_url(gate_db)) is True


def _run_gate(database: str, control: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "migration_gate"],
        cwd=BACKEND_DIR,
        env={**os.environ, "POSTGRES_DB": database, "UPDATE_CONTROL_DIR": str(control)},
        capture_output=True,
        text=True,
        timeout=60,
    )


async def _revision(database: str) -> str:
    conn = await admin_connection(database)
    try:
        return await conn.fetchval("SELECT version_num FROM alembic_version")
    finally:
        await conn.close()


async def test_the_gate_stops_an_old_updater_from_migrating(
    gate_db: str, tmp_path: Path
) -> None:
    await asyncio.to_thread(run_alembic, "upgrade", OLDER_HEAD, database=gate_db)
    _legacy_result(tmp_path, "applying", f"v{VERSION}")

    proc = await asyncio.to_thread(_run_gate, gate_db, tmp_path)

    assert proc.returncode == REFUSED_EXIT, proc.stderr
    assert "will not change the database schema" in proc.stderr
    assert await _revision(gate_db) == OLDER_HEAD


async def test_the_gate_lets_a_capable_update_migrate(
    gate_db: str, tmp_path: Path
) -> None:
    await asyncio.to_thread(run_alembic, "upgrade", OLDER_HEAD, database=gate_db)
    _maintenance(tmp_path)

    proc = await asyncio.to_thread(_run_gate, gate_db, tmp_path)

    assert proc.returncode == 0, proc.stderr


async def test_the_gate_reports_an_unreachable_database(tmp_path: Path) -> None:
    env = {**os.environ, "POSTGRES_PORT": "1", "UPDATE_CONTROL_DIR": str(tmp_path)}

    proc = await asyncio.to_thread(
        lambda: subprocess.run(
            [sys.executable, "-m", "migration_gate"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    )

    assert proc.returncode == 1
    assert "cannot reach the database" in proc.stderr
    assert os.environ["POSTGRES_PASSWORD"] not in proc.stderr


def test_the_entrypoint_runs_the_gate_before_any_migration() -> None:
    lines = [
        line.strip()
        for line in (BACKEND_DIR / "entrypoint.sh").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert "set -euo pipefail" in lines
    assert lines.index("python -m migration_gate") < lines.index("alembic upgrade head")


@pytest.mark.parametrize("image", ["backend", "frontend"])
def test_release_images_declare_the_updater_protocol_they_need(image: str) -> None:
    dockerfile = (ROOT / "docker" / image / "Dockerfile").read_text()
    runtime = dockerfile.split("AS runtime", 1)[1]
    label = re.search(
        rf'LABEL {re.escape(MIN_UPDATER_PROTOCOL_LABEL)}="(\d+)"', runtime
    )
    assert label is not None
    assert int(label.group(1)) == REQUIRED_UPDATER_PROTOCOL


def test_the_updater_speaks_the_protocol_the_backend_requires() -> None:
    source = (ROOT / "docker" / "updater" / "updater.py").read_text()
    dockerfile = (ROOT / "docker" / "updater" / "Dockerfile").read_text()
    declared = re.search(r"^PROTOCOL = (\d+)$", source, re.M)
    label = re.search(r'LABEL io\.ciphermoth\.updater-protocol="(\d+)"', dockerfile)
    assert declared is not None and label is not None
    protocol = int(declared.group(1))
    assert protocol >= REQUIRED_UPDATER_PROTOCOL
    assert int(label.group(1)) == protocol
    assert f'MIN_PROTOCOL_LABEL = "{MIN_UPDATER_PROTOCOL_LABEL}"' in source
    flattened = re.sub(r'"\s+"', "", source)
    assert RECREATE_UPDATER_COMMAND in flattened
