import asyncio
import json
import os
import sys
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from crud.engine import create_engine
from crud.health import migration_heads
from settings import get_api_settings
from update_protocol import (
    FIRST_PROTOCOL_2_RELEASE,
    LEGACY_UPDATER_WINDOW_SECONDS,
    REQUIRED_UPDATER_PROTOCOL,
    UNREADABLE_RESULT_WINDOW_SECONDS,
)

REFUSED_EXIT = 78

LEGACY_UPDATER = (
    "the one-click updater applying it predates updater protocol "
    f"{REQUIRED_UPDATER_PROTOCOL} and could not restore the database if the update "
    "failed. The database was not touched and the updater will roll back. Either "
    f"set CIPHERMOTH_VERSION={FIRST_PROTOCOL_2_RELEASE} in .env and run 'docker "
    "compose -f docker-compose.prod.yml --profile autoupdate pull' and '... "
    "--profile autoupdate up -d' (that release changes no schema and brings the "
    "new updater), then update with one click; or back up and update by hand"
)


def _plain(value: object) -> str:
    text_value = str(value or "")
    return text_value[1:] if text_value.startswith("v") else text_value


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def decide(pending: bool, control: Path, version: str, now: float) -> str | None:
    if not pending:
        return None
    maintenance = control / "maintenance.json"
    if os.path.lexists(maintenance):
        data = _read(maintenance)
        if data is None:
            return "an update is in progress but its maintenance file is unreadable"
        protocol = data.get("protocol")
        target = _plain(data.get("target"))
        if not isinstance(protocol, int) or protocol < REQUIRED_UPDATER_PROTOCOL:
            return (
                f"the updater applying it speaks protocol {protocol}; protocol "
                f"{REQUIRED_UPDATER_PROTOCOL} is required to restore the database "
                "if the update fails"
            )
        if target != version:
            return (
                f"an update to v{target} is in progress; let the updater finish or "
                "roll it back first"
            )
        if data.get("snapshot_verified") is not True:
            return "the updater has not verified a database snapshot yet"
        return None
    result = control / "result.json"
    try:
        modified = result.stat().st_mtime
    except OSError:
        return None
    if now - modified > LEGACY_UPDATER_WINDOW_SECONDS:
        return None
    try:
        data = json.loads(result.read_text())
    except PermissionError:
        recent = now - modified <= UNREADABLE_RESULT_WINDOW_SECONDS
        return LEGACY_UPDATER if recent else None
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("protocol"):
        return None
    if (
        data.get("state") in ("verifying", "applying")
        and _plain(data.get("target")) == version
    ):
        return LEGACY_UPDATER
    return None


async def pending_migration(url: str | None = None) -> bool:
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            tables = {
                row[0]
                for row in await connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }
            if "alembic_version" not in tables:
                return bool(tables)
            revisions = frozenset(
                row[0]
                for row in await connection.execute(
                    text("SELECT version_num FROM alembic_version")
                )
            )
    finally:
        await engine.dispose()
    return revisions != migration_heads()


def main() -> int:
    version = get_api_settings().version
    control = Path(os.environ.get("UPDATE_CONTROL_DIR", "/update-control"))
    try:
        pending = asyncio.run(pending_migration())
    except (SQLAlchemyError, OSError) as error:
        print(
            f"CipherMoth cannot reach the database ({type(error).__name__})",
            file=sys.stderr,
        )
        return 1
    reason = decide(pending, control, version, time.time())
    if reason is None:
        return 0
    print(
        f"CipherMoth v{version} will not change the database schema: {reason}.",
        file=sys.stderr,
    )
    return REFUSED_EXIT


if __name__ == "__main__":
    sys.exit(main())
