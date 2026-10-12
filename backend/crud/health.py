from functools import lru_cache
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from crud.engine import Database

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations" / "ciphermoth"


@lru_cache
def migration_heads() -> frozenset[str]:
    return frozenset(ScriptDirectory(str(MIGRATIONS)).get_heads())


async def schema_state(database: Database) -> str:
    try:
        async with database.engine.connect() as connection:
            rows = await connection.execute(
                text("SELECT version_num FROM alembic_version")
            )
            revisions = frozenset(row[0] for row in rows)
    except (SQLAlchemyError, OSError):
        return "unknown"
    return "current" if revisions == migration_heads() else "pending"
